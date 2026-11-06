"""用例工作台路由（API V1.3 §3.8）。

包含两组 router：
- ``router``：/api/case-sets 用例集 CRUD、用例行批量保存、确认/废弃/映射、
  AI 候选生成、双模型对比与行级补全、xlsx 导入/模板、xlsx/xmind 导出；
- ``folders_router``：/api/case-folders 用例目录树管理（在 main.py 单独注册）。

AI 候选生成（ai-generate）与行级补全（ai-fill）只返回未落库候选，前端人工
确认后必须再经 PUT /api/case-sets/{id}/cases 保存；confirmed 用例集为版本
快照，任何写操作一律拒绝。expires_at 由任务域在关联任务进入
awaiting_case_confirm 时写入（+72h），本域不主动维护。
"""

import io
import json
import logging
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC
from typing import Any
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi import Request as FastApiRequest
from openpyxl import Workbook
from pydantic import ValidationError
from shared.case_compare import compare_case_runs
from shared.casegen import (
    MAX_COUNT,
    STRATEGY_WEIGHTS,
    build_coverage_prompt,
    build_prompts,
    build_review_prompt,
    clip_source,
    dedupe_cases,
    generation_token_budget,
    mark_pending_complete,
    parse_cases_with_stats,
    parse_coverage,
    parse_review,
    rebalance_with_stats,
    selfcheck,
)
from sqlalchemy.orm import Session

from ..case_excel import (
    EXPORT_FIXED_COLUMNS,
    IMPORT_MAX_BYTES,
    build_import_template,
    parse_cases_xlsx,
    xlsx_media_type,
)
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..llm_client import call_agent_model, call_profile_model, extract_json_array
from ..models import (
    AuditLog,
    CaseFolder,
    CaseItem,
    CaseSet,
    ProtocolProfile,
    Task,
    User,
    utcnow,
    uuid_str,
)
from ..schemas import (
    CaseAiCompareIn,
    CaseAiFillIn,
    CaseAiGenerateIn,
    CaseAiReviewIn,
    CaseCancelIn,
    CaseConfirmIn,
    CaseCoverageIn,
    CaseIn,
    CaseMapIn,
    CaseSetCreate,
    CaseSetDetailOut,
    CaseSetFromCandidatesIn,
    CaseSetOut,
    CaseSetUpdate,
    CasesPayload,
    FolderIn,
    FolderOut,
)
from ..task_policy import require_owned_source_file
from ._common import assert_folder_exists, client_ip, get_folder_or_404

router = APIRouter(prefix="/api/case-sets", tags=["case-sets"])
folders_router = APIRouter(prefix="/api/case-folders", tags=["case-folders"])
logger = logging.getLogger("ai-eval.cases")

# 用例行响应的固定字段键；扩展列同名键不写入 extras，避免平铺时覆盖固定字段
_RESERVED_EXTRA_KEYS = {
    "id",
    "case_set_id",
    "strategy",
    "priority",
    "module",
    "submodule",
    "feature_point",
    "name",
    "precondition",
    "steps",
    "expected",
    "test_type",
    "mapped",
    "pending_complete",
    "extras",
    "sort_order",
    "created_at",
    "updated_at",
}

# 6 大策略英文键 -> 中文策略名；默认配比对齐 API §3.8（正向40/反向25/边界15/等价类10/状态迁移5/场景5）
_STRATEGY_NAMES = {
    "positive": "正向",
    "negative": "反向",
    "boundary": "边界",
    "equivalence": "等价类",
    "state": "状态迁移",
    "scenario": "场景",
}
# 候选生成的模型调用超时：与 Worker 用例生成预算（280s）对齐，
# 否则同为 80 条 / 16384 tokens 的请求在向导路径更容易被 120s 默认值掐断。
GENERATION_TIMEOUT_S = 280.0
# 需求覆盖复审是独立轻量请求（输入是清单而非全量需求生成），预算单独一档。
COVERAGE_TIMEOUT_S = 120.0
COVERAGE_MAX_TOKENS = 2048
# 评审要读整份用例（60+ 条的步骤与预期），预算与超时都比覆盖检查大一档。
REVIEW_TIMEOUT_S = 150.0
REVIEW_MAX_TOKENS = 4096

_DEFAULT_STRATEGY_WEIGHTS = {
    "positive": 40,
    "negative": 25,
    "boundary": 15,
    "equivalence": 10,
    "state": 5,
    "scenario": 5,
}

# 来源文档注入 prompt 的最大字符数，防止超大文档撑爆模型上下文
_SOURCE_DOC_MAX_CHARS = 20_000

_XLSX_MEDIA_TYPE = xlsx_media_type()
_XMIND_MEDIA_TYPE = "application/vnd.xmind.workbook"


def _get_case_set_or_404(db: Session, set_id: str, *, lock: bool = False) -> CaseSet:
    """读取用例集或抛出 NOT_FOUND。"""
    query = db.query(CaseSet).filter(CaseSet.id == set_id)
    if lock:
        query = query.populate_existing().with_for_update()
    case_set = query.first()
    if not case_set:
        raise AppError(ErrorCode.NOT_FOUND, "用例集不存在")
    return case_set


def _assert_editable(case_set: CaseSet) -> None:
    """终态或超过确认期限的用例集不能再修改或确认。"""
    if case_set.status in {"confirmed", "cancelled"}:
        raise AppError(ErrorCode.VALIDATION, "用例集已终态，不可修改")
    deadline = case_set.expires_at
    if deadline and deadline.replace(tzinfo=deadline.tzinfo or UTC) <= utcnow():
        raise AppError(ErrorCode.VALIDATION, "用例确认已超时，请重新生成")


def _lock_editable_case_set(db: Session, set_id: str) -> tuple[CaseSet, Task | None]:
    """与超时扫描保持 CaseSet→Task 锁序，并在持锁后复验编辑状态。"""
    case_set = _get_case_set_or_404(db, set_id, lock=True)
    task = None
    if case_set.task_id:
        task = db.query(Task).filter(Task.id == case_set.task_id).populate_existing().with_for_update().first()
    _assert_editable(case_set)
    if task is not None and task.status != "awaiting_case_confirm":
        raise AppError(ErrorCode.VALIDATION, "关联任务已不在等待确认状态")
    return case_set, task


