"""个人记忆：用户主动保存与默认关闭的自动抽取；私有 ACL、版本及有界召回。

召回默认走关键词；开启 ``agent_memory_semantic_enabled`` 后，用查询向量与已回填
向量做余弦融合排序（阈值见 ``semantic.SIMILARITY_THRESHOLD``）。Embedding 失败
只降级为关键词，不阻断模型请求；未回填向量的旧记录仍可被关键词命中。
"""

from __future__ import annotations

import json
import logging
import re
from uuid import uuid4

from sqlalchemy import String, cast, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError, ErrorCode
from app.harness.context.meter import estimate_tokens
from app.harness.security.loop_redaction import contains_credential
from app.models import AuditLog, KnowledgeMemory, User, Workspace
from app.time_utils import iso_utc

from .semantic import as_vector, combined_score, cosine, is_candidate

logger = logging.getLogger("harness.memory.personal")

MAX_MEMORIES = 200
RECALL_LIMIT = 5
RECALL_TOKEN_BUDGET = 2048
# 召回处在模型请求路径上：查询向量给 1.5s 上限，超时立即退回关键词。
RECALL_EMBED_TIMEOUT_S = 1.5
# 自动抽取的向量去重阈值：高于召回阈值，避免把不同事实误判为重复。
DEDUP_SIMILARITY = 0.92
SOURCE_MANUAL = "manual:"
SOURCE_AUTO = "auto:"
_WORDS = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.IGNORECASE)


def _owned(db: Session, user_id: str):
    """先以 SQL 收紧命名空间、ACL 和来源，旧宽 ACL 记录绝不进入候选。"""
    return db.query(KnowledgeMemory).filter(
        KnowledgeMemory.tenant_id == f"personal:{user_id}",
        KnowledgeMemory.acl == "private", KnowledgeMemory.acl_user_ids == [user_id],
        KnowledgeMemory.meta["kind"].as_string() == "personal_memory",
        # 不把脏历史 JSON 强转为整数，避免非法版本令整页读取失败。
        cast(KnowledgeMemory.meta["schema_version"].as_string(), String) == "1",
        or_(
            KnowledgeMemory.source_id == SOURCE_MANUAL + KnowledgeMemory.id,
            KnowledgeMemory.source_id == SOURCE_AUTO + KnowledgeMemory.id,
        ),
        KnowledgeMemory.source_version >= 1, KnowledgeMemory.memory_revoked.is_(False),
    ).populate_existing()


def _lock_user(db: Session, user_id: str) -> None:
    """所有个人记忆写入同成员串行，配额与版本检查在同一事务中完成。"""
    user = db.query(User).filter(User.id == user_id).populate_existing().with_for_update(key_share=True).first()
    if user is None or user.disabled:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户不可用")


def _workspace(db: Session, user_id: str, workspace_id: str | None, *, lock=False):
    """只解析当前成员活跃工作区；写入时先取工作区锁，再取用户锁。"""
    if workspace_id is None:
        return None
    query = db.query(Workspace).filter(
        Workspace.id == workspace_id, Workspace.owner_id == user_id, Workspace.deleted_at.is_(None),
    ).populate_existing()
    if lock:
        query = query.with_for_update()
    return query.first()


def _workspace_names(db: Session, user_id: str, rows: list) -> dict[str, str]:
    """批量读取可见工作区名称；失效绑定仍可在管理列表撤回或改为全局。"""
    ids = {row.meta.get("workspace_id") for row in rows if isinstance(row.meta.get("workspace_id"), str)}
    if not ids:
        return {}
    return {row.id: row.name for row in db.query(Workspace).filter(
        Workspace.id.in_(ids), Workspace.owner_id == user_id, Workspace.deleted_at.is_(None),
    ).populate_existing().all()}


def _safe_row(row: KnowledgeMemory) -> bool:
    """读旧记录也校验有界正文和凭据，脏存量不能进入响应或模型上下文。"""
    meta = row.meta
    title, content = meta.get("title"), row.content
    workspace_id = meta.get("workspace_id")
    return (type(meta.get("schema_version")) is int and meta["schema_version"] == 1
            and isinstance(title, str) and bool(title.strip()) and len(title) <= 80
            and isinstance(content, str) and bool(content.strip()) and len(content) <= 2000
            and meta.get("category") in ("preference", "fact")
            and (workspace_id is None or isinstance(workspace_id, str) and 0 < len(workspace_id) <= 128)
            and not contains_credential(title) and not contains_credential(content))


