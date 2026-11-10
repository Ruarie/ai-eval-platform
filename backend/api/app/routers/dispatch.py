"""调度内核与 Worker 节点管理路由（API V1.3 §3.13）。

大盘指标由 dispatch_workers / tasks / dispatch_events 三表实时聚合；
分发策略与全局并发容量复用 settings 表持久化（strategy 存 ``dispatch``
键，max_running_tasks 与 admin 设置共享同一键，保证 worker 消费一致）。
分配日志只能由调度器 / worker 追加，本路由对浏览器只读。
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import AuditLog, DispatchEvent, DispatchWorker, Setting, Task, User
from ..schemas import (
    DispatchConfigUpdate,
    DispatchEventOut,
    DispatchEventPage,
    DispatchOverviewOut,
    DispatchWorkerCreate,
    DispatchWorkerOut,
    DispatchWorkerUpdate,
)

router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])

# 调度器轮询周期（毫秒），与原型大盘标注一致
HEARTBEAT_INTERVAL_MS = 500
# 心跳超过该时长未上报的节点视为离线
HEARTBEAT_TIMEOUT = timedelta(seconds=30)

DEFAULT_STRATEGY = "负载均衡"
DEFAULT_MAX_RUNNING = 3


def _load_config(db: Session) -> dict[str, Any]:
    """读取分发策略、全局并发容量和暂停标记；缺省回退默认值。"""
    strategy = DEFAULT_STRATEGY
    max_running = DEFAULT_MAX_RUNNING
    paused = False
    row = db.query(Setting).filter(Setting.key == "dispatch").first()
    if row and isinstance(row.value, dict):
        strategy = row.value.get("strategy", DEFAULT_STRATEGY)
        paused = row.value.get("paused") is True
    admin_row = db.query(Setting).filter(Setting.key == "max_running_tasks").first()
    if admin_row and isinstance(admin_row.value, int):
        max_running = admin_row.value
    return {"strategy": strategy, "max_running_tasks": max_running, "paused": paused}


def _effective_state(worker: DispatchWorker) -> str:
    """心跳超时的 busy/idle 节点按离线对待，排空、离线和重启中保持原状态。"""
    if worker.state in {"idle", "busy"}:
        last = worker.last_heartbeat_at
        if last is None:
            return "offline"
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if datetime.now(UTC) - last > HEARTBEAT_TIMEOUT:
            return "offline"
    return worker.state


def _worker_out(worker: DispatchWorker, task: Task | None) -> DispatchWorkerOut:
    """组装契约响应；current_task 附带任务类型便于调度大盘展示。"""
    current_task = None
    if task is not None:
        current_task = f"{task.id[:8]} · {task.kind}"
    return DispatchWorkerOut(
        id=worker.id,
        name=worker.name,
        caps=worker.caps or [],
        state=_effective_state(worker),
        weight=worker.weight,
        load_percent=worker.load_percent,
        current_task=current_task,
        last_heartbeat_at=worker.last_heartbeat_at,
    )


@router.get("/overview", response_model=DispatchOverviewOut, summary="调度大盘指标")
def get_overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """聚合 Worker 在线数、排队深度、平均调度耗时与今日已分配量。"""
    workers = db.query(DispatchWorker).all()
    online = sum(1 for w in workers if _effective_state(w) in {"idle", "busy"})
    queue_depth = db.query(func.count(Task.id)).filter(Task.status == "queued").scalar() or 0

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    assigned_events = (
        db.query(DispatchEvent)
        .filter(DispatchEvent.event == "assigned", DispatchEvent.ts >= today_start)
        .all()
    )
    costs = [
        float(e.detail["cost_ms"])
        for e in assigned_events
        if isinstance(e.detail, dict) and isinstance(e.detail.get("cost_ms"), int | float)
    ]
    avg_cost = round(sum(costs) / len(costs), 1) if costs else 0.0

    config = _load_config(db)
    return DispatchOverviewOut(
        online_workers=online,
        total_workers=len(workers),
        queue_depth=queue_depth,
        avg_dispatch_cost_ms=avg_cost,
        assigned_today=len(assigned_events),
        strategy=config["strategy"],
        max_running_tasks=config["max_running_tasks"],
        heartbeat_interval_ms=HEARTBEAT_INTERVAL_MS,
        paused=config["paused"],
    )


@router.get("/workers", summary="Worker 节点池状态列表")
def list_workers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """返回全部执行节点；current_task 关联任务表取短 ID 与类型。"""
    workers = db.query(DispatchWorker).order_by(DispatchWorker.id).all()
    task_ids = [w.current_task_id for w in workers if w.current_task_id]
    tasks = {t.id: t for t in db.query(Task).filter(Task.id.in_(task_ids)).all()} if task_ids else {}
    return {
        "items": [_worker_out(w, tasks.get(w.current_task_id)).model_dump(mode="json") for w in workers]
    }


@router.post("/workers", response_model=DispatchWorkerOut, status_code=201, summary="注册 Worker 节点")
def create_worker(
    body: DispatchWorkerCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """注册新执行节点，初始状态为 offline 等待首次心跳。"""
    if db.query(DispatchWorker).filter(DispatchWorker.id == body.id).first():
        raise AppError(ErrorCode.VALIDATION, "节点 ID 已存在")
    worker = DispatchWorker(id=body.id, name=body.name, caps=body.caps, weight=body.weight, state="offline")
    db.add(worker)
    db.add(
        AuditLog(
            user_id=user.id,
            action="dispatch_worker_register",
            target_type="dispatch_worker",
            target_id=body.id,
            detail={"name": body.name, "caps": body.caps},
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    db.refresh(worker)
    return _worker_out(worker, None)


@router.put("/workers/{worker_id}", response_model=DispatchWorkerOut, summary="治理 Worker 节点")
def update_worker(
    worker_id: str,
    body: DispatchWorkerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修改节点状态 / 权重 / 能力标签；进入 draining 时追加一条调度事件。"""
    worker = db.query(DispatchWorker).filter(DispatchWorker.id == worker_id).first()
    if not worker:
        raise AppError(ErrorCode.NOT_FOUND, "Worker 节点不存在")
    if body.state is not None:
        worker.state = body.state
    if body.weight is not None:
        worker.weight = body.weight
    if body.caps is not None:
        worker.caps = body.caps
    if body.state == "draining":
        db.add(
            DispatchEvent(
                worker_id=worker.id,
                event="draining",
                message=f"节点 {worker.name} 进入排空状态，不再接收新任务",
                detail={"weight": worker.weight},
            )
        )
    db.add(
        AuditLog(
            user_id=user.id,
            action="dispatch_worker_update",
            target_type="dispatch_worker",
            target_id=worker.id,
            detail=body.model_dump(exclude_none=True),
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    db.refresh(worker)
    task = db.query(Task).filter(Task.id == worker.current_task_id).first() if worker.current_task_id else None
    return _worker_out(worker, task)


@router.put("/config", summary="更新分发策略与并发容量")
def update_config(
    body: DispatchConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """策略与暂停标记写入 dispatch 设置键；并发容量与 admin 设置共享 max_running_tasks 键。"""
    if body.strategy is None and body.max_running_tasks is None and body.paused is None:
        raise AppError(ErrorCode.VALIDATION, "没有需要更新的调度配置")
    if body.strategy is not None or body.paused is not None:
        row = db.query(Setting).filter(Setting.key == "dispatch").first()
        current = dict(row.value) if row and isinstance(row.value, dict) else {}
        if body.strategy is not None:
            current["strategy"] = body.strategy
        if body.paused is not None:
            current["paused"] = body.paused
        if row:
            row.value = current
            row.updated_by = user.id
        else:
            db.add(Setting(key="dispatch", value=current, updated_by=user.id))
    if body.max_running_tasks is not None:
        row = db.query(Setting).filter(Setting.key == "max_running_tasks").first()
        if row:
            row.value = body.max_running_tasks
            row.updated_by = user.id
        else:
            db.add(Setting(key="max_running_tasks", value=body.max_running_tasks, updated_by=user.id))
    db.add(
        AuditLog(
            user_id=user.id,
            action="dispatch_config_update",
            target_type="settings",
            detail=body.model_dump(exclude_none=True),
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    return _load_config(db)


@router.post("/workers/{worker_id}/restart", response_model=DispatchWorkerOut, summary="请求重启 Worker 节点")
def restart_worker(
    worker_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """把节点标为 restarting。空闲进程会退出，由容器重启策略重新拉起。

    正在执行的任务会先跑完。平台不在 API 进程里杀容器。
    """
    worker = db.query(DispatchWorker).filter(DispatchWorker.id == worker_id).first()
    if not worker:
        raise AppError(ErrorCode.NOT_FOUND, "节点不存在")
    worker.state = "restarting"
    db.add(
        DispatchEvent(
            worker_id=worker.id,
            event="restarting",
            message=f"已请求重启节点 {worker.name}，当前任务结束后进程退出",
            detail={"requested_by": user.id},
        )
    )
    db.add(
        AuditLog(
            user_id=user.id,
            action="dispatch_worker_restart",
            target_type="dispatch_worker",
            target_id=worker.id,
            detail={"name": worker.name},
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    db.refresh(worker)
    task = db.query(Task).filter(Task.id == worker.current_task_id).first() if worker.current_task_id else None
    return _worker_out(worker, task)


@router.get("/events", response_model=DispatchEventPage, summary="调度分配日志增量流")
def list_events(
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按单调 id 升序增量返回；after_id 缺省时取最近一页（尾部 limit 条）。"""
    if after_id is not None:
        items = (
            db.query(DispatchEvent)
            .filter(DispatchEvent.id > after_id)
            .order_by(DispatchEvent.id.asc())
            .limit(limit)
            .all()
        )
    else:
        items = (
            db.query(DispatchEvent)
            .order_by(DispatchEvent.id.desc())
            .limit(limit)
            .all()
        )
        items.reverse()
    next_after = items[-1].id if items else (after_id or 0)
    return DispatchEventPage(
        items=[DispatchEventOut.model_validate(e) for e in items],
        next_after_id=next_after,
    )