def _case_to_item(case: CaseItem) -> dict[str, Any]:
    """把用例行展开为契约用例项：固定字段 + extras 扩展键平铺。"""
    item: dict[str, Any] = {
        "id": case.id,
        "strategy": case.strategy,
        "priority": case.priority,
        "module": case.module or "",
        "submodule": case.submodule or "",
        "feature_point": case.feature_point or "",
        "name": case.name,
        "precondition": case.precondition or "",
        "steps": case.steps or "",
        "expected": case.expected or "",
        "test_type": case.test_type or "",
        "mapped": bool(case.mapped),
        "pending_complete": bool(case.pending_complete),
    }
    item.update({key: value for key, value in (case.extras or {}).items() if key not in _RESERVED_EXTRA_KEYS})
    return item


def _list_cases(db: Session, case_set: CaseSet) -> list[CaseItem]:
    """按排序号与创建时间返回用例集内全部用例行。"""
    return (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == case_set.id)
        .order_by(CaseItem.sort_order.asc(), CaseItem.created_at.asc())
        .all()
    )


def _refresh_generated_count(db: Session, case_set: CaseSet) -> None:
    """按 case_items 实况重算用例集生成条数。"""
    case_set.generated_count = (
        db.query(CaseItem).filter(CaseItem.case_set_id == case_set.id).count()
    )


def _upsert_case(
    db: Session, case_set: CaseSet, case_in: CaseIn, case: CaseItem | None, sort_order: int
) -> CaseItem:
    """按用例 id 更新或插入单行；已有行上未提供的可空字段保留原值。"""
    provided = case_in.model_fields_set
    if case is None:
        case = CaseItem(
            id=case_in.id or uuid_str(),
            case_set_id=case_set.id,
            strategy=case_in.strategy,
            priority=case_in.priority,
            module=case_in.module,
            submodule=case_in.submodule or "",
            feature_point=case_in.feature_point or "",
            name=case_in.name,
            precondition=case_in.precondition or "",
            steps=case_in.steps or "",
            expected=case_in.expected or "",
            test_type=case_in.test_type or "",
            sort_order=sort_order,
        )
        db.add(case)
    else:
        case.sort_order = sort_order
        case.strategy = case_in.strategy
        case.priority = case_in.priority
        case.module = case_in.module
        case.name = case_in.name
        if "submodule" in provided:
            case.submodule = case_in.submodule or ""
        if "feature_point" in provided:
            case.feature_point = case_in.feature_point or ""
        if "precondition" in provided:
            case.precondition = case_in.precondition or ""
        if "steps" in provided:
            case.steps = case_in.steps or ""
        if "expected" in provided:
            case.expected = case_in.expected or ""
        if "test_type" in provided:
            case.test_type = case_in.test_type or ""
    extras = {k: v for k, v in (case_in.model_extra or {}).items() if k not in _RESERVED_EXTRA_KEYS}
    if extras:
        merged = dict(case.extras or {})
        merged.update(extras)
        case.extras = merged
    # name / expected 任一缺失即视为待补全，映射入库时进入目标集待补全行
    case.pending_complete = not (case.name or "").strip() or not (case.expected or "").strip()
    return case


def _merge_column_schema(case_set: CaseSet, extra_keys: list[str]) -> None:
    """把用例中未登记的扩展列并入 column_schema，已有 key 不覆盖。"""
    schema = [col for col in (case_set.column_schema or []) if isinstance(col, dict)]
    existing = {str(col.get("key") or "") for col in schema}
    for key in extra_keys:
        if not key or key in existing or key in _RESERVED_EXTRA_KEYS:
            continue
        schema.append({"key": key, "name": key, "type": "string", "sort_order": len(schema) + 1})
        existing.add(key)
    case_set.column_schema = schema


def _selfcheck_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """编辑/导入后重算确认页提示：无核心正向、缺约束反向。

    这里拿不到用户生成时的策略配比（用例集不持久化该配置），因此用 ``warning``
    而不是 ``error``：用户主动选「只生成正向」时，不能拿默认配比否定其配置。
    生成阶段的 ``selfcheck`` 有配比上下文，仍按 ``error`` 报缺项。
    """
    checks: list[dict[str, Any]] = []
    positives = [item for item in items if item.get("strategy") == "正向"]
    core_positives = [
        item
        for item in positives
        if item.get("priority") == "HX" or "核心" in str(item.get("test_type") or "")
    ]
    if not positives:
        checks.append({"level": "warning", "code": "no_core_positive", "message": "自检提示：未导入任何正向策略用例"})
    elif not core_positives:
        checks.append({"level": "warning", "code": "no_core_positive", "message": "自检提示：正向用例中没有 HX 核心用例"})
    if not any(item.get("strategy") == "反向" for item in items):
        checks.append({"level": "warning", "code": "missing_constraint_negative", "message": "自检提示：缺少反向（约束/异常）策略用例"})
    return checks


def _parsed_row_to_case_in(item: dict[str, Any]) -> CaseIn:
    """把 Excel 解析行转为 CaseIn；extras 平铺为扩展列。"""
    payload = {key: value for key, value in item.items() if key != "extras"}
    payload.update(item.get("extras") or {})
    return CaseIn.model_validate(payload)