def _project(row: KnowledgeMemory, names: dict[str, str]) -> dict:
    """只暴露记忆契约字段；来源只区分手动/自动，不冒充会话证据。"""
    workspace_id = row.meta.get("workspace_id")
    return {
        "id": row.id, "title": row.meta["title"], "content": row.content,
        "category": row.meta["category"], "workspace_id": workspace_id,
        "workspace_name": names.get(workspace_id), "version": row.source_version,
        "source": "auto" if row.source_id.startswith(SOURCE_AUTO) else "manual",
        "source_id": row.source_id, "created_at": iso_utc(row.created_at),
        "updated_at": iso_utc(row.updated_at),
    }


def list_personal_memories(db: Session, user_id: str, *, q="", workspace_id=None, limit=50, offset=0) -> dict:
    """按本人范围分页；省略 scope 查全部，空字符串只查全局，非空查指定工作区。"""
    query = _owned(db, user_id)
    if workspace_id is not None:
        scope = KnowledgeMemory.meta["workspace_id"].as_string()
        query = query.filter(scope.is_(None) if workspace_id == "" else scope == workspace_id)
    if q:
        query = query.filter(or_(KnowledgeMemory.content.icontains(q, autoescape=True),
                                 KnowledgeMemory.meta["title"].as_string().icontains(q, autoescape=True)))
    rows = [row for row in query.order_by(KnowledgeMemory.updated_at.desc(), KnowledgeMemory.id).all()
            if _safe_row(row)]
    selected = rows[offset:offset + limit]
    names = _workspace_names(db, user_id, selected)
    return {"items": [_project(row, names) for row in selected], "total": len(rows)}


def _write_fields(db: Session, user_id: str, title: str, content: str, category: str, workspace_id: str | None):
    """验证已通过请求 schema 的文本及绑定，保持工作区→用户的锁顺序。"""
    if contains_credential(title) or contains_credential(content):
        raise AppError(ErrorCode.VALIDATION, "请移除疑似凭据后再保存记忆")
    workspace = _workspace(db, user_id, workspace_id, lock=True)
    if workspace_id is not None and workspace is None:
        raise AppError(ErrorCode.NOT_FOUND, "工作区不存在或不可用")
    _lock_user(db, user_id)
    return {"kind": "personal_memory", "schema_version": 1, "title": title,
            "category": category, "workspace_id": workspace_id}, workspace


def _audit(db: Session, user_id: str, row: KnowledgeMemory, action: str) -> None:
    """审计只记录动作、作用域和版本，不保留标题或正文。"""
    db.add(AuditLog(user_id=user_id, action=action, target_type="personal_memory", target_id=row.id,
                    detail={"version": row.source_version, "category": row.meta["category"],
                            "workspace_id": row.meta.get("workspace_id")}))


def create_personal_memory(db: Session, user_id: str, *, title: str, content: str, category="fact", workspace_id=None) -> dict:
    """保存用户手动填写的记忆；调用者负责与审计一并提交。"""
    meta, workspace = _write_fields(db, user_id, title, content, category, workspace_id)
    if _owned(db, user_id).count() >= MAX_MEMORIES:
        raise AppError(ErrorCode.VALIDATION, "个人记忆已达 200 条上限，请先撤回不再需要的记忆")
    identity = str(uuid4())
    row = KnowledgeMemory(id=identity, tenant_id=f"personal:{user_id}", source_id=f"manual:{identity}",
                          source_version=1, content=content, embedding=None, meta=meta,
                          acl="private", acl_user_ids=[user_id], memory_revoked=False)
    db.add(row)
    db.flush()
    _audit(db, user_id, row, "agent_memory_create")
    return _project(row, {workspace.id: workspace.name} if workspace else {})


def _versioned_row(db: Session, user_id: str, memory_id: str, version: int) -> KnowledgeMemory:
    """越权与撤回统一隐藏，已有记录才检查乐观版本冲突。"""
    row = _owned(db, user_id).filter(KnowledgeMemory.id == memory_id).with_for_update().first()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "记忆不存在")
    if row.source_version != version:
        raise AppError(ErrorCode.CONCURRENCY, "记忆已更新，请刷新后重试")
    return row


def update_personal_memory(db: Session, user_id: str, memory_id: str, *, version: int,
                           title: str, content: str, category="fact", workspace_id=None) -> dict:
    """全量替换一条手动记忆，版本匹配后才允许更新。"""
    meta, workspace = _write_fields(db, user_id, title, content, category, workspace_id)
    row = _versioned_row(db, user_id, memory_id, version)
    row.meta, row.content, row.source_version = meta, content, version + 1
    row.embedding = None
    db.flush()
    _audit(db, user_id, row, "agent_memory_update")
    return _project(row, {workspace.id: workspace.name} if workspace else {})


