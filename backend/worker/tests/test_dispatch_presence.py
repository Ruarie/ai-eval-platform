"""调度节点心跳：登记本进程，且不覆盖管理员的排空或离线。"""

from datetime import UTC, datetime, timedelta

from app.dispatch_presence import Presence, claim_allowed, take_idle_restart, write_presence
from app.models import DispatchWorker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_presence_registers_and_preserves_governed_state(tmp_path, monkeypatch):
    """空表插入空闲节点；排空节点只刷新心跳和负载，不改回 busy。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'presence.db'}")
    DispatchWorker.__table__.create(engine)
    factory = sessionmaker(engine, autoflush=False)
    monkeypatch.setattr("app.dispatch_presence.SessionLocal", factory)

    write_presence("worker-1", "用例 Worker", busy=False, task_id=None)
    with factory() as db:
        row = db.query(DispatchWorker).one()
        assert row.state == "idle"
        assert row.caps == ["testcase"]
        assert row.load_percent == 0
        assert row.last_heartbeat_at is not None
        row.state = "draining"
        row.weight = 40
        row.last_heartbeat_at = datetime.now(UTC) - timedelta(minutes=5)
        db.commit()

    write_presence("worker-1", "另一个名字", busy=True, task_id=None)
    with factory() as db:
        row = db.query(DispatchWorker).one()
        assert row.state == "draining"
        assert row.weight == 40
        assert row.name == "用例 Worker"
        assert row.load_percent == 100
        seen = row.last_heartbeat_at
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        assert seen > datetime.now(UTC) - timedelta(seconds=10)
    assert claim_allowed("worker-1") is False

    with factory() as db:
        row = db.query(DispatchWorker).one()
        row.state = "offline"
        db.commit()
    assert claim_allowed("worker-1") is False

    with factory() as db:
        row = db.query(DispatchWorker).one()
        row.state = "idle"
        db.commit()
    assert claim_allowed("worker-1") is True
    assert claim_allowed("missing") is True
    engine.dispose()


def test_restarting_stops_claims_until_acknowledged(tmp_path, monkeypatch):
    """restarting 不领新任务；空闲确认后改回 idle，避免新进程反复退出。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'restart.db'}")
    DispatchWorker.__table__.create(engine)
    factory = sessionmaker(engine, autoflush=False)
    monkeypatch.setattr("app.dispatch_presence.SessionLocal", factory)

    write_presence("worker-1", "用例 Worker", busy=False, task_id=None)
    with factory() as db:
        row = db.query(DispatchWorker).one()
        row.state = "restarting"
        db.commit()
    assert claim_allowed("worker-1") is False
    write_presence("worker-1", "用例 Worker", busy=True, task_id="task-1")
    with factory() as db:
        row = db.query(DispatchWorker).one()
        assert row.state == "restarting"
    assert take_idle_restart("worker-1") is True
    with factory() as db:
        row = db.query(DispatchWorker).one()
        assert row.state == "idle"
        assert row.current_task_id is None
    assert take_idle_restart("worker-1") is False

    # 主循环持有 Presence 实例；实例方法必须与模块函数同语义，否则 worker 永不领任务。
    monkeypatch.setenv("WORKER_NODE_ID", "worker-1")
    presence = Presence()
    with factory() as db:
        row = db.query(DispatchWorker).one()
        row.state = "restarting"
        db.commit()
    assert presence.take_idle_restart() is True
    with factory() as db:
        row = db.query(DispatchWorker).one()
        assert row.state == "idle"
        assert row.current_task_id is None
    assert presence.take_idle_restart() is False
    engine.dispose()