def _build_xlsx(case_set: CaseSet, cases: list[CaseItem]) -> bytes:
    """生成 Excel 工作簿字节流：固定列 + column_schema 声明的扩展列。"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "用例集"
    extra_columns = [
        (col.get("key", ""), col.get("name") or col.get("key", ""))
        for col in (case_set.column_schema or [])
    ]
    sheet.append([title for _, title in EXPORT_FIXED_COLUMNS] + [name for _, name in extra_columns])
    for case in cases:
        item = _case_to_item(case)
        row: list[Any] = []
        for field, _title in EXPORT_FIXED_COLUMNS:
            value = item.get(field)
            if isinstance(value, bool):
                value = "是" if value else "否"
            row.append(value)
        row.extend((case.extras or {}).get(key) for key, _ in extra_columns)
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _xmind_topic(topic_id: str, title: str, timestamp: int, note: str = "", children: str = "") -> str:
    """拼接单个 XMind topic 节点 XML；标题与备注均做 XML 转义。"""
    parts = [f'<topic id="{topic_id}" timestamp="{timestamp}">', f"<title>{escape(title)}</title>"]
    if note:
        parts.append(f"<notes><plain>{escape(note)}</plain></notes>")
    if children:
        parts.append(f'<children><topics type="attached">{children}</topics></children>')
    parts.append("</topic>")
    return "".join(parts)


def _build_xmind(case_set: CaseSet, cases: list[CaseItem]) -> bytes:
    """生成 XMind 8 文件字节流（zip：content.xml + META-INF/manifest.xml）。

    结构：根节点=用例集名，二级节点按 module 分组，叶子=用例名（expected 写入备注）。
    """
    timestamp = int(time.time() * 1000)
    modules: dict[str, list[CaseItem]] = {}
    for case in cases:
        modules.setdefault(case.module or "未分组", []).append(case)
    modules_xml = "".join(
        _xmind_topic(
            uuid_str(),
            module,
            timestamp,
            children="".join(
                _xmind_topic(uuid_str(), case.name, timestamp, note=case.expected or "")
                for case in group
            ),
        )
        for module, group in modules.items()
    )
    content_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" '
        'xmlns:fo="http://www.w3.org/1999/XSL/Format" '
        'xmlns:svg="http://www.w3.org/2000/svg" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" version="2.0">'
        f'<sheet id="{uuid_str()}" timestamp="{timestamp}">'
        + _xmind_topic(uuid_str(), case_set.name, timestamp, children=modules_xml)
        + "</sheet></xmap-content>"
    )
    manifest_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<manifest xmlns="urn:xmind:xmap:xmlns:manifest:1.0">'
        '<file-entry full-path="content.xml" media-type="text/xml"/>'
        "</manifest>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.xml", content_xml)
        archive.writestr("META-INF/manifest.xml", manifest_xml)
    return buffer.getvalue()


@router.get("")
def list_case_sets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    page: int | None = Query(default=None, ge=1, description="当前页码（从1开始）"),
    page_size: int | None = Query(default=None, ge=1, le=500, description="每页条数"),
    q: str | None = Query(default=None, description="用例集名称检索关键字"),
):
    """列出全部用例集，按契约返回 {items, total} 包装，支持分页与关键词过滤。"""
    query = db.query(CaseSet)
    if q and q.strip():
        query = query.filter(CaseSet.name.ilike(f"%{q.strip()}%"))
    total = query.count()
    query = query.order_by(CaseSet.created_at.desc())
    if page is not None and page_size is not None:
        rows = query.offset((page - 1) * page_size).limit(page_size).all()
    else:
        rows = query.all()
    return {"items": [CaseSetOut.model_validate(row) for row in rows], "total": total}


@router.post("", response_model=CaseSetOut, status_code=201)
def create_case_set(
    body: CaseSetCreate,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建空用例集（status=generated，generated_count=0）；expires_at 留空由任务域写入。"""
    if body.folder_id:
        assert_folder_exists(db, CaseFolder, body.folder_id)
    case_set = CaseSet(
        name=body.name,
        folder_id=body.folder_id,
        column_schema=[col.model_dump() for col in body.column_schema or []],
        created_by=user.id,
    )
    db.add(case_set)
    db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_create",
            target_type="case_set",
            target_id=case_set.id,
            detail={"name": case_set.name},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(case_set)
    return case_set


