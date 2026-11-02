"""知识库与黄金 QA 工作台路由（API V1.3 §3.9）。

- ``/api/kb``：知识库 CRUD、文档上传/列表/删除、切块预览、检索 Playground；
- ``/api/kb/{id}/gold-qa``：黄金 QA 上传（JSONL/CSV/JSON）与列表。

写操作均落 AuditLog；检索经 ``shared.kb`` 完成（LightRAG 优先，本地关键词兜底）。
"""

import asyncio
import csv
import io
import json
import logging
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi import Request as FastApiRequest
from sqlalchemy.orm import Session

from shared.kb import (
    chunk_text,
    compute_metrics,
    delete_documents,
    document_statuses,
    index_document,
    retrieve,
)

from ..config import settings
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import (
    AuditLog,
    GoldQa,
    GoldQaItem,
    KbDocument,
    KnowledgeBase,
    User,
    uuid_str,
)
from ..schemas import (
    GoldQaOut,
    KbChunkOut,
    KbCreate,
    KbDocOut,
    KbOut,
    KbQueryIn,
    KbQueryItemOut,
    KbQueryOut,
    KbUpdate,
)
from ._common import client_ip

logger = logging.getLogger("ai-eval.api.kb")

router = APIRouter(prefix="/api/kb", tags=["kb"])

MAX_DOC_BYTES = 20 * 1024 * 1024
MAX_GOLD_QA_ROWS = 10_000
GOLD_QA_COLUMNS = {"question", "reference", "expected_doc_ids"}


def _get_kb_or_404(db: Session, kb_id: str) -> KnowledgeBase:
    """读取知识库或抛出 NOT_FOUND。"""
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise AppError(ErrorCode.NOT_FOUND, "知识库不存在")
    return kb


def _get_doc_or_404(db: Session, kb_id: str, doc_id: str) -> KbDocument:
    """读取属于指定知识库的文档或抛出 NOT_FOUND。"""
    doc = (
        db.query(KbDocument)
        .filter(KbDocument.kb_id == kb_id, KbDocument.id == doc_id)
        .first()
    )
    if not doc:
        raise AppError(ErrorCode.NOT_FOUND, "文档不存在")
    return doc


def _owner_name(db: Session, created_by: str | None) -> str:
    """解析创建人显示名；成员已删除或未记录时返回空串。"""
    if not created_by:
        return ""
    user = db.query(User).filter(User.id == created_by).first()
    if not user:
        return ""
    return user.display_name or user.username or ""


def _format_size(size: int) -> str:
    """把字节数格式化为展示串（对齐前端 mock 的 "2.4 MB" 风格）。"""
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def _kb_out(db: Session, kb: KnowledgeBase) -> KbOut:
    """构造知识库响应：doc_count 实时统计，external_chat 返回 null。"""
    doc_count = None
    if kb.kind == "lightrag":
        doc_count = db.query(KbDocument).filter(KbDocument.kb_id == kb.id).count()
    return KbOut(
        id=kb.id,
        name=kb.name,
        kind=kb.kind,
        doc_count=doc_count,
        is_core=kb.is_core,
        owner=_owner_name(db, kb.created_by),
        profile_id=kb.profile_id,
        capabilities={"projection": False, "rerank_compare": False},
        created_at=kb.created_at,
    )


def _gold_qa_out(db: Session, qa: GoldQa) -> GoldQaOut:
    """构造黄金 QA 响应。"""
    return GoldQaOut(
        id=qa.id,
        kb_id=qa.kb_id,
        name=qa.name,
        version=qa.version,
        row_count=qa.row_count,
        owner=_owner_name(db, qa.created_by),
        created_at=qa.created_at,
    )


def _set_core_exclusive(db: Session, kb_id: str) -> None:
    """把目标知识库置为核心库，同时清除其它知识库的核心标记。"""
    db.query(KnowledgeBase).filter(KnowledgeBase.is_core.is_(True)).update(
        {KnowledgeBase.is_core: False}
    )


# ─── 知识库 CRUD ────────────────────────────────────────────────────────


