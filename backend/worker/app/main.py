"""Worker 主循环：轮询 PG 任务队列并按 kind 分发执行器。

- ``benchmark`` / ``testcase``：真实执行器（见 benchmark.py / testcase.py）；
- ``rag``：真实执行器（见 rag.py：LightRAG 检索优先，本地关键词兜底）；
- ``stress``：下发 stress 容器发压，轮询取消并写 time_series 报告。

主循环同时承担 72h 用例确认超时扫描（PRD 3.3 / 5.4.1）：generated 状态的
用例集过期后联动 awaiting_case_confirm 任务与用例集双双置 cancelled。
"""

import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from .benchmark import run_benchmark
from .dispatch_presence import Presence
from .dataset_import import (
    claim_next_dataset_import,
    recover_expired_dataset_import_leases,
    run_dataset_import,
)
from .db import SessionLocal
from .events import push_ws
from .models import CaseSet, Setting, Task, TaskEvent
from .rag import run_rag
from .stress import run_stress
from .task_state import (
    TASK_LEASE_SECONDS,
    cancel_non_testcase_tasks,
    claim_running_task_for_terminal_write,
    lease_expired,
    recover_expired_task_leases,
    task_lease_heartbeat,
)
from .testcase import run_testcase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

TERMINAL = {"succeeded", "failed", "cancelled"}

# 平台并发上限默认值（PRD 3.4 / 后端计划 W4）：与 api 侧 DEFAULT_SETTINGS 保持一致
DEFAULT_MAX_RUNNING_TASKS = 3

# 72h 超时扫描节流间隔（秒）：主循环 1s 一轮，扫描器每 60s 实际执行一次
EXPIRE_SCAN_INTERVAL_S = 60.0
# 租约回收扫描间隔：租约 120s，5s 粒度足够，避免每秒扫两张表。
RECLAIM_SCAN_INTERVAL_S = 5.0
# 非 testcase 任务退役扫描间隔：只在启动/低频执行，防止旧任务被反复领取。
RETIRE_SCAN_INTERVAL_S = 30.0
# 数据库连续失败时指数退避上限（秒），避免故障期间日志与连接风暴。
MAX_BACKOFF_S = 30.0


def _dispatch_settings(db) -> tuple[bool, int]:
    """一次读回调度暂停标记与并发闸门；两条 Setting 合并为单次查询。"""
    rows = (
        db.query(Setting)
        .filter(Setting.key.in_(("dispatch", "max_running_tasks")))
        .all()
    )
    values = {row.key: row.value for row in rows}
    dispatch = values.get("dispatch")
    paused = isinstance(dispatch, dict) and dispatch.get("paused") is True
    raw = values.get("max_running_tasks")
    if isinstance(raw, bool):
        limit = DEFAULT_MAX_RUNNING_TASKS
    elif isinstance(raw, int) and raw >= 1:
        limit = raw
    elif isinstance(raw, float) and raw >= 1:
        limit = int(raw)
    else:
        limit = DEFAULT_MAX_RUNNING_TASKS
    return paused, limit


def _dispatch_paused(db) -> bool:
    """调度中心暂停后不再领取新任务；缺省或脏数据都按未暂停。"""
    return _dispatch_settings(db)[0]


def _max_running_tasks(db) -> int:
    """读取 settings.max_running_tasks 并发闸门；缺失或非法时回退默认 3。"""
    return _dispatch_settings(db)[1]