# 固定路径 /ai-generate 必须声明在 /{set_id} 之前，避免被路径参数吞掉
@router.post("/ai-generate")
def ai_generate_cases(
    body: CaseAiGenerateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按 Agent 协议档生成候选用例（新八字段格式 + 新优先级）；候选不落库。

    响应同时返回自检结果与裁剪统计，前端可在采纳前就提示缺项，
    不必等到保存后才发现「缺核心正向」。
    """
    source_text = body.source_text or ""
    if body.source_doc_id:
        source_text = _read_stored_file_text(db, body.source_doc_id, user.id)
    if not source_text.strip():
        raise AppError(ErrorCode.VALIDATION, "需要提供需求文档内容 source_text 或来源文档 source_doc_id")
    source_text, source_truncated = clip_source(source_text)

    weights = body.strategy_weights or STRATEGY_WEIGHTS
    max_count = body.max_count
    system, user_prompt = build_prompts(source_text, max_count, weights=weights)
    # 与 Worker 同一预算口径（280s）：80 条十六字段的中文 JSON 在 120s 内经常跑不完。
    result = call_agent_model(db, system, user_prompt, temperature=0.3,
                              max_tokens=generation_token_budget(max_count),
                              timeout_s=GENERATION_TIMEOUT_S)
    cases, dropped = _materialize_cases(result.text, max_count, weights)
    if not cases:
        raise AppError(ErrorCode.UPSTREAM, "模型未返回符合所选策略的有效用例")
    return {
        "items": [mark_pending_complete(case) for case in cases],
        "checks": selfcheck(cases, weights=weights),
        "source_truncated": source_truncated,
        "dropped": dropped,
    }


def _materialize_cases(text: str, max_count: int, weights: dict[str, int]) -> tuple[list[dict], dict[str, int]]:
    """解析、去重再按策略裁剪。两条生成路径共用，避免对比和单模型结果口径分叉。"""
    try:
        cases, parse_stats = parse_cases_with_stats(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "模型输出无法解析为用例") from exc
    cases, dropped_duplicate = dedupe_cases(cases)
    cases, dropped = rebalance_with_stats(cases, max_count, weights=weights)
    return cases, {**dropped, "dropped_duplicate": dropped_duplicate, **parse_stats}


def _load_compare_profiles(db: Session, profile_ids: list[str]) -> list[ProtocolProfile]:
    """按请求顺序取出两个已启用 agent 用途的协议档。"""
    found = {
        profile.id: profile
        for profile in db.query(ProtocolProfile).filter(ProtocolProfile.id.in_(profile_ids)).all()
    }
    profiles: list[ProtocolProfile] = []
    for profile_id in profile_ids:
        profile = found.get(profile_id)
        if profile is None:
            raise AppError(ErrorCode.NOT_FOUND, "协议档不存在")
        if "agent" not in (profile.usages or []):
            raise AppError(ErrorCode.VALIDATION, f"协议档「{profile.name}」未启用 agent 用途")
        profiles.append(profile)
    return profiles


def _profile_snapshot(profile: ProtocolProfile) -> Any:
    """复制线程需要的协议档字段，避免工作线程触发 ORM 懒加载。"""
    from types import SimpleNamespace

    return SimpleNamespace(
        id=profile.id,
        name=profile.name,
        model=profile.model,
        protocol=profile.protocol,
        base_url=profile.base_url,
        usages=list(profile.usages or []),
        anthropic_version=profile.anthropic_version,
        encrypted_key=profile.encrypted_key,
    )


def _failed_run(profile: Any, code: str, message: str, elapsed_ms: int) -> dict[str, Any]:
    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "model": profile.model,
        "ok": False,
        "error": {"code": code, "message": message},
        "elapsed_ms": elapsed_ms,
        "items": [],
        "checks": [],
        "dropped": {},
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _generate_with_profile(
    profile: Any,
    system: str,
    user_prompt: str,
    max_count: int,
    weights: dict[str, int],
) -> dict[str, Any]:
    """跑一侧模型。失败留在该侧结果里，不让另一侧的成功被整单错误盖掉。"""
    started = time.perf_counter()
    payload: dict[str, Any] = {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "model": profile.model,
        "ok": False,
        "error": None,
        "elapsed_ms": 0,
        "items": [],
        "checks": [],
        "dropped": {
            "dropped_unknown_strategy": 0,
            "dropped_over_quota": 0,
            "dropped_duplicate": 0,
            "dropped_missing_name": 0,
            "dropped_non_object": 0,
        },
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    try:
        result = call_profile_model(
            profile, system, user_prompt, temperature=0.3,
            max_tokens=generation_token_budget(max_count),
            timeout_s=GENERATION_TIMEOUT_S,
        )
        cases, dropped = _materialize_cases(result.text, max_count, weights)
        if not cases:
            raise AppError(ErrorCode.UPSTREAM, "模型未返回符合所选策略的有效用例")
        payload.update({
            "ok": True,
            "model": profile.model,
            "items": [mark_pending_complete(case) for case in cases],
            "checks": selfcheck(cases, weights=weights),
            "dropped": dropped,
            "usage": {
                "prompt_tokens": int((result.usage or {}).get("prompt_tokens") or 0),
                "completion_tokens": int((result.usage or {}).get("completion_tokens") or 0),
                "total_tokens": int((result.usage or {}).get("total_tokens") or 0),
            },
        })
    except AppError as exc:
        payload["error"] = {"code": exc.code.value, "message": exc.message}
    except Exception as exc:
        logger.warning("模型对比单侧失败 type=%s", type(exc).__name__)
        payload["error"] = {"code": ErrorCode.INTERNAL.value, "message": "AI 生成调用失败，请稍后重试"}
    payload["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return payload


@router.post("/ai-compare")
def ai_compare_cases(
    body: CaseAiCompareIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """同一需求并行交给两个协议档生成候选，并返回本轮结构对比。

    候选不落库。两侧同时发起，墙钟时间接近较慢的一侧，而不是两次相加。
    一侧失败时仍返回另一侧结果，方便看出是模型差异还是调用失败。
    """
    source_text = body.source_text or ""
    if body.source_doc_id:
        source_text = _read_stored_file_text(db, body.source_doc_id, user.id)
    if not source_text.strip():
        raise AppError(ErrorCode.VALIDATION, "需要提供需求文档内容 source_text 或来源文档 source_doc_id")
    source_text, source_truncated = clip_source(source_text)
    profiles = _load_compare_profiles(db, body.profile_ids)
    weights = body.strategy_weights or STRATEGY_WEIGHTS
    max_count = body.max_count
    system, user_prompt = build_prompts(source_text, max_count, weights=weights)
    # 先读完 ORM 字段再进线程。线程里只拿这份快照，避免复用请求上的数据库会话。
    snapshots = [_profile_snapshot(profile) for profile in profiles]
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="case-compare")
    try:
        futures = [
            pool.submit(_generate_with_profile, profile, system, user_prompt, max_count, weights)
            for profile in snapshots
        ]
        runs: list[dict[str, Any]] = []
        for profile, future in zip(snapshots, futures, strict=True):
            try:
                runs.append(future.result(timeout=GENERATION_TIMEOUT_S + 5))
            except FutureTimeout:
                runs.append(_failed_run(
                    profile,
                    ErrorCode.TIMEOUT.value,
                    "模型对比超时，请减少生成条数后重试",
                    int(GENERATION_TIMEOUT_S * 1000),
                ))
    finally:
        # 不等待卡住的工作线程，避免单侧超时把整次请求留在反向代理读超时之外。
        pool.shutdown(wait=False, cancel_futures=True)
    comparison = compare_case_runs(
        runs[0]["items"] if runs[0]["ok"] else [],
        runs[1]["items"] if runs[1]["ok"] else [],
        weights,
        left_name=runs[0]["profile_name"] or "模型 A",
        right_name=runs[1]["profile_name"] or "模型 B",
        left_ok=bool(runs[0]["ok"]),
        right_ok=bool(runs[1]["ok"]),
    )
    return {"source_truncated": source_truncated, "runs": runs, "comparison": comparison}


@router.post("/ai-coverage")
def check_case_coverage(
    body: CaseCoverageIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """需求覆盖自检：找出需求中有、候选里没有的功能点。

    独立请求而非塞进生成流程：生成已占 280 秒预算，再叠加一次模型调用会突破
    反向代理的读超时。这里只做一次轻量复审，失败直接报错由用户重试。
    """
    source_text = body.source_text or ""
    if body.source_doc_id:
        source_text = _read_stored_file_text(db, body.source_doc_id, user.id)
    if not source_text.strip():
        raise AppError(ErrorCode.VALIDATION, "需要提供需求文档内容 source_text 或来源文档 source_doc_id")
    source_text, source_truncated = clip_source(source_text)
    cases = [case.model_dump() for case in body.cases]
    system, user_prompt = build_coverage_prompt(source_text, cases)
    result = call_agent_model(db, system, user_prompt, temperature=0.1,
                              max_tokens=COVERAGE_MAX_TOKENS,
                              timeout_s=COVERAGE_TIMEOUT_S)
    try:
        coverage = parse_coverage(result.text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "覆盖检查输出无法解析，请重试") from exc
    return {**coverage, "source_truncated": source_truncated, "case_count": len(cases)}


@router.post("/from-candidates", response_model=CaseSetDetailOut, status_code=201)
def create_case_set_from_candidates(
    body: CaseSetFromCandidatesIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """一次事务保存人工采纳的候选、用例集和自检结果，失败不留空草稿。"""
    name = body.name.strip()
    if not name:
        raise AppError(ErrorCode.VALIDATION, "用例集名称不能为空")
    try:
        if body.folder_id:
            assert_folder_exists(db, CaseFolder, body.folder_id)
        case_set = CaseSet(name=name, folder_id=body.folder_id, created_by=user.id, revision=1)
        db.add(case_set)
        db.flush()
        extra_keys = [key for case_in in body.cases for key in (case_in.model_extra or {})]
        _merge_column_schema(case_set, extra_keys)
        for index, case_in in enumerate(body.cases):
            # 候选不能指定持久身份；只采纳正文和业务扩展列。
            _upsert_case(db, case_set, case_in.model_copy(update={"id": None}), None, index)
        db.flush()
        items = [_case_to_item(case) for case in _list_cases(db, case_set)]
        case_set.generated_count = len(items)
        case_set.checks = _selfcheck_items(items)
        db.add(AuditLog(
            user_id=user.id, action="case_set_create", target_type="case_set",
            target_id=case_set.id,
            detail={"name": case_set.name, "source": "ai_candidates", "case_count": len(items)},
            ip=client_ip(request),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(case_set)
    detail = CaseSetDetailOut.model_validate(case_set)
    detail.cases = items
    return detail


def _read_stored_file_text(db: Session, file_id: str, user_id: str) -> str:
    """读取来源文档正文（文本/xlsx），用于 AI 用例生成的素材。"""
    from pathlib import Path

    stored = require_owned_source_file(db, file_id, user_id)
    if not stored.storage_path:
        raise AppError(ErrorCode.NOT_FOUND, "来源文档不存在或已删除")
    path = Path(stored.storage_path)
    if not path.exists():
        raise AppError(ErrorCode.NOT_FOUND, "来源文档已从磁盘移除")
    suffix = Path(stored.filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm"} or stored.kind in {"xlsx", "xlsm"}:
        from openpyxl import load_workbook

        lines: list[str] = []
        # 上传存储使用 .bin；通过字节流避免 openpyxl 按内部路径后缀拒绝合法工作簿。
        try:
            wb = load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=True)
        except (zipfile.BadZipFile, OSError, ValueError, KeyError) as exc:
            raise AppError(ErrorCode.VALIDATION, "来源文档不是有效的 Excel 工作簿") from exc
        try:
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    line = " ".join(str(cell) for cell in row if cell is not None)
                    if line.strip():
                        lines.append(line)
        finally:
            wb.close()
        # 截断由调用方 clip_source 统一处理，这里才能把「是否截断」如实报给前端。
        return "\n".join(lines)
    return path.read_bytes().decode("utf-8", errors="ignore")


@router.get("/import-template")
def download_import_template(
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """下载平台标准列 Excel 模板（含填写说明工作表）。"""
    content = build_import_template()
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_import_template",
            target_type="case_set",
            target_id="template",
            detail={"fmt": "xlsx"},
            ip=client_ip(request),
        )
    )
    db.commit()
    filename = quote("用例导入模板.xlsx")
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# 固定路径 /import 必须在 /{set_id} 路由前声明，避免被当作用例集 ID。
@router.post("/import", status_code=201)
async def create_case_set_from_excel(
    request: FastApiRequest,
    file: UploadFile = File(...),
    name: str = Form(...),
    folder_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """单事务创建用例集并导入 Excel；失败时不留下空草稿。"""
    name = name.strip()
    if not name or len(name) > 100:
        raise AppError(ErrorCode.VALIDATION, "用例集名称长度须为 1 至 100 字")
    parsed, fmt, skipped = await _read_import_file(file)
    try:
        if folder_id:
            assert_folder_exists(db, CaseFolder, folder_id)
        case_set = CaseSet(name=name, folder_id=folder_id, created_by=user.id)
        db.add(case_set)
        db.flush()
        imported = _write_imported_cases(
            db, case_set, parsed, fmt, skipped, "replace", file.filename, request, user,
        )
        db.add(AuditLog(
            user_id=user.id, action="case_set_create", target_type="case_set",
            target_id=case_set.id, detail={"name": case_set.name}, ip=client_ip(request),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(case_set)
    return {"case_set_id": case_set.id, **_import_result(case_set, fmt, "replace", imported, skipped)}


@router.get("/{set_id}", response_model=CaseSetDetailOut)
def get_case_set(
    set_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """读取用例集详情，含全部用例行（固定字段 + 扩展列平铺）。"""
    case_set = _get_case_set_or_404(db, set_id)
    detail = CaseSetDetailOut.model_validate(case_set)
    detail.cases = [_case_to_item(case) for case in _list_cases(db, case_set)]
    return detail


@router.put("/{set_id}", response_model=CaseSetOut)
def update_case_set(
    set_id: str,
    body: CaseSetUpdate,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按提供的字段更新用例集；column_schema 整体替换，confirmed 集拒绝修改。"""
    case_set, _task = _lock_editable_case_set(db, set_id)
    values = body.model_dump(exclude_unset=True)
    expected_revision = values.pop("expected_revision", None)
    if "column_schema" in values and values["column_schema"] is None:
        raise AppError(ErrorCode.VALIDATION, "column_schema 不能为 null，请传空数组清空扩展列")
    if "column_schema" in values and expected_revision != case_set.revision:
        raise AppError(ErrorCode.CONCURRENCY, "用例列已由其他操作更新，请刷新后再保存")
    if "folder_id" in values:
        folder_id = values.pop("folder_id")
        if folder_id is not None:
            assert_folder_exists(db, CaseFolder, folder_id)
        case_set.folder_id = folder_id
    if "column_schema" in values:
        case_set.column_schema = values.pop("column_schema")
        case_set.revision += 1
    for field, value in values.items():
        setattr(case_set, field, value)
    # 用例集元信息变更写审计（与 dataset_update / folder_update 口径一致）
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_update",
            target_type="case_set",
            target_id=case_set.id,
            detail={"name": case_set.name, "fields": sorted(body.model_fields_set)},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(case_set)
    return case_set


@router.put("/{set_id}/cases")
def save_cases(
    set_id: str,
    body: CasesPayload,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按用例 id 批量 upsert 用例行与扩展列；id 缺省时服务端生成，保存后重算 generated_count。"""
    case_set, _task = _lock_editable_case_set(db, set_id)
    if case_set.revision != body.expected_revision:
        raise AppError(ErrorCode.CONCURRENCY, "用例已由其他操作更新，请刷新后再保存")
    if body.column_schema is not None:
        case_set.column_schema = [column.model_dump() for column in body.column_schema]
    existing = {
        case.id: case
        for case in db.query(CaseItem).filter(CaseItem.case_set_id == case_set.id).all()
    }
    # 当前视图保存语义：载荷中未包含的现有用例视为已删除（前端"批量删除→保存修改"依赖此行为）
    payload_ids = {case_in.id for case_in in body.cases if case_in.id}
    for case_id, case in existing.items():
        if case_id not in payload_ids:
            db.delete(case)
    for index, case_in in enumerate(body.cases):
        target = existing.get(case_in.id) if case_in.id else None
        if case_in.id and target is None:
            # 显式 id 未命中时按插入处理；若 id 已被其他用例集占用则拒绝，避免跨集串行
            clash = db.query(CaseItem).filter(CaseItem.id == case_in.id).first()
            if clash:
                raise AppError(ErrorCode.VALIDATION, f"用例 {case_in.id} 不属于该用例集")
        _upsert_case(db, case_set, case_in, target, index)
    db.flush()
    _refresh_generated_count(db, case_set)
    cases = _list_cases(db, case_set)
    case_set.checks = _selfcheck_items([_case_to_item(case) for case in cases])
    case_set.revision += 1
    db.commit()
    return {"items": [_case_to_item(case) for case in cases], "total": len(cases),
            "checks": case_set.checks, "revision": case_set.revision}


@router.post("/{set_id}/ai-review")
def ai_review_case_set(
    set_id: str,
    body: CaseAiReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """对已落库的用例集做 AI 评审：覆盖/可执行/重复/分布四维打分 + 问题清单。

    结果写入 ``case_sets.checks``（``kind="ai_review"``，覆盖旧评审、保留自检红字），
    不改变用例内容与状态；confirmed 用例集是版本快照，仍允许评审（只读）。
    """
    case_set = db.query(CaseSet).filter(CaseSet.id == set_id).first()
    if not case_set:
        raise AppError(ErrorCode.NOT_FOUND, "用例集不存在")
    items = (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == set_id)
        .order_by(CaseItem.sort_order)
        .all()
    )
    if not items:
        raise AppError(ErrorCode.VALIDATION, "用例集为空，没有可评审的内容")

    source_text = (body.source_text or "").strip()
    doc_id = body.source_doc_id
    if not source_text and not doc_id and case_set.task_id:
        task = db.query(Task).filter(Task.id == case_set.task_id).first()
        doc_id = ((task.config or {}).get("case_source") or {}).get("file_id") if task else None
    if doc_id and not source_text:
        try:
            source_text = _read_stored_file_text(db, doc_id, user.id)
        except Exception:  # noqa: BLE001 - 来源不可读时退化为纯用例评审
            logger.warning("AI 评审读取来源文档失败 doc_id=%s", doc_id)
    source_truncated = False
    if source_text.strip():
        source_text, source_truncated = clip_source(source_text)
    else:
        source_text = "（未提供需求文档：只评审用例自身的可执行性、重复与策略分布）"

    cases = [
        {
            "module": item.module,
            "name": item.name,
            "strategy": item.strategy,
            "steps": item.steps,
            "expected": item.expected,
        }
        for item in items[:MAX_COUNT]
    ]
    system, user_prompt = build_review_prompt(source_text, cases)
    result = call_agent_model(
        db, system, user_prompt, temperature=0.1,
        max_tokens=REVIEW_MAX_TOKENS, timeout_s=REVIEW_TIMEOUT_S,
    )
    try:
        review = parse_review(result.text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "评审输出无法解析，请重试") from exc

    review.update(
        {
            "reviewed_at": utcnow().isoformat(),
            "case_count": len(cases),
            "source_truncated": source_truncated,
        }
    )
    checks = [
        check for check in (case_set.checks or [])
        if not (isinstance(check, dict) and check.get("kind") == "ai_review")
    ]
    checks.append({"kind": "ai_review", **review})
    case_set.checks = checks
    db.commit()
    return review


@router.post("/{set_id}/confirm", response_model=CaseSetOut)
def confirm_case_set(
    set_id: str,
    body: CaseConfirmIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """确认用例入库（ok=true）或废弃（ok=false），并联动关联 testcase 任务状态。

    edits / mapping_target / target_id 为兼容字段，仅记入审计明细；
    旧评测数据集映射已停用。
    """
    case_set, task = _lock_editable_case_set(db, set_id)
    if case_set.revision != body.expected_revision:
        raise AppError(ErrorCode.CONCURRENCY, "用例已由其他操作更新，请刷新后再审核")
    if body.ok:
        if case_set.generated_count < 1:
            raise AppError(ErrorCode.VALIDATION, "用例集至少需要一条用例才能确认入库")
        case_set.status = "confirmed"
        case_set.confirmed_count = case_set.generated_count
        task_status = "succeeded"
    else:
        case_set.status = "cancelled"
        task_status = "cancelled"
    # 仅当关联任务仍在等待用例确认时联动流转，其余状态由任务域自行负责
    if task:
        task.status = task_status
        task.finished_at = utcnow()
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_confirm",
            target_type="case_set",
            target_id=case_set.id,
            detail={
                "name": case_set.name,
                "ok": body.ok,
                "mapping_target": body.mapping_target,
                "target_id": body.target_id,
            },
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(case_set)
    return case_set


@router.post("/{set_id}/cancel", response_model=CaseSetOut)
def cancel_case_set(
    set_id: str,
    body: CaseCancelIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """废弃用例集；关联的 awaiting_case_confirm 任务同步置 cancelled。"""
    case_set, task = _lock_editable_case_set(db, set_id)
    if case_set.revision != body.expected_revision:
        raise AppError(ErrorCode.CONCURRENCY, "用例已由其他操作更新，请刷新后再废弃")
    case_set.status = "cancelled"
    if task:
        task.status = "cancelled"
        task.finished_at = utcnow()
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_cancel",
            target_type="case_set",
            target_id=case_set.id,
            detail={"name": case_set.name, "reason": body.reason},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(case_set)
    return case_set


@router.post("/{set_id}/map")
def map_cases(
    set_id: str,
    body: CaseMapIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """历史评测数据集映射已停用；用例审核后仅在用例域入库。"""
    raise AppError(ErrorCode.VALIDATION, "评测数据集映射已停用，请在用例页审核入库")


@router.post("/{set_id}/ai-fill")
def ai_fill_cases(
    set_id: str,
    body: CaseAiFillIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按 Agent 协议档补全指定用例缺失字段；返回 {id, ...补全字段} 候选，不直接落库。"""
    _ = user
    case_set, _task = _lock_editable_case_set(db, set_id)
    # 补全只生成候选，调用供应商期间释放行锁，避免阻塞取消和超时扫描。
    db.commit()
    cases = (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == set_id, CaseItem.id.in_(body.case_ids))
        .all()
    )
    if len(cases) != len(set(body.case_ids)):
        raise AppError(ErrorCode.VALIDATION, "部分用例不存在")

    payload = json.dumps(
        [_case_to_item(case) for case in sorted(cases, key=lambda c: c.sort_order)],
        ensure_ascii=False,
    )
    fields_hint = (
        "、".join(body.fields) if body.fields else "name/expected/precondition/steps/module/submodule/feature_point/test_type/priority"
    )
    instruction = body.instruction or "请结合用例已有内容，补全缺失字段"
    system = (
        "你是资深测试设计专家，负责补全测试用例。只输出一个 JSON 数组，"
        "每条必须含 id 与补全后的字段，保持字段名与输入一致，不要输出解释文字或代码围栏。"
    )
    user_prompt = (
        f"{instruction}。请补全以下用例中缺失的 {fields_hint} 字段，"
        f"已有内容保持不变，只输出 JSON 数组（每条含 id）。\n\n用例：\n{payload}"
    )
    result = call_agent_model(db, system, user_prompt, temperature=0.2, max_tokens=8192)
    items = extract_json_array(result.text)
    # 模型仅能补全请求范围内的正文/扩展列，不能替换身份、流程状态或已有内容。
    by_id = {case.id: _case_to_item(case) for case in cases}
    allowed_fields = set(CaseIn.model_fields) - {"id"}
    allowed_fields.update(
        str(column["key"]) for column in case_set.column_schema or []
        if isinstance(column, dict) and column.get("key") and column["key"] not in _RESERVED_EXTRA_KEYS
    )
    if body.fields is not None:
        allowed_fields.intersection_update(body.fields)
    filled = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        case_id = item["id"]
        if case_id not in by_id or case_id in seen_ids:
            continue
        updates = {
            key: value for key, value in item.items()
            if key in allowed_fields and not by_id[case_id].get(key)
        }
        try:
            CaseIn.model_validate({**by_id[case_id], **updates})
        except ValidationError:
            continue
        if updates:
            filled.append({"id": case_id, **updates})
            seen_ids.add(case_id)
    _lock_editable_case_set(db, set_id)
    if not filled:
        raise AppError(ErrorCode.UPSTREAM, "模型未返回可识别的补全结果")
    return {"items": filled}


async def _read_import_file(file: UploadFile) -> tuple[list[dict[str, Any]], str, int]:
    """读取并解析 Excel，写库前完成格式与规模校验。"""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xlsm")):
        raise AppError(ErrorCode.VALIDATION, "仅支持 .xlsx，请将 .xls 另存为 .xlsx 后再导入")
    content = await file.read()
    if not content:
        raise AppError(ErrorCode.VALIDATION, "上传文件为空")
    if len(content) > IMPORT_MAX_BYTES:
        raise AppError(ErrorCode.VALIDATION, "文件大小超过 10MB 上限")

    return parse_cases_xlsx(content)


def _write_imported_cases(
    db: Session, case_set: CaseSet, parsed: list[dict[str, Any]],
    fmt: str, skipped: int, mode: str, filename: str | None,
    request: FastApiRequest, user: User,
) -> int:
    """在调用方事务中写入导入行与审计；创建新集时由调用方一并提交。"""
    extra_keys: list[str] = []
    for item in parsed:
        extra_keys.extend((item.get("extras") or {}).keys())
    _merge_column_schema(case_set, extra_keys)

    existing = {
        case.id: case
        for case in db.query(CaseItem).filter(CaseItem.case_set_id == case_set.id).all()
    }
    if mode == "replace":
        db.query(CaseItem).filter(CaseItem.case_set_id == case_set.id).delete(synchronize_session=False)
        db.flush()
        existing = {}

    sort_base = 0 if mode == "replace" else len(existing)
    imported = 0
    for offset, item in enumerate(parsed):
        try:
            case_in = _parsed_row_to_case_in(item)
        except ValidationError as exc:
            raise AppError(ErrorCode.VALIDATION, f"第 {offset + 1} 条用例字段不合法") from exc
        source_id = case_in.id
        target = existing.get(source_id) if source_id else None
        if case_in.id and target is None:
            clash = db.query(CaseItem).filter(CaseItem.id == case_in.id).first()
            if clash:
                # 其他用例集占用该编号时改为新 id，避免跨集串行
                case_in.id = None
        saved = _upsert_case(db, case_set, case_in, target, sort_base + offset)
        # 包含尚未 flush 的新行；跨集编号重建后也按原编号复用本批副本。
        if source_id:
            existing[source_id] = saved
        imported += 1
    db.flush()
    _refresh_generated_count(db, case_set)
    case_set.checks = _selfcheck_items([_case_to_item(case) for case in _list_cases(db, case_set)])
    case_set.revision += 1
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_import",
            target_type="case_set",
            target_id=case_set.id,
            detail={
                "name": case_set.name,
                "filename": filename,
                "mode": mode,
                "format": fmt,
                "imported_count": imported,
                "skipped_count": skipped,
            },
            ip=client_ip(request),
        )
    )
    return imported


