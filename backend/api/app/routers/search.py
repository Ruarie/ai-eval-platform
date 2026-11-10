"""全局搜索（N-07 MVP）：跨用例集、任务、会话、报告、知识库、数据集、工作区与个人记忆。

设计边界：
- 只读查询，不写审计、不改任何实体状态；
- 所有结果按当前登录成员权限过滤，私有会话/工作区/记忆不得泄漏；
- 每类最多 ``limit`` 条，不做全量计数，避免把搜索变成慢查询；
- 返回 ``url`` 由前端直接跳转，后端不拼接外部域名。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..harness.memory.personal import list_personal_memories
from ..models import (
    CaseItem,
    CaseSet,
    Dataset,
    KnowledgeBase,
    Report,
    Task,
    User,
    Workspace,
)
from ..models import (
    Session as AgentSession,
)
from ..schemas import SearchGroupOut, SearchItemOut, SearchResultOut
from ..time_utils import iso_utc

router = APIRouter(prefix="/api/search", tags=["search"])

_TYPE_LABELS = {
    "case": "用例集",
    "task": "任务",
    "session": "会话",
    "report": "报告",
    "kb": "知识库",
    "dataset": "数据集",
    "workspace": "工作区",
    "memory": "记忆",
}
_TYPE_ORDER = tuple(_TYPE_LABELS)

_CASE_STATUS = {"generated": "待确认", "confirmed": "已确认", "cancelled": "已废弃"}
_TASK_KIND = {"testcase": "用例生成", "benchmark": "基准评测", "rag": "RAG 评测", "stress": "压测"}
_TASK_STATUS = {
    "queued": "排队中",
    "running": "运行中",
    "awaiting_case_confirm": "待确认",
    "succeeded": "成功",
    "failed": "失败",
    "cancelled": "已取消",
}
_MEMORY_CATEGORY = {"preference": "偏好", "fact": "事实"}


def _like(term: str) -> str:
    """转义 LIKE 通配符，避免用户输入 ``%`` / ``_`` 变成全表匹配。"""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _item(
    *,
    entity_id: str,
    kind: str,
    title: str,
    subtitle: str = "",
    status: str = "",
    url: str,
    updated_at: str | None = None,
) -> SearchItemOut:
    """统一构造结果项，保证前端字段齐全。"""
    return SearchItemOut(
        id=entity_id,
        type=kind,
        title=title,
        subtitle=subtitle,
        status=status,
        url=url,
        updated_at=updated_at,
    )


def _search_cases(db: Session, pattern: str, limit: int) -> list[SearchItemOut]:
    """按用例集名称或用例正文命中搜索；返回用例集级结果，跳转后展示整集。"""
    matched_set_ids = select(CaseItem.case_set_id).where(
        or_(
            CaseItem.name.ilike(pattern, escape="\\"),
            CaseItem.module.ilike(pattern, escape="\\"),
            CaseItem.feature_point.ilike(pattern, escape="\\"),
        )
    )
    rows = (
        db.query(CaseSet.id, CaseSet.name, CaseSet.status, CaseSet.updated_at)
        .filter(
            or_(
                CaseSet.name.ilike(pattern, escape="\\"),
                CaseSet.id.in_(matched_set_ids),
            )
        )
        .order_by(CaseSet.updated_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return []
    ids = [row.id for row in rows]
    counts = dict(
        db.query(CaseItem.case_set_id, func.count(CaseItem.id))
        .filter(CaseItem.case_set_id.in_(ids))
        .group_by(CaseItem.case_set_id)
        .all()
    )
    return [
        _item(
            entity_id=row.id,
            kind="case",
            title=row.name or f"用例集 {row.id[:8]}",
            subtitle=f"用例集 · {counts.get(row.id, 0)} 条用例",
            status=_CASE_STATUS.get(row.status, row.status),
            url=f"/cases?set_id={row.id}",
            updated_at=iso_utc(row.updated_at),
        )
        for row in rows
    ]


def _search_tasks(db: Session, pattern: str, limit: int) -> list[SearchItemOut]:
    """按任务 ID、类型或状态搜索；不读取 config/result/progress 大 JSON。"""
    rows = (
        db.query(Task.id, Task.kind, Task.status, Task.updated_at)
        .filter(
            or_(
                Task.id.ilike(pattern, escape="\\"),
                Task.kind.ilike(pattern, escape="\\"),
                Task.status.ilike(pattern, escape="\\"),
            )
        )
        .order_by(Task.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [
        _item(
            entity_id=row.id,
            kind="task",
            title=f"{_TASK_KIND.get(row.kind, row.kind)} · {row.id[:8]}",
            subtitle=f"任务 {row.id}",
            status=_TASK_STATUS.get(row.status, row.status),
            url=f"/tasks?id={row.id}",
            updated_at=iso_utc(row.updated_at),
        )
        for row in rows
    ]


def _search_sessions(db: Session, pattern: str, limit: int, user: User) -> list[SearchItemOut]:
    """会话只搜标题与 ID；私有会话仅属主可见，团队会话全员可见。"""
    rows = (
        db.query(
            AgentSession.id,
            AgentSession.title,
            AgentSession.visibility,
            AgentSession.updated_at,
        )
        .filter(
            AgentSession.deleted_at.is_(None),
            AgentSession.engine_version == "agent_loop_v2",
            or_(
                AgentSession.title.ilike(pattern, escape="\\"),
                AgentSession.id.ilike(pattern, escape="\\"),
            ),
            or_(
                AgentSession.visibility == "team",
                AgentSession.user_id == user.id,
            ),
        )
        .order_by(AgentSession.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [
        _item(
            entity_id=row.id,
            kind="session",
            title=row.title or "未命名会话",
            subtitle="团队共享会话" if row.visibility == "team" else "私有会话",
            status="共享" if row.visibility == "team" else "私有",
            url=f"/agent?session_id={row.id}",
            updated_at=iso_utc(row.updated_at),
        )
        for row in rows
    ]


def _search_reports(db: Session, pattern: str, limit: int) -> list[SearchItemOut]:
    """报告按 ID 或类型搜索；不读取 metrics 与分享令牌。"""
    rows = (
        db.query(Report.id, Report.kind, Report.task_id, Report.created_at)
        .filter(
            or_(
                Report.id.ilike(pattern, escape="\\"),
                Report.kind.ilike(pattern, escape="\\"),
            )
        )
        .order_by(Report.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        _item(
            entity_id=row.id,
            kind="report",
            title=f"{_TASK_KIND.get(row.kind, row.kind)}报告 · {row.id[:8]}",
            subtitle=f"任务 {row.task_id}",
            url=f"/reports/{row.id}",
            updated_at=iso_utc(row.created_at),
        )
        for row in rows
    ]


def _search_kbs(db: Session, pattern: str, limit: int) -> list[SearchItemOut]:
    """知识库按名称搜索；外部 Chat 库同样可见。"""
    rows = (
        db.query(
            KnowledgeBase.id,
            KnowledgeBase.name,
            KnowledgeBase.kind,
            KnowledgeBase.is_core,
            KnowledgeBase.created_at,
        )
        .filter(KnowledgeBase.name.ilike(pattern, escape="\\"))
        .order_by(KnowledgeBase.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        _item(
            entity_id=row.id,
            kind="kb",
            title=row.name,
            subtitle="知识库 · LightRAG" if row.kind == "lightrag" else "知识库 · 外部 Chat",
            status="核心库" if row.is_core else "",
            url=f"/kb?kb_id={row.id}",
            updated_at=iso_utc(row.created_at),
        )
        for row in rows
    ]


def _search_datasets(db: Session, pattern: str, limit: int) -> list[SearchItemOut]:
    """数据集按名称搜索；仅历史只读资产。"""
    rows = (
        db.query(Dataset.id, Dataset.name, Dataset.created_at)
        .filter(Dataset.name.ilike(pattern, escape="\\"))
        .order_by(Dataset.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        _item(
            entity_id=row.id,
            kind="dataset",
            title=row.name,
            subtitle="历史数据集",
            url="/datasets",
            updated_at=iso_utc(row.created_at),
        )
        for row in rows
    ]


def _search_workspaces(db: Session, pattern: str, limit: int, user: User) -> list[SearchItemOut]:
    """工作区只搜当前成员未注销的目录。"""
    rows = (
        db.query(Workspace.id, Workspace.name, Workspace.kind, Workspace.created_at)
        .filter(
            Workspace.owner_id == user.id,
            Workspace.deleted_at.is_(None),
            Workspace.name.ilike(pattern, escape="\\"),
        )
        .order_by(Workspace.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        _item(
            entity_id=row.id,
            kind="workspace",
            title=row.name,
            subtitle="远程 SSH 工作区" if row.kind == "ssh" else "本地工作区",
            status="远程" if row.kind == "ssh" else "本地",
            url="/workspaces",
            updated_at=iso_utc(row.created_at),
        )
        for row in rows
    ]


def _search_memories(db: Session, term: str, limit: int, user: User) -> list[SearchItemOut]:
    """个人记忆复用现有受控查询，避免绕开 ACL、凭据与版本过滤。"""
    result = list_personal_memories(db, user.id, q=term, limit=limit)
    return [
        _item(
            entity_id=item["id"],
            kind="memory",
            title=item["title"],
            subtitle="记忆 · " + _MEMORY_CATEGORY.get(item.get("category", ""), "资料")
            + (f" · {item['workspace_name']}" if item.get("workspace_name") else ""),
            status="已撤回" if item.get("revoked") else "",
            url="/memories",
            updated_at=item.get("updated_at"),
        )
        for item in result.get("items", [])
    ]


@router.get("", response_model=SearchResultOut, summary="跨实体全局搜索")
def global_search(
    q: str = Query(min_length=1, max_length=80, description="搜索词"),
    limit: int = Query(5, ge=1, le=10, description="每类最多返回条数"),
    types: str | None = Query(default=None, description="逗号分隔的类型过滤"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchResultOut:
    """按权限搜索八类资产；空搜索词直接返回空结果，不报 422。"""
    term = q.strip()
    if not term:
        return SearchResultOut(query="", groups=[])

    raw_types = [name for name in (types or "").split(",") if name]
    requested = [name for name in raw_types if name in _TYPE_LABELS]
    if raw_types and not requested:
        # 显式传入未知类型时不回退成全量搜索，避免调用方误以为筛选生效。
        return SearchResultOut(query=term, groups=[])
    ordered = [name for name in _TYPE_ORDER if not requested or name in requested]
    pattern = _like(term)

    handlers = {
        "case": lambda: _search_cases(db, pattern, limit),
        "task": lambda: _search_tasks(db, pattern, limit),
        "session": lambda: _search_sessions(db, pattern, limit, user),
        "report": lambda: _search_reports(db, pattern, limit),
        "kb": lambda: _search_kbs(db, pattern, limit),
        "dataset": lambda: _search_datasets(db, pattern, limit),
        "workspace": lambda: _search_workspaces(db, pattern, limit, user),
        "memory": lambda: _search_memories(db, term, limit, user),
    }

    groups: list[SearchGroupOut] = []
    for name in ordered:
        items = handlers[name]()
        if items:
            groups.append(SearchGroupOut(type=name, label=_TYPE_LABELS[name], items=items))
    return SearchResultOut(query=term, groups=groups)