def _run_task(task_id: str) -> None:
    """按任务类型分发执行。

    入参为任务 ID 而非 ORM 对象：主循环 Session 与执行器 Session 相互独立，
    直接传递跨 Session 的 ORM 实例会导致 refresh 抛 InvalidRequestError、
    状态赋值不进脏检查（任务永久卡 running）。
    """
    db = SessionLocal()
    task: Task | None = None
    try:
        # 在本函数自己的 Session 内重新加载任务，确保后续读写均被脏检查追踪
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.error("task %s not found, skip execution", task_id)
            return

        db.add(TaskEvent(task_id=task.id, event="start", payload={"kind": task.kind}))
        db.commit()
        logger.info("开始执行 task=%s kind=%s", task.id, task.kind)
        print(f"[worker] start task={task.id} kind={task.kind}", flush=True)

        if task.kind == "rag":
            # M3 真实执行：LightRAG 检索优先，本地关键词检索兜底；
            # 执行器自管数据库会话与任务终态，这里提前释放本层会话
            db.close()
            logger.info("task %s (rag) dispatch to real executor", task_id)
            run_rag(task_id)
            return

        if task.kind == "benchmark":
            # M2 真实执行：两类协议调用 + 规则评分 + 预算熔断 + 断点续跑；
            # 执行器自管数据库会话与任务终态，这里提前释放本层会话
            db.close()
            logger.info("task %s (benchmark) dispatch to real executor", task_id)
            run_benchmark(task_id)
            return

        if task.kind == "testcase":
            # M2 W8 真实执行：六策略 LLM 生成 + 自检红字 + awaiting_case_confirm；
            # 执行器自管数据库会话与任务状态流转
            db.close()
            logger.info("task %s (testcase) dispatch to real executor", task_id)
            run_testcase(task_id)
            return

        if task.kind == "stress":
            db.close()
            logger.info("task %s (stress) dispatch to stress engine", task_id)
            run_stress(task_id)
            return

        logger.error("task %s unknown kind=%s", task_id, task.kind)
        task = claim_running_task_for_terminal_write(db, task_id)
        if not task:
            return
        task.status = "failed"
        task.finished_at = datetime.now(UTC)
        db.add(
            TaskEvent(
                task_id=task.id,
                event="error",
                payload={"message": "未知任务类型"},
            )
        )
        db.commit()
        push_ws(
            task.session_id,
            "error",
            {"code": "VALIDATION", "message": "未知任务类型"},
            task_id=task.id,
        )
    except Exception as exc:
        # rollback 会令 ORM 属性过期；先取标量，避免数据库仍不可用时再次触发刷新异常。
        try:
            failed_session_id = task.session_id if task is not None else None
        except Exception:
            failed_session_id = None
        db.rollback()
        # 详细堆栈只进服务端日志;给浏览器/事件流的失败原因仅透出异常类名辅助定位
        logger.exception("task %s execution error", task_id)
        print(f"[worker] failed task={task_id}", flush=True)
        # 失败状态落库单独保护：即使落库再失败也不阻断 error 事件推送
        try:
            if task is not None:
                task = claim_running_task_for_terminal_write(db, task.id)
                if not task:
                    logger.info("task %s skipped exception failure because it is no longer running", task_id)
                    return
                task.status = "failed"
                task.finished_at = datetime.now(UTC)
            db.add(
                TaskEvent(
                    task_id=task_id,
                    event="error",
                    payload={"message": f"执行失败({type(exc).__name__})"},
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("task %s failed-status persist error", task_id)
        push_ws(
            failed_session_id,
            "error",
            {"code": "INTERNAL", "message": f"执行失败({type(exc).__name__})"},
            task_id=task_id,
        )
    finally:
        db.close()


def _expire_stale_case_confirmations(db) -> int:
    """72h 用例确认超时扫描（PRD 3.3 / 5.4.1）。

    generated 状态且 ``expires_at`` 已过期的用例集 → cancelled；关联任务仍在
    ``awaiting_case_confirm`` 时同步取消并推送 WS 事件。任务已被单独取消的
    悬挂用例集也一并清理（扫描器只改 case set / task 状态，不动其它域）。
    返回本次取消的用例集数量，供日志与测试观测。
    """
    now = datetime.now(UTC)
    stale = (
        db.query(CaseSet)
        .filter(
            CaseSet.status == "generated",
            CaseSet.expires_at.isnot(None),
            CaseSet.expires_at <= now,
        )
        .with_for_update(skip_locked=True)
        .populate_existing()
        .all()
    )
    if not stale:
        return 0
    expired_count = 0
    notifications: list[tuple[str, str | None, str]] = []
    for case_set in stale:
        # 与 API 确认/废弃共享 CaseSet → Task 锁序，锁内复核截止时间及状态。
        if case_set.status != "generated" or not lease_expired(case_set.expires_at, now):
            continue
        case_set.status = "cancelled"
        expired_count += 1
        if not case_set.task_id:
            continue
        task = (
            db.query(Task)
            .filter(Task.id == case_set.task_id, Task.status == "awaiting_case_confirm")
            .with_for_update()
            .populate_existing()
            .first()
        )
        if task and task.status == "awaiting_case_confirm":
            task.status = "cancelled"
            task.finished_at = now
            task.progress = {**(task.progress or {}), "message": "用例确认超时，任务已自动取消"}
            db.add(
                TaskEvent(
                    task_id=task.id,
                    event="cancelled",
                    message="用例确认超过 72h，任务自动取消",
                    payload={"case_set_id": case_set.id},
                )
            )
            notifications.append((task.id, task.session_id, task.kind))
    db.commit()
    # 只通知本次确实取消的任务，避免把已经成功的任务广播为超时。
    for task_id, session_id, kind in notifications:
        if session_id:
            push_ws(
                session_id,
                "task_cancelled",
                {"status": "cancelled", "kind": kind, "message": "用例确认超时，任务已自动取消"},
                task_id=task_id,
            )
    logger.info("expired %d stale case set(s)", expired_count)
    return expired_count


def loop() -> None:
    """轮询评测与导入两条独立队列，二者各自受并发闸门和租约约束。"""
    last_expire_scan = 0.0
    last_reclaim_scan = 0.0
    last_retire_scan = 0.0
    # 连续失败次数：数据库不可用时指数退避，恢复后自动清零。
    error_streak = 0
    # 任务租约使用进程内随机 ID，避免新进程续上已退出进程的租约。
    # 调度星图使用稳定节点 ID，见 dispatch_presence。
    worker_id = uuid4().hex
    presence = Presence()
    presence.start()
    while True:
        db = SessionLocal()
        task_id: str | None = None
        import_claim: tuple[str, str] | None = None
        backoff_s = 0.0
        try:
            now = time.monotonic()
            # 退役扫描与租约回收不需要每秒执行：按各自间隔节流，空闲时几乎零查询。
            if now - last_retire_scan >= RETIRE_SCAN_INTERVAL_S:
                cancel_non_testcase_tasks(db)
                last_retire_scan = now
            if now - last_reclaim_scan >= RECLAIM_SCAN_INTERVAL_S:
                recover_expired_task_leases(db)
                # 导入租约独立于 Task：回收异常退出的领取。
                recover_expired_dataset_import_leases(db)
                last_reclaim_scan = now
            # 管理员请求重启：只在本轮还没领到任务时退出，正在执行的任务先跑完。
            if presence.take_idle_restart():
                logger.info("管理员请求重启节点，空闲退出以便容器重新拉起")
                print("[worker] restart requested, exiting", flush=True)
                raise SystemExit(0)
            # 排空、离线或调度暂停时不领新任务；已经在执行的任务由租约心跳继续。
            paused, max_running = _dispatch_settings(db)
            claimable = presence.allows_claim() and not paused
            if claimable:
                import_claim = claim_next_dataset_import(db)
            # 平台并发闸门（PRD 3.4）：running 任务达到 max_running_tasks 时
            # 不领取新任务，queued 任务保持排队；会话内串行由 tasks 表的
            # 部分唯一索引 uq_tasks_active_session 在创建侧保证。
            if claimable and not import_claim:
                running = db.query(Task).filter(Task.status == "running").count()
                if running < max_running:
                    task = (
                        db.query(Task)
                        .filter(Task.status == "queued", Task.kind == "testcase")
                        .order_by(Task.created_at.asc())
                        .with_for_update(skip_locked=True)
                        .first()
                    )
                    if task:
                        task.status = "running"
                        task.started_at = datetime.now(UTC)
                        task.claimed_by_worker_id = worker_id
                        task.claim_expires_at = task.started_at + timedelta(seconds=TASK_LEASE_SECONDS)
                        task.attempt = (task.attempt or 0) + 1
                        db.commit()
                        task_id = task.id
            error_streak = 0
        except Exception:
            error_streak += 1
            backoff_s = min(MAX_BACKOFF_S, float(2 ** min(error_streak - 1, 5)))
            logger.exception("worker loop error (连续 %d 次，退避 %.0fs)", error_streak, backoff_s)
        finally:
            db.close()
        # 执行器自建 Session；主循环绝不将 ORM 实体跨 Session 传递。
        if import_claim:
            import_id, lease_token = import_claim
            logger.info("开始执行 dataset import=%s", import_id)
            print(f"[worker] dataset-import start import={import_id}", flush=True)
            presence.set_activity(busy=True, task_id=None)
            try:
                run_dataset_import(import_id, lease_token)
            except Exception:
                # 数据库故障等异常不得带崩主循环；租约到期后由回收逻辑兜底。
                logger.exception("dataset import %s crashed", import_id)
            finally:
                presence.set_activity(busy=False, task_id=None)
        elif task_id:
            presence.set_activity(busy=True, task_id=task_id)
            try:
                with task_lease_heartbeat(task_id, worker_id) as active:
                    if active:
                        _run_task(task_id)
            except Exception:
                logger.exception("task %s crashed outside executor", task_id)
            finally:
                presence.set_activity(busy=False, task_id=None)
        # 72h 超时扫描：节流执行，避免每秒全表扫（表量级小，代价可忽略）
        if not backoff_s and time.monotonic() - last_expire_scan >= EXPIRE_SCAN_INTERVAL_S:
            last_expire_scan = time.monotonic()
            scan_db = SessionLocal()
            try:
                _expire_stale_case_confirmations(scan_db)
            except Exception:
                scan_db.rollback()
                logger.exception("case confirmation expire scan error")
            finally:
                scan_db.close()
        # 数据库连续失败时退避，避免故障期间每秒重连与刷日志。
        time.sleep(backoff_s or 1)


if __name__ == "__main__":
    logger.info("worker started")
    print("[worker] started", flush=True)
    loop()