def _import_result(case_set: CaseSet, fmt: str, mode: str, imported: int, skipped: int) -> dict[str, Any]:
    """返回新建导入和原有集导入共用的响应字段。"""
    return {
        "ok": True,
        "format": fmt,
        "mode": mode,
        "imported_count": imported,
        "skipped_count": skipped,
        "generated_count": case_set.generated_count,
        "checks": case_set.checks,
        "revision": case_set.revision,
    }


@router.post("/{set_id}/import")
async def import_case_set(
    set_id: str,
    request: FastApiRequest,
    file: UploadFile = File(...),
    mode: str = Query("append"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    expected_revision: int = Query(..., ge=0),
):
    """从 Excel 导入用例行。mode=append 追加（同 id 则更新），replace 先清空再写入。"""
    case_set = _get_case_set_or_404(db, set_id)
    _assert_editable(case_set)
    if mode not in {"append", "replace"}:
        raise AppError(ErrorCode.VALIDATION, "mode 仅支持 append 或 replace")
    parsed, fmt, skipped = await _read_import_file(file)
    # 上传和解析期间不占业务行锁；写入前再获取最新状态并校验确认期限。
    case_set, _task = _lock_editable_case_set(db, set_id)
    if case_set.revision != expected_revision:
        raise AppError(ErrorCode.CONCURRENCY, "用例已由其他操作更新，请刷新后再导入")
    imported = _write_imported_cases(
        db, case_set, parsed, fmt, skipped, mode, file.filename, request, user,
    )
    db.commit()
    db.refresh(case_set)
    return _import_result(case_set, fmt, mode, imported, skipped)


@router.get("/{set_id}/export")
def export_case_set(
    set_id: str,
    request: FastApiRequest,
    fmt: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出用例集为 xlsx 或 xmind 文件流；generated/confirmed 均可导出，fmt 必填。"""
    case_set = _get_case_set_or_404(db, set_id)
    cases = _list_cases(db, case_set)
    if fmt == "xlsx":
        content, media_type, suffix = _build_xlsx(case_set, cases), _XLSX_MEDIA_TYPE, ".xlsx"
    elif fmt == "xmind":
        content, media_type, suffix = _build_xmind(case_set, cases), _XMIND_MEDIA_TYPE, ".xmind"
    else:
        raise AppError(ErrorCode.VALIDATION, "fmt 仅支持 xlsx 或 xmind")
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_export",
            target_type="case_set",
            target_id=case_set.id,
            detail={"name": case_set.name, "fmt": fmt, "case_count": len(cases)},
            ip=client_ip(request),
        )
    )
    db.commit()
    # 中文文件名按 RFC 5987 编码，避免 Content-Disposition 乱码
    filename = quote(f"{case_set.name}{suffix}")
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@folders_router.get("")
def list_case_folders(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """按排序号返回全部用例目录节点，前端自行组装树。"""
    rows = (
        db.query(CaseFolder)
        .order_by(CaseFolder.sort_order.asc(), CaseFolder.created_at.asc())
        .all()
    )
    return {"items": [FolderOut.model_validate(row) for row in rows], "total": len(rows)}


@folders_router.post("", response_model=FolderOut, status_code=201)
def create_case_folder(
    body: FolderIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建用例目录节点；parent_id 缺省表示根目录。"""
    if not body.name:
        raise AppError(ErrorCode.VALIDATION, "目录名称不能为空")
    if body.parent_id:
        assert_folder_exists(db, CaseFolder, body.parent_id)
    folder = CaseFolder(
        name=body.name,
        parent_id=body.parent_id,
        sort_order=body.sort_order or 0,
    )
    db.add(folder)
    db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_folder_create",
            target_type="case_folder",
            target_id=folder.id,
            detail={"name": folder.name},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(folder)
    return folder


@folders_router.put("/{folder_id}", response_model=FolderOut)
def update_case_folder(
    folder_id: str,
    body: FolderIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按提供的字段更新用例目录；移动时校验父目录存在且不构成环。"""
    folder = get_folder_or_404(db, CaseFolder, folder_id)
    values = body.model_dump(exclude_unset=True)
    if "parent_id" in values:
        parent_id = values.pop("parent_id")
        if parent_id is not None:
            assert_folder_exists(db, CaseFolder, parent_id)
            # 沿祖先链向上检查，防止把目录挂到自身或后代节点下形成环
            current = parent_id
            while current:
                if current == folder.id:
                    raise AppError(ErrorCode.VALIDATION, "不能把目录移动到自身或其子目录下")
                node = db.query(CaseFolder).filter(CaseFolder.id == current).first()
                current = node.parent_id if node else None
        folder.parent_id = parent_id
    for field, value in values.items():
        if value is not None:
            setattr(folder, field, value)
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_folder_update",
            target_type="case_folder",
            target_id=folder.id,
            detail={"name": folder.name, "fields": sorted(body.model_fields_set)},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(folder)
    return folder


@folders_router.delete("/{folder_id}")
def delete_case_folder(
    folder_id: str,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除空目录；仍含用例集或子目录时返回 VALIDATION。"""
    folder = get_folder_or_404(db, CaseFolder, folder_id)
    if db.query(CaseFolder).filter(CaseFolder.parent_id == folder.id).first():
        raise AppError(ErrorCode.VALIDATION, "目录下仍有子目录，无法删除")
    if db.query(CaseSet).filter(CaseSet.folder_id == folder.id).first():
        raise AppError(ErrorCode.VALIDATION, "目录下仍有用例集，无法删除")
    db.delete(folder)
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_folder_delete",
            target_type="case_folder",
            target_id=folder_id,
            detail={"name": folder.name},
            ip=client_ip(request),
        )
    )
    db.commit()
    return {"ok": True}