@router.get("")
def list_kb(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """按创建时间返回全部知识库。"""
    rows = db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.asc()).all()
    return {"items": [_kb_out(db, row) for row in rows], "total": len(rows)}


@router.post("", response_model=KbOut, status_code=201)
def create_kb(
    body: KbCreate,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """创建知识库；kind 仅允许 lightrag / external_chat。"""
    if body.kind not in {"lightrag", "external_chat"}:
        raise AppError(ErrorCode.VALIDATION, "不支持的 knowledge base 类型")
    kb = KnowledgeBase(
        name=body.name.strip(),
        kind=body.kind,
        profile_id=body.profile_id,
        created_by=user.id,
    )
    db.add(kb)
    db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="kb_create",
            target_type="knowledge_base",
            target_id=kb.id,
            detail={"name": kb.name, "kind": kb.kind},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(kb)
    return _kb_out(db, kb)


@router.get("/{kb_id}", response_model=KbOut)
def get_kb(
    kb_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """返回单个知识库。"""
    return _kb_out(db, _get_kb_or_404(db, kb_id))


@router.put("/{kb_id}", response_model=KbOut)
def update_kb(
    kb_id: str,
    body: KbUpdate,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """更新知识库；is_core=true 时清除其它知识库的核心标记。"""
    kb = _get_kb_or_404(db, kb_id)
    values = body.model_dump(exclude_unset=True)
    if values.get("is_core"):
        _set_core_exclusive(db, kb.id)
    for field, value in values.items():
        if value is not None:
            setattr(kb, field, value)
    db.add(
        AuditLog(
            user_id=user.id,
            action="kb_update",
            target_type="knowledge_base",
            target_id=kb.id,
            detail={"name": kb.name, "fields": sorted(body.model_fields_set)},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(kb)
    return _kb_out(db, kb)


@router.delete("/{kb_id}")
def delete_kb(
    kb_id: str,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除知识库及其文档（含磁盘文件、LightRAG 索引）与黄金 QA。"""
    kb = _get_kb_or_404(db, kb_id)
    docs = db.query(KbDocument).filter(KbDocument.kb_id == kb.id).all()

    # 先清引擎索引：已建索引的文档删除失败即中止，避免留下无法再定位的脏召回。
    indexed = [doc.id for doc in docs if doc.status == "indexed"]
    others = [doc.id for doc in docs if doc.status != "indexed"]
    if not delete_documents(kb.id, indexed):
        raise AppError(ErrorCode.UPSTREAM, "LightRAG 索引删除失败，请稍后重试")
    # 建索引未完成/失败的文档在引擎里可能从未落库：删除失败不应阻断清理，
    # 否则引擎不可用时用户连空知识库都删不掉。
    if others and not delete_documents(kb.id, others):
        logger.warning(
            "知识库删除时未完成索引的文档未在引擎中清理 kb_id=%s 条数=%d", kb.id, len(others)
        )

    for doc in docs:
        if doc.storage_path:
            Path(doc.storage_path).unlink(missing_ok=True)
    db.query(KbDocument).filter(KbDocument.kb_id == kb.id).delete()

    qa_ids = [qa.id for qa in db.query(GoldQa).filter(GoldQa.kb_id == kb.id).all()]
    if qa_ids:
        db.query(GoldQaItem).filter(GoldQaItem.gold_qa_id.in_(qa_ids)).delete()
    db.query(GoldQa).filter(GoldQa.kb_id == kb.id).delete()

    db.add(
        AuditLog(
            user_id=user.id,
            action="kb_delete",
            target_type="knowledge_base",
            target_id=kb.id,
            detail={"name": kb.name},
            ip=client_ip(request),
        )
    )
    db.delete(kb)
    db.commit()


# ─── 文档：上传 / 列表 / 切块预览 / 删除 ────────────────────────────────


@router.post("/{kb_id}/documents", response_model=KbDocOut, status_code=201)
async def upload_doc(
    kb_id: str,
    request: FastApiRequest,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传文档：保存原始文件，并尽力提取 UTF-8/GBK 文本供切块与检索。"""
    _get_kb_or_404(db, kb_id)
    filename = Path(file.filename or "").name
    if not filename:
        raise AppError(ErrorCode.VALIDATION, "文件名不能为空")
    content = await file.read(MAX_DOC_BYTES + 1)
    if not content:
        raise AppError(ErrorCode.VALIDATION, "文件不能为空")
    if len(content) > MAX_DOC_BYTES:
        raise AppError(ErrorCode.VALIDATION, "单文件不能超过 20MB")

    doc_id = uuid_str()
    storage_dir = Path(settings.data_dir) / "kb" / kb_id
    storage_path = storage_dir / doc_id
    # 20MB 上限的落盘与解码都在线程池执行：同步 IO/CPU 留在事件循环里会阻塞
    # 同进程的所有 WS 与 REST 请求（上传高峰表现为整站卡顿）。
    await asyncio.to_thread(storage_dir.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(storage_path.write_bytes, content)
    text = await asyncio.to_thread(_decode_text, content)
    # 先记 indexing：真实索引由 LightRAG 适配服务异步完成，状态回读后再收敛。
    # 没有可用正文（二进制或解码失败）时直接 failed，不做乐观标记。
    doc_status = "indexing" if text else "failed"
    doc = KbDocument(
        id=doc_id,
        kb_id=kb_id,
        filename=filename,
        size=len(content),
        mime=file.content_type or "",
        text=text,
        status=doc_status,
        storage_path=str(storage_path),
        created_by=user.id,
    )
    db.add(doc)
    db.add(
        AuditLog(
            user_id=user.id,
            action="kb_doc_upload",
            target_type="kb_document",
            target_id=doc.id,
            detail={"filename": filename, "kb_id": kb_id},
            ip=client_ip(request),
        )
    )
    try:
        # flush 生成 created_at 等默认值；响应改用局部变量，避免 commit 后回表
        # 把整段正文（最大 20MB）重新拉回内存。
        db.flush()
        created_at = doc.created_at
        db.commit()
    except Exception:
        db.rollback()
        storage_path.unlink(missing_ok=True)
        raise

    if text:
        # 建索引是长耗时操作（LightRAG 需多次 LLM 抽取），必须离开事件循环执行；
        # 适配服务只受理入队，故此处等待时间与文档体积无关。
        result = await asyncio.to_thread(index_document, kb_id, doc_id, filename, text)
        doc_status = result["status"]
        try:
            # 只更新状态列：对象级赋值/refresh 会让该行整体重新加载。
            # synchronize_session=False 避免 update 反向同步会话对象时回表。
            db.query(KbDocument).filter(KbDocument.id == doc_id).update(
                {"status": doc_status}, synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("文档索引状态回写失败 doc_id=%s", doc_id)
    return KbDocOut(
        doc_id=doc_id,
        filename=filename,
        status=doc_status,
        size=_format_size(len(content)),
        created_at=created_at,
    )


def _decode_text(content: bytes) -> str:
    """尽力解码上传文档文本；均失败返回空串（文档状态置 failed）。"""
    for encoding in ("utf-8", "gbk", "utf-8-sig"):
        try:
            text = content.decode(encoding)
            if encoding != "utf-8-sig":
                return text
            return text.lstrip("\ufeff")
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


# 状态回读的短 TTL 缓存：前端在建索引期间每 5 秒轮询，多标签页/多用户同时
# 打开同一库时会重复打引擎。缓存值 None 表示「引擎未收录」，同样避免重复查询。
_STATUS_CACHE_TTL_S = 3.0
_status_cache: dict[str, tuple[float, str | None]] = {}


def _cached_statuses(doc_ids: list[str]) -> dict[str, str]:
    """带短 TTL 的批量状态回读；过期项顺带清理，避免长期运行无限增长。"""
    now = time.monotonic()
    for doc_id in [key for key, (ts, _) in _status_cache.items() if now - ts > _STATUS_CACHE_TTL_S]:
        _status_cache.pop(doc_id, None)
    missing = [doc_id for doc_id in doc_ids if doc_id not in _status_cache]
    if missing:
        live = document_statuses(missing)
        stamp = time.monotonic()
        for doc_id in missing:
            _status_cache[doc_id] = (stamp, live.get(doc_id))
    return {
        doc_id: status
        for doc_id in doc_ids
        if (status := _status_cache.get(doc_id, (0.0, None))[1]) is not None
    }


def _refresh_doc_statuses(db: Session, rows: list[KbDocument]) -> dict[str, str]:
    """回读仍在建索引的文档状态，返回需要落库的新状态（不在此处提交）。

    由调用方先用返回结果构造响应、再统一 UPDATE：``commit`` 会让会话对象过期，
    逐行回表会把正文列（最大 20MB）重新拉进内存。引擎不可用或回读失败时返回
    空集合，保留数据库原值，避免把「查不到」误写成 failed。
    """
    pending = [doc.id for doc in rows if doc.status == "indexing"]
    if not pending:
        return {}
    current = {doc.id: doc.status for doc in rows}
    live = _cached_statuses(pending)
    return {
        doc_id: status
        for doc_id, status in live.items()
        if status and current.get(doc_id) not in (None, status)
    }


@router.get("/{kb_id}/documents")
def list_docs(
    kb_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """返回知识库文档元信息（不含正文与切块）。"""
    _get_kb_or_404(db, kb_id)
    rows = (
        db.query(KbDocument)
        .filter(KbDocument.kb_id == kb_id)
        .order_by(KbDocument.created_at.asc())
        .all()
    )
    updates = _refresh_doc_statuses(db, rows)
    # 先按新状态构造响应，再做 UPDATE：commit 后对象过期，任何属性访问都会回表。
    items = [
        KbDocOut(
            doc_id=doc.id,
            filename=doc.filename,
            status=updates.get(doc.id, doc.status),
            size=_format_size(doc.size),
            created_at=doc.created_at,
        )
        for doc in rows
    ]
    if updates:
        try:
            for doc_id, status in updates.items():
                db.query(KbDocument).filter(KbDocument.id == doc_id).update(
                    {"status": status}, synchronize_session=False
                )
            db.commit()
        except Exception:
            db.rollback()
            logger.warning("文档索引状态同步失败（保留原状态） 条数=%d", len(updates))
    return {"items": items, "total": len(items)}


@router.get("/{kb_id}/documents/{doc_id}/chunks")
def get_doc_chunks(
    kb_id: str,
    doc_id: str,
    chunk_size: int = Query(default=512, ge=64, le=24_000),
    overlap: int = Query(default=64, ge=0, le=24_000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按请求切块参数返回服务端生成的切块预览。"""
    doc = _get_doc_or_404(db, kb_id, doc_id)
    chunks = chunk_text(doc.text, chunk_size=chunk_size, overlap=overlap, doc_id=doc.id)
    return {
        "items": [KbChunkOut(**chunk) for chunk in chunks],
        "total": len(chunks),
    }


@router.delete("/{kb_id}/documents/{doc_id}")
def delete_doc(
    kb_id: str,
    doc_id: str,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """删除文档记录、磁盘文件与 LightRAG 索引。

    先删引擎再删库内记录：引擎删除失败时抛错中止，避免留下「库里已删、
    向量库里仍在」的脏召回。引擎未配置或空库场景由适配服务按幂等处理。
    """
    doc = _get_doc_or_404(db, kb_id, doc_id)
    if not delete_documents(kb_id, [doc.id]):
        if doc.status == "indexed":
            raise AppError(ErrorCode.UPSTREAM, "LightRAG 索引删除失败，请稍后重试")
        # 从未建成索引的文档在引擎里可能没有记录：引擎不可用不该把用户锁死。
        logger.warning(
            "删除未完成索引的文档时引擎不可用，按无残留处理 doc_id=%s status=%s",
            doc.id,
            doc.status,
        )
    if doc.storage_path:
        Path(doc.storage_path).unlink(missing_ok=True)
    db.add(
        AuditLog(
            user_id=user.id,
            action="kb_doc_delete",
            target_type="kb_document",
            target_id=doc.id,
            detail={"filename": doc.filename, "kb_id": kb_id},
            ip=client_ip(request),
        )
    )
    db.delete(doc)
    db.commit()


# ─── 检索 Playground ────────────────────────────────────────────────────


@router.post("/{kb_id}/query", response_model=KbQueryOut)
def query_kb(
    kb_id: str,
    body: KbQueryIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """执行一次 Top-K 检索并计算指标。

    指标按「question 匹配的黄金 QA 行」计算：先精确后包含匹配该库下的
    黄金 QA 行，取期望文档与参考答案计算 hit_rate/mrr/recall/contain。
    """
    _get_kb_or_404(db, kb_id)
    items = retrieve(db, kb_id, body.query, mode=body.mode, k=body.k)

    expected, reference = _match_gold_qa(db, kb_id, body.query)
    expected_set = set(expected)
    metrics = compute_metrics(items, expected, reference)
    reranked = [item["chunk_id"] for item in items]
    out_items = [
        KbQueryItemOut(
            chunk_id=item["chunk_id"],
            doc_name=item.get("doc_name") or item.get("doc_id", ""),
            similarity=item.get("similarity"),
            text=item.get("text", ""),
            hit=bool(expected_set) and item.get("doc_id") in expected_set,
        )
        for item in items
    ]
    return KbQueryOut(
        query=body.query,
        mode=body.mode,
        items=out_items,
        reranked_ids=reranked,
        metrics=metrics,
    )


def _match_gold_qa(db: Session, kb_id: str, query: str) -> tuple[list[str], str]:
    """查找与该查询最匹配的黄金 QA 行（先精确后包含），返回期望文档与参考。"""
    qas = db.query(GoldQa).filter(GoldQa.kb_id == kb_id).all()
    qa_ids = [qa.id for qa in qas]
    if not qa_ids:
        return [], ""
    rows = db.query(GoldQaItem).filter(GoldQaItem.gold_qa_id.in_(qa_ids)).all()
    exact = [r for r in rows if r.question.strip() == query.strip()]
    target = exact[0] if exact else None
    if target is None:
        for r in rows:
            q = r.question.strip()
            if q and (q in query or query in q):
                target = r
                break
    if target is None:
        return [], ""
    return list(target.expected_doc_ids or []), target.reference or ""


# ─── 黄金 QA ─────────────────────────────────────────────────────────────


@router.get("/{kb_id}/gold-qa")
def list_gold_qa(
    kb_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """返回知识库下的黄金 QA 集元信息。"""
    _get_kb_or_404(db, kb_id)
    rows = db.query(GoldQa).filter(GoldQa.kb_id == kb_id).order_by(GoldQa.created_at.asc()).all()
    return {"items": [_gold_qa_out(db, row) for row in rows], "total": len(rows)}


@router.post("/{kb_id}/gold-qa", response_model=GoldQaOut, status_code=201)
async def upload_gold_qa(
    kb_id: str,
    request: FastApiRequest,
    file: UploadFile = File(...),
    name: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """上传黄金 QA（JSONL/CSV/JSON）；同名覆盖时 version 递增。"""
    _get_kb_or_404(db, kb_id)
    if not name.strip():
        raise AppError(ErrorCode.VALIDATION, "黄金 QA 名称不能为空")
    content = await file.read()
    if not content:
        raise AppError(ErrorCode.VALIDATION, "文件不能为空")
    rows = _parse_gold_qa(content, filename=file.filename or "")
    if not rows:
        raise AppError(ErrorCode.VALIDATION, "未解析到任何有效行")
    if len(rows) > MAX_GOLD_QA_ROWS:
        raise AppError(ErrorCode.VALIDATION, f"行数超过上限 {MAX_GOLD_QA_ROWS}")

    qa_name = name.strip()
    existing = (
        db.query(GoldQa)
        .filter(GoldQa.kb_id == kb_id, GoldQa.name == qa_name)
        .first()
    )
    if existing:
        version = existing.version + 1
        db.query(GoldQaItem).filter(GoldQaItem.gold_qa_id == existing.id).delete()
        qa = existing
    else:
        version = 1
        qa = GoldQa(kb_id=kb_id, name=qa_name, version=version, created_by=user.id)
        db.add(qa)
        db.flush()

    qa.version = version
    qa.row_count = len(rows)
    for row_no, row in enumerate(rows, start=1):
        db.add(
            GoldQaItem(
                gold_qa_id=qa.id,
                row_no=row_no,
                question=row.get("question", ""),
                reference=row.get("reference", ""),
                expected_doc_ids=row.get("expected_doc_ids", []),
            )
        )
    db.add(
        AuditLog(
            user_id=user.id,
            action="gold_qa_upload",
            target_type="gold_qa",
            target_id=qa.id,
            detail={"name": qa_name, "kb_id": kb_id, "version": version, "rows": len(rows)},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(qa)
    return _gold_qa_out(db, qa)


def _parse_gold_qa(content: bytes, filename: str = "") -> list[dict]:
    """解析黄金 QA 上传文件，统一为 [{question, reference, expected_doc_ids}]。

    支持 JSONL（每行一个对象）、CSV（表头 question/reference/expected_doc_ids）、
    JSON（对象数组）。expected_doc_ids 可为数组、JSON 字符串或分号分隔串。
    """
    text = content.decode("utf-8-sig", errors="replace")
    stripped = text.strip()
    if not stripped:
        return []
    suffix = Path(filename).suffix.lower()

    raw_rows: list[dict] = []
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            if not row:
                continue
            q = (row.get("question") or "").strip()
            if not q:
                continue
            raw_rows.append(
                {
                    "question": q,
                    "reference": (row.get("reference") or "").strip(),
                    "expected_doc_ids": _parse_expected(row.get("expected_doc_ids", "")),
                }
            )
    elif suffix == ".json" or stripped.lstrip().startswith("["):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AppError(ErrorCode.VALIDATION, "JSON 文件格式不正确") from exc
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                q = str(item.get("question") or "").strip()
                if not q:
                    continue
                raw_rows.append(
                    {
                        "question": q,
                        "reference": str(item.get("reference") or "").strip(),
                        "expected_doc_ids": _parse_expected(item.get("expected_doc_ids")),
                    }
                )
        elif isinstance(parsed, dict):
            q = str(parsed.get("question") or "").strip()
            if q:
                raw_rows.append(
                    {
                        "question": q,
                        "reference": str(parsed.get("reference") or "").strip(),
                        "expected_doc_ids": _parse_expected(parsed.get("expected_doc_ids")),
                    }
                )
    else:
        # JSONL：逐行解析，容忍空行与 # 注释
        for line in stripped.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(item, dict):
                continue
            q = str(item.get("question") or "").strip()
            if not q:
                continue
            raw_rows.append(
                {
                    "question": q,
                    "reference": str(item.get("reference") or "").strip(),
                    "expected_doc_ids": _parse_expected(item.get("expected_doc_ids")),
                }
            )
    return raw_rows[:MAX_GOLD_QA_ROWS]


def _parse_expected(value) -> list[str]:
    """把 expected_doc_ids 归一为字符串数组：支持数组 / JSON 串 / 分隔串 / Python 列表字面量。"""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except json.JSONDecodeError:
            pass
        # CSV 单元格常见写法：去掉 [ ] 外层后按分隔符拆分
        if s.startswith("[") and s.endswith("]"):
            s = s[1:-1]
        parts = re_split(s)
        cleaned: list[str] = []
        for part in parts:
            token = part.strip().strip("'").strip('"')
            if token:
                cleaned.append(token)
        return cleaned
    return []


def re_split(s: str) -> list[str]:
    """按逗号 / 分号 / 竖线拆分期望文档 ID 串。"""
    import re

    return [part for part in re.split(r"[,;|]", s) if part.strip()]
