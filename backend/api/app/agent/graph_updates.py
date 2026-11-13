"""从图节点 update 中提取事件/审计/入队信息（纯函数，供 ws 层转发）。"""

from __future__ import annotations

from collections.abc import Iterator


def iter_pending_events(update: dict) -> Iterator[dict]:
    """从 LangGraph updates 增量中提取节点产出的 pending_events（图外消费）。"""
    for value in update.values():
        if isinstance(value, dict):
            events = value.get("pending_events")
            if isinstance(events, list):
                yield from events


def router_audit_from_update(update: dict) -> dict | None:
    """从 updates 增量中提取 Router 审计三元组（engine 已写入时）。

    供 ws.py 在取消 / 异常收尾路径携带审计（O2 信号：如 agent 分支立即
    /stop）；正常路径的审计已由收尾节点写入 completed payload，无需重复。
    """
    for value in update.values():
        if isinstance(value, dict) and value.get("engine"):
            return {
                "engine": value.get("engine"),
                "router_confidence": float(value.get("router_confidence") or 0.0),
                "router_reason": str(value.get("router_reason") or ""),
            }
    return None


def enqueued_task_id_from_update(update: dict) -> str | None:
    """从 updates 增量中提取 W6 入队结果（确认卡回执回显 task_id 用）。"""
    for value in update.values():
        if isinstance(value, dict) and value.get("enqueued_task_id"):
            return str(value["enqueued_task_id"])
    return None
