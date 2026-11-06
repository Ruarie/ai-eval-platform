"""用例生成 Skill 真实执行器（M2 W8 / PRD 5.4.1）。

执行流程：
1. 读任务快照 ``case_source``（file_id 或 text）：文本类（PRD/OpenAPI/Markdown）
   经 Agent 协议档 LLM 按六策略配比生成；Excel 由 openpyxl 抽取文本行后同路生成；
2. 规模口径：目标中等 45 条，硬上限 80（PRD：简单/中/复杂 20/45/80），
   超上限 → failed 提示拆分，禁止灌水；
3. 自检红字（P0）：无核心正向、缺约束反向 → 写入 ``case_sets.checks``；
4. 落库用例集（generated）与用例行，任务转 ``awaiting_case_confirm``，
   ``expires_at = now + 72h``；确认/废弃由 api 侧 confirm/cancel 联动任务终态，
   72h 未确认由主循环扫描器取消；
5. 5 分钟总预算：LLM 调用超时 280s，超时 → failed(TIMEOUT)。

prompt 与解析口径镜像 ``api/app/routers/cases.py`` 的 ai-generate（中文策略名、
JSON 数组输出、配比校正），修改任一侧必须同步另一侧。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from pathlib import Path

from shared.casegen import (
    MAX_COUNT,
    MODEL_RESERVED_KEYS,
    SOURCE_MAX_CHARS,
    TARGET_COUNT,
    build_prompts,
    clip_source,
    dedupe_cases,
    generation_token_budget,
    parse_cases_with_stats,
    rebalance_with_stats,
    split_sections,
    selfcheck,
    validate_strategy_weights,
)
from sqlalchemy.orm import Session

from .db import SessionLocal
from .events import push_ws
from .models import (
    CaseItem,
    CaseSet,
    ProtocolProfile,
    Setting,
    StoredFile,
    Task,
    TaskEvent,
    utcnow,
)
from .profile_env import profile_connection, read_profile_env
from .protocol import ProtocolCallError, call_protocol
from .task_state import claim_running_task_for_terminal_write, is_cancelled

logger = logging.getLogger("worker.testcase")

# ─── 超时与确认窗口口径（PRD 5.4.1） ───
LLM_TIMEOUT_S = 280.0  # 单次 LLM 调用超时；总预算 5 分钟留 20s 落库余量
CONFIRM_WINDOW_H = 72  # 确认窗口：72h 未确认由扫描器取消
# 输出被 max_tokens 截断时的重试上限，与 api 侧 llm_client 同口径。
TRUNCATION_RETRY_CEILING = 32768


def _fail(db: Session, task: Task, code: str, message: str) -> None:
    """任务失败收尾：落终态、写错误时间线并推送 WS error 事件。"""
    task_id = task.id
    task = claim_running_task_for_terminal_write(db, task_id)
    if not task:
        logger.info("testcase task %s skipped failure because it is no longer running", task_id)
        return
    task.status = "failed"
    task.finished_at = utcnow()
    task.result = {**(task.result or {}), "error_code": code, "error_message": message}
    db.add(TaskEvent(task_id=task.id, event="error", level="error", message=message, payload={"code": code}))
    db.commit()
    push_ws(task.session_id, "error", {"code": code, "message": message}, task_id=task.id)
    logger.warning("testcase task %s failed (%s): %s", task.id, code, message)


def _read_source(db: Session, case_source: dict, user_id: str) -> str:
    """读取来源文档内容：file_id 走文件卷，text 直取；Excel 抽取文本行。

    口径镜像 api 侧 ``cases.py`` 的来源文档读取（xlsx 逐行拼接、其余 UTF-8 容错读）。
    """
    text = (case_source.get("text") or "").strip()
    if text:
        # 不在读取层截断：上层需要知道「是否发生过截断」才能提示用户拆分需求。
        return text
    file_id = case_source.get("file_id")
    if not file_id:
        raise ValueError("case_source 缺少 file_id 或 text")
    stored = db.query(StoredFile).filter(StoredFile.id == file_id).first()
    # 排队后权限可能变化，消费前必须复验；知道文件 ID 不构成读取授权。
    if not stored or stored.uploaded_by != user_id:
        raise FileNotFoundError("来源文件不存在或已删除")
    path = Path(stored.storage_path)
    if not path.exists():
        raise FileNotFoundError("来源文件已从磁盘移除")
    suffix = Path(stored.filename or "").suffix.lower()
    if suffix in {".xlsx", ".xlsm"} or stored.kind in {"xlsx", "xlsm"}:
        from openpyxl import load_workbook

        # 文件卷以 UUID 命名，传入二进制流避免 openpyxl 按存储路径误判类型。
        with path.open("rb") as stream:
            workbook = load_workbook(stream, read_only=True, data_only=True)
            try:
                lines = []
                for sheet in workbook.worksheets:
                    for row in sheet.iter_rows(values_only=True):
                        line = " ".join(str(cell) for cell in row if cell is not None)
                        if line.strip():
                            lines.append(line)
            finally:
                workbook.close()
        return "\n".join(lines)
    return path.read_bytes().decode("utf-8", errors="ignore")


def _to_case_items(case_set_id: str, cases: list[dict]) -> list[CaseItem]:
    """把模型输出的用例字典转换为待落库的 CaseItem 行（固定字段 + 透传扩展键）。"""
    fixed = {
        "strategy", "priority", "module", "submodule", "feature_point",
        "name", "precondition", "steps", "expected", "test_type",
    }
    # 与 API 保存口径一致：模型只能提供业务扩展列，不能覆盖数据库身份和状态。
    items: list[CaseItem] = []
    for index, case in enumerate(cases):
        extras = {k: v for k, v in case.items() if k not in fixed | MODEL_RESERVED_KEYS}
        name = str(case.get("name") or "")
        expected = str(case.get("expected") or "")
        items.append(
            CaseItem(
                case_set_id=case_set_id,
                strategy=str(case.get("strategy") or "正向"),
                priority=str(case.get("priority") or "FHX"),
                module=str(case.get("module") or ""),
                submodule=str(case.get("submodule") or ""),
                feature_point=str(case.get("feature_point") or ""),
                name=name,
                precondition=str(case.get("precondition") or ""),
                steps=str(case.get("steps") or ""),
                expected=expected,
                test_type=str(case.get("test_type") or ""),
                extras=extras,
                pending_complete=not name.strip() or not expected.strip(),
                sort_order=index,
            )
        )
    return items


def _pick_generation_profile(db: Session, profile_id: str | None):
    """选生成用例用的协议档；返回 ``(profile, 是否发生了切换)``。

    用例生成是"长结构化 JSON 输出"，effort 型思考模板（``reasoning_effort`` 只是
    建议值、思考量由模型决定）会把 max_tokens 全烧在思考上、正文为空——实测 hy4
    单模块 8K/16K 预算均输出 0 字符。因此优先选非 effort 模板的档位。
    """
    preferred = (
        db.query(ProtocolProfile).filter(ProtocolProfile.id == profile_id).first()
        if profile_id
        else None
    )

    def risky(item: ProtocolProfile | None) -> bool:
        return bool(item) and "effort" in str(getattr(item, "reasoning_template_id", "") or "").lower()

    if preferred and not risky(preferred):
        return preferred, False
    safe = (
        db.query(ProtocolProfile)
        .filter(~ProtocolProfile.reasoning_template_id.ilike("%effort%"))
        .order_by(ProtocolProfile.created_at)
        .first()
    )
    if safe:
        return safe, True
    return preferred, False


def run_testcase(task_id: str) -> None:
    """testcase 任务真实执行入口：生成用例集并转入 awaiting_case_confirm。"""
    db = SessionLocal()
    task: Task | None = None
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error("testcase task %s not found, skip execution", task_id)
            return
        config = task.config or {}
        case_source = config.get("case_source") or {}
        if not case_source:
            _fail(db, task, "VALIDATION", "任务快照缺少 case_source，无法生成用例")
            return

        # ─── 读取来源文档 ───
        try:
            source_text = _read_source(db, case_source, task.created_by)
        except FileNotFoundError as exc:
            _fail(db, task, "VALIDATION", str(exc))
            return
        except ValueError as exc:
            _fail(db, task, "VALIDATION", str(exc))
            return
        except Exception as exc:
            _fail(db, task, "VALIDATION", "来源文档内容不可读，请改用文本输入")
            logger.exception("testcase task %s source read error: %s", task_id, exc)
            return
        if not source_text.strip():
            _fail(db, task, "VALIDATION", "来源文档内容为空，无法生成用例")
            return
        source_text, source_truncated = clip_source(source_text)
        if source_truncated:
            # 截断必须留痕：否则用户会以为整份需求都参与了生成。
            db.add(TaskEvent(
                task_id=task.id, event="progress",
                message=(
                    f"来源文档超过 {SOURCE_MAX_CHARS} 字符，仅前 {SOURCE_MAX_CHARS} 字符参与生成；"
                    "建议拆分需求后分别生成，避免后半段未被覆盖"
                ),
            ))
            db.commit()

        max_count = config.get("max_count", TARGET_COUNT)
        try:
            if type(max_count) is not int or not 1 <= max_count <= MAX_COUNT:
                raise ValueError("max_count 须为 1–80 的整数")
            weights = validate_strategy_weights(config.get("strategy_weights"))
        except ValueError as exc:
            _fail(db, task, "VALIDATION", f"用例生成参数无效：{exc}")
            return

        # ─── 解析 Agent 协议档并调用 LLM 生成（六策略配比） ───
        row = db.query(Setting).filter(Setting.key == "agent_profile_id").first()
        profile_id = row.value if row else None
        profile, profile_switched = _pick_generation_profile(db, profile_id)
        if profile_switched:
            db.add(TaskEvent(
                task_id=task.id, event="progress",
                message=(
                    f"默认 Agent 协议档使用「思考强度」型模板（思考量不可控，容易把输出预算"
                    f"全用于思考导致正文为空），本次生成改用「{profile.name}」"
                ),
            ))
            db.commit()
        if not profile:
            _fail(db, task, "VALIDATION", "未配置 Agent 协议档或未填写 API Key，无法生成用例")
            return
        base_url, model, api_key = profile_connection(profile, allow_global_alias=True)
        if not api_key:
            _fail(db, task, "VALIDATION", "未配置 Agent 协议档或未填写 API Key，无法生成用例")
            return

        db.add(TaskEvent(task_id=task.id, event="progress", message="正在按六策略生成用例"))
        db.commit()
        push_ws(task.session_id, "progress", {"percent": 20, "done": 0, "total": 1, "message": "正在生成用例"}, task_id=task.id)

        # P4-2 取消传播：发起 LLM 调用前检查任务是否已取消（避免烧 token）
        if is_cancelled(db, task.id):
            logger.info("testcase task %s cancelled before LLM call, skip", task_id)
            return

        # ─── 分批生成：按需求分节，每次只产 6–10 条 ───
        # 单次直出 40+ 条时，推理模型会把 max_tokens 全花在思考上、正文为空
        # （实测 hy4 单模块 16K 预算输出 0 字符）。分批后每批输出小、思考可控，
        # 也避免撞上单次输出上限。
        sections = split_sections(source_text)
        logger.info(
            "testcase task %s split: sections=%d chars=%d titles=%s",
            task_id, len(sections), len(source_text),
            [item["title"][:16] for item in sections][:6],
        )
        if len(sections) <= 1:
            batches: list[tuple[str, str, int]] = [("全文", source_text, max_count)]
        else:
            per_section = min(10, max(6, -(-max_count // len(sections))))
            batches = [(item["title"], item["text"], per_section) for item in sections]

        def invoke(system_prompt: str, user_prompt: str, budget: int):
            return call_protocol(
                protocol=profile.protocol,
                base_url=base_url,
                full_url=read_profile_env(profile.id).full_url,
                model=model,
                api_key=api_key,
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt,
                temperature=0.3,
                max_tokens=budget,
                anthropic_version=profile.anthropic_version,
                timeout_s=LLM_TIMEOUT_S,
            )

        collected: list[dict] = []
        failed_batches: list[str] = []
        truncated_batches = 0
        total_batches = len(batches)
        for index, (title, body, per_batch) in enumerate(batches, start=1):
            if is_cancelled(db, task.id):
                logger.info("testcase task %s cancelled during batched generation", task_id)
                return
            system, user = build_prompts(body, per_batch, weights=weights)
            budget = generation_token_budget(per_batch)
            try:
                result = invoke(system, user, budget)
                # 单批被截断时抬预算重试一次，仍截断则记为该批失败。
                if (
                    getattr(result, "finish_reason", None) == "length"
                    and budget < TRUNCATION_RETRY_CEILING
                ):
                    budget = min(TRUNCATION_RETRY_CEILING, budget * 2)
                    result = invoke(system, user, budget)
            except ProtocolCallError as exc:
                failed_batches.append(f"{title}({exc.code})")
                logger.warning("testcase batch %s failed: %s", title, exc.code)
                continue
            batch_text = (result.text or "").strip()
            if getattr(result, "finish_reason", None) == "length" or not batch_text:
                if getattr(result, "finish_reason", None) == "length":
                    truncated_batches += 1
                failed_batches.append(title)
                logger.warning(
                    "testcase batch %s empty_or_truncated finish=%s",
                    title, getattr(result, "finish_reason", None),
                )
                continue
            try:
                part, part_stats = parse_cases_with_stats(batch_text)
            except (ValueError, json.JSONDecodeError):
                failed_batches.append(title)
                logger.warning("testcase batch %s unparsable", title)
                continue
            if not part:
                # 模型返回了合法 JSON 但内容全被丢弃：按失败计，避免"成功 9 批却只出 8 条"。
                failed_batches.append(f"{title}(解析后为空 {part_stats})")
                logger.warning("testcase batch %s parsed empty stats=%s", title, part_stats)
                continue
            collected.extend(part)
            logger.info("testcase batch %s -> %d cases", title, len(part))
            push_ws(
                task.session_id,
                "progress",
                {
                    "percent": 20 + int(60 * index / total_batches),
                    "done": len(collected),
                    "total": max_count,
                    "message": f"已生成 {len(collected)} 条（{index}/{total_batches} 批）",
                },
                task_id=task.id,
            )

        if not collected:
            # 全部批次都因长度上限失败时，给可操作的预算错误而不是笼统的上游失败。
            if truncated_batches == total_batches:
                _fail(
                    db, task, "BUDGET_EXCEEDED",
                    f"模型输出被长度上限截断（max_tokens={budget}），"
                    "请减少生成条数或拆分需求后重试",
                )
            else:
                _fail(
                    db, task, "UPSTREAM",
                    f"模型未产出可用用例（{len(failed_batches)}/{total_batches} 批失败），"
                    "可减少条数或拆分需求后重试",
                )
            return
        if failed_batches:
            db.add(TaskEvent(
                task_id=task.id, event="progress",
                message=(
                    f"分批生成：{total_batches - len(failed_batches)}/{total_batches} 批成功；"
                    f"失败批次：{'、'.join(failed_batches[:5])}"
                ),
            ))
            db.commit()
        cases = collected
        logger.info(
            "testcase task %s batched total=%d failed=%d truncated=%d",
            task_id, len(collected), len(failed_batches), truncated_batches,
        )
        parse_stats = {"dropped_missing_name": 0, "dropped_non_object": 0}

        # ─── 去重与规模闸门 ───
        # 注意：分批生成时每批已经解析并累计到 collected，这里**不能**再解析
        # 最后一次模型响应，否则会把累计结果覆盖成最后一批的 8 条。
        # 先去重再判上限与裁剪：重复项属于灌水，不应让整单失败，也不该按配额
        # 挤掉真正不同的用例。
        cases, dropped_duplicate = dedupe_cases(cases)
        if len(cases) > MAX_COUNT:
            _fail(
                db, task, "VALIDATION",
                f"生成 {len(cases)} 条超过上限 {MAX_COUNT} 条，请拆分需求文档后重新发起",
            )
            return
        cases, dropped = rebalance_with_stats(cases, max_count, weights=weights)
        if not cases:
            _fail(db, task, "UPSTREAM", "模型输出经配比校正后无有效用例")
            return
        if (dropped_duplicate or dropped["dropped_unknown_strategy"]
                or dropped["dropped_over_quota"] or parse_stats["dropped_missing_name"]):
            # 去重与裁剪都是静默行为，必须让用户知道实际保留数与丢弃原因。
            parts = []
            if dropped_duplicate:
                parts.append(f"同名、同内容或近似功能点去重 {dropped_duplicate} 条")
            if parse_stats["dropped_missing_name"]:
                parts.append(f"缺少用例名称丢弃 {parse_stats['dropped_missing_name']} 条")
            if dropped["dropped_unknown_strategy"]:
                parts.append(f"策略不匹配丢弃 {dropped['dropped_unknown_strategy']} 条")
            if dropped["dropped_over_quota"]:
                parts.append(f"超出配额丢弃 {dropped['dropped_over_quota']} 条")
            db.add(TaskEvent(
                task_id=task.id, event="progress",
                message="按所选策略整理：" + "；".join(parts),
            ))
            db.commit()

        # ─── 落库用例集 + 自检红字 + 任务转 awaiting_case_confirm ───
        # 模型调用期间可能收到取消；落库前重新锁定任务，不能覆盖 cancelled 终态。
        task = claim_running_task_for_terminal_write(db, task.id)
        if not task:
            logger.info("testcase task %s skipped persistence because it is no longer running", task_id)
            return
        expires_at = utcnow() + timedelta(hours=CONFIRM_WINDOW_H)
        case_set = CaseSet(
            task_id=task.id,
            created_by=task.created_by,
            name=f"AI 生成用例集 · 任务 {task.id[:8]}",
            status="generated",
            generated_count=len(cases),
            confirmed_count=0,
            checks=selfcheck(cases, weights=weights),
            expires_at=expires_at,
        )
        db.add(case_set)
        db.flush()
        db.add_all(_to_case_items(case_set.id, cases))

        task.status = "awaiting_case_confirm"
        task.progress = {"percent": 100, "done": len(cases), "total": len(cases), "message": "用例已生成，等待确认入库"}
        task.result = {"case_set_id": case_set.id, "generated_count": len(cases)}
        db.add(
            TaskEvent(
                task_id=task.id,
                event="awaiting_case_confirm",
                message=f"已生成 {len(cases)} 条用例，等待确认入库（72h 内有效）",
                payload={"case_set_id": case_set.id},
            )
        )
        db.commit()

        push_ws(
            task.session_id,
            "progress",
            {"percent": 100, "done": len(cases), "total": len(cases), "message": "用例已生成，等待确认入库"},
            task_id=task.id,
        )
        push_ws(
            task.session_id,
            "thought",
            {"text": f"已生成 {len(cases)} 条用例（含自检结果），请到「用例」页确认入库或拒绝；72 小时内未确认将自动取消。"},
            task_id=task.id,
        )
        logger.info("testcase task %s awaiting confirm (case_set=%s, %d cases)", task_id, case_set.id, len(cases))
    except Exception as exc:
        db.rollback()
        logger.exception("testcase task %s execution error", task_id)
        if task is not None:
            _fail(db, task, "INTERNAL", f"执行失败({type(exc).__name__})，详情见服务端日志")
    finally:
        db.close()
