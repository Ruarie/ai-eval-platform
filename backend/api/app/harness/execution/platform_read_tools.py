"""平台只读查询工具：知识库清单与任务清单。

给通用助手一个「查平台数据」的正规入口：模型不必再用 ``bash``/``glob``
去翻工作区（那既查不到数据库里的数据，还会弹出工具确认卡阻塞对话）。

两条硬约束：

- **只读**：只做 SELECT，不写库、不触发任务、不改状态；
- **脱敏**：只返回名称/状态/数量这类摘要，不返回文档正文、凭据或内部路径。
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import func

from .session_guard import with_managed_session

# 单次返回上限：模型一次拿太多行只会稀释上下文，也拖慢响应。
_MAX_LIMIT = 50


def _limit(arguments: Mapping[str, object], default: int) -> int:
    """解析 ``limit``：非法值回退默认，并收敛到 [1, _MAX_LIMIT]。"""
    raw = arguments.get("limit")
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, _MAX_LIMIT))


def list_knowledge_bases(arguments: Mapping[str, object], context: object | None = None) -> dict:
    """列出知识库及其文档数（与 /kb 页面同源）。"""
    from app.models import KbDocument, KnowledgeBase

    limit = _limit(arguments, 20)
    with with_managed_session() as db:
        rows = (
            db.query(KnowledgeBase)
            .order_by(KnowledgeBase.created_at.desc())
            .limit(limit)
            .all()
        )
        counts = dict(
            db.query(KbDocument.kb_id, func.count(KbDocument.id))
            .group_by(KbDocument.kb_id)
            .all()
        )
        total = int(db.query(func.count(KnowledgeBase.id)).scalar() or 0)
        items = [
            {
                "id": kb.id,
                "name": kb.name,
                "kind": kb.kind,
                "doc_count": int(counts.get(kb.id, 0)),
                "is_core": bool(getattr(kb, "is_core", False)),
                "created_at": kb.created_at.isoformat() if kb.created_at else None,
            }
            for kb in rows
        ]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "note": "doc_count 与 /kb 页面一致；如需文档明细请在 /kb 查看。",
    }


def list_tasks(arguments: Mapping[str, object], context: object | None = None) -> dict:
    """列出最近任务（可按 kind 过滤），只返回状态摘要。"""
    from app.models import Task

    limit = _limit(arguments, 10)
    kind = str(arguments.get("kind") or "").strip()
    with with_managed_session() as db:
        query = db.query(Task)
        if kind:
            query = query.filter(Task.kind == kind)
        rows = query.order_by(Task.created_at.desc()).limit(limit).all()
        total = int(query.count())
        items = [
            {
                "task_id": task.id,
                "kind": task.kind,
                "status": task.status,
                "session_id": task.session_id,
                # 与 task.status 同源：用例任务完成后可从 result 里取到用例集 ID，
                # 模型据此直接给出 /cases?set_id=... 链接，无需再调一次 task.status。
                "case_set_id": (task.result or {}).get("case_set_id") if task.kind == "testcase" else None,
                "report_id": task.report_id,
                "created_at": task.created_at.isoformat() if task.created_at else None,
            }
            for task in rows
        ]
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "note": "只含状态摘要；具体草稿与报告请在 /cases、/tasks、/reports 查看。",
    }