def revoke_personal_memory(db: Session, user_id: str, memory_id: str, version: int) -> None:
    """撤回立即排除未来召回并清空标题正文；保留无正文来源与递增版本。"""
    _lock_user(db, user_id)
    row = _versioned_row(db, user_id, memory_id, version)
    row.meta = {**row.meta, "title": ""}
    row.content, row.embedding, row.memory_revoked, row.source_version = "", None, True, version + 1
    _audit(db, user_id, row, "agent_memory_revoke")


def _keywords(value: str) -> set[str]:
    """英文按词、中文按相邻双字拆分；不进行模型推断或无关事实补齐。"""
    result = set()
    for word in _WORDS.findall(value.casefold()):
        if "\u4e00" <= word[0] <= "\u9fff":
            result.update(word[index:index + 2] for index in range(len(word) - 1))
        elif len(word) > 1:
            result.add(word)
    return result


def _recall_query_vector(query: str) -> list[float] | None:
    """召回查询向量；未启用、未配置、超时或失败时返回 None，由关键词兜底。

    召回在模型请求路径上，任何 Embedding 异常都不得阻断回合，也不回写记忆。
    """
    text = (query or "").strip()[:2000]
    if not text or not settings.agent_memory_semantic_enabled:
        return None
    return _embed_texts([text], timeout_s=RECALL_EMBED_TIMEOUT_S)[0]


def recall_personal_memories(db: Session, user_id: str, workspace_id: str | None, query: str) -> list[dict]:
    """每次新查最多 200 个已授权候选，返回最多五条且整组不超过 2048 估算 token。"""
    if db.query(User.id).filter(User.id == user_id, User.disabled.is_(False)).first() is None:
        return []
    workspace = _workspace(db, user_id, workspace_id)
    scope = KnowledgeMemory.meta["workspace_id"].as_string()
    scope_filter = or_(scope.is_(None), scope == workspace.id) if workspace else scope.is_(None)
    rows = _owned(db, user_id).filter(scope_filter).order_by(
        KnowledgeMemory.updated_at.desc(), KnowledgeMemory.id,
    ).limit(MAX_MEMORIES).all()
    words = _keywords(query[:2000])
    query_vector = _recall_query_vector(query)
    ranked = []
    for row in rows:
        if not _safe_row(row):
            continue
        keyword_score = 3 * len(words & _keywords(row.meta["title"])) + len(words & _keywords(row.content))
        if query_vector is not None:
            # 未回填向量的旧记录 similarity=0，只靠关键词命中；偏好始终保留。
            similarity = cosine(query_vector, row.embedding)
            if is_candidate(keyword_score, similarity, always=row.meta["category"] == "preference"):
                ranked.append((combined_score(keyword_score, similarity), row))
        elif keyword_score or row.meta["category"] == "preference":
            ranked.append((float(keyword_score), row))
    # Python 稳定排序保留 SQL 已按更新时间和 ID 排好的相同相关度顺序。
    ranked.sort(key=lambda item: item[0], reverse=True)
    names = {workspace.id: workspace.name} if workspace else {}
    selected = []
    for _, row in ranked:
        item = _project(row, names)
        if estimate_tokens(json.dumps([*selected, item], ensure_ascii=False, sort_keys=True)) <= RECALL_TOKEN_BUDGET:
            selected.append(item)
        if len(selected) == RECALL_LIMIT:
            break
    return selected


def _normalized(title: str, content: str) -> str:
    """精确去重的归一文本：压缩空白后比较，避免排版差异刷出重复记忆。"""
    return " ".join(f"{title}\n{content}".split())


def _embed_texts(texts: list[str], *, timeout_s: float = 3.0) -> list[list[float] | None]:
    """按开关生成向量；未启用、未配置或上游失败时全部返回 None。

    记忆读写不能因向量失败而中断：调用方在 None 时只做精确文本去重。
    """
    if not texts:
        return []
    if not settings.agent_memory_semantic_enabled:
        return [None] * len(texts)
    try:
        from app.llm import embeddings

        vectors = embeddings.embed_texts(texts, timeout_s=timeout_s)
    except AppError as exc:
        logger.info("个人记忆向量跳过 code=%s", exc.code.value)
        return [None] * len(texts)
    except Exception as exc:  # 上游/HTTP 异常不进入记忆事务
        logger.warning("个人记忆向量失败 type=%s", type(exc).__name__)
        return [None] * len(texts)
    if len(vectors) != len(texts):
        return [None] * len(texts)
    return [as_vector(item) for item in vectors]


def _apply_vector(db: Session, row: KnowledgeMemory, vector: list[float] | None) -> bool:
    """在保存点内写入向量；维度不符等失败只丢弃该行向量，不影响记忆正文。"""
    if not vector:
        return False
    try:
        with db.begin_nested():
            row.embedding = vector
            db.flush()
    except Exception as exc:  # pgvector 维度/存储异常
        db.expire(row, ["embedding"])
        logger.warning("个人记忆向量写入失败 type=%s", type(exc).__name__)
        return False
    return True


def store_extracted_memories(db: Session, user_id: str, workspace_id: str | None,
                             items: list[dict], *, max_items: int = 3) -> list[str]:
    """落库自动抽取候选；返回新建记忆 ID。

    候选已在模型侧生成，这里仍做代码侧强校验：条数与长度、枚举、凭据拒绝、
    精确/向量去重、200 条配额与私有 ACL。工作区不属于本人时回落全局，
    不静默越权绑定；调用方负责提交事务。
    """
    prepared: list[tuple[str, str, str]] = []
    for item in items or []:
        if len(prepared) >= max_items:
            break
        if not isinstance(item, dict):
            continue
        title = " ".join(str(item.get("title") or "").split())[:80]
        content = " ".join(str(item.get("content") or "").split())[:2000]
        category = item.get("category")
        if not title or not content or category not in ("preference", "fact"):
            continue
        if contains_credential(title) or contains_credential(content):
            continue
        prepared.append((title, content, category))
    if not prepared:
        return []

    _lock_user(db, user_id)
    workspace = _workspace(db, user_id, workspace_id, lock=True)
    scope_id = workspace.id if workspace else None
    rows = _owned(db, user_id).order_by(
        KnowledgeMemory.updated_at.desc(), KnowledgeMemory.id,
    ).limit(MAX_MEMORIES).all()
    quota = len(rows)
    seen_text = {_normalized(row.meta["title"], row.content) for row in rows if _safe_row(row)}
    seen_vectors = [as_vector(row.embedding) for row in rows if _safe_row(row)]
    vectors = _embed_texts([f"{title}\n{content}" for title, content, _ in prepared])

    created: list[str] = []
    for (title, content, category), vector in zip(prepared, vectors):
        if quota >= MAX_MEMORIES:
            break
        normalized = _normalized(title, content)
        if normalized in seen_text:
            continue
        if vector and any(
            cosine(vector, existing) >= DEDUP_SIMILARITY
            for existing in seen_vectors if existing
        ):
            continue
        identity = str(uuid4())
        meta = {
            "kind": "personal_memory", "schema_version": 1, "title": title,
            "category": category, "workspace_id": scope_id, "origin": "auto",
        }
        row = KnowledgeMemory(
            id=identity, tenant_id=f"personal:{user_id}", source_id=SOURCE_AUTO + identity,
            source_version=1, content=content, embedding=None, meta=meta,
            acl="private", acl_user_ids=[user_id], memory_revoked=False,
        )
        db.add(row)
        db.flush()
        _apply_vector(db, row, vector)
        db.add(AuditLog(
            user_id=user_id, action="agent_memory_extract", target_type="personal_memory",
            target_id=identity,
            detail={"version": 1, "category": category, "workspace_id": scope_id},
        ))
        seen_text.add(normalized)
        if vector:
            seen_vectors.append(vector)
        created.append(identity)
        quota += 1
    return created


def reindex_personal_memories(db: Session, user_id: str, *, limit: int = 200,
                              force: bool = False) -> dict:
    """为本人记忆补齐向量（force 时重算全部）；语义未启用时显式拒绝。

    只处理通过安全校验的记录；单行向量失败不影响其余行，返回本次新增数量
    与仍需回填的数量，便于管理命令重复执行。
    """
    if not settings.agent_memory_semantic_enabled:
        raise AppError(ErrorCode.VALIDATION, "语义向量未启用，请先配置 Embedding 端点")
    query = _owned(db, user_id)
    if not force:
        query = query.filter(KnowledgeMemory.embedding.is_(None))
    rows = [row for row in query.order_by(
        KnowledgeMemory.updated_at.desc(), KnowledgeMemory.id,
    ).limit(limit).all() if _safe_row(row)]
    if not rows:
        return {"embedded": 0, "candidates": 0, "remaining": 0}
    vectors = _embed_texts([f"{row.meta['title']}\n{row.content}" for row in rows])
    embedded = 0
    for row, vector in zip(rows, vectors):
        if _apply_vector(db, row, vector):
            embedded += 1
    remaining = _owned(db, user_id).filter(KnowledgeMemory.embedding.is_(None)).count()
    return {"embedded": embedded, "candidates": len(rows), "remaining": remaining}
