"""PostgreSQL 上的 SKIP LOCKED 领取语义。

本地没有数据库时跳过。CI 的 worker job 会提供 WORKER_TEST_DATABASE_URL。
SQLite 夹具不会真正锁行，所以这条不能并进普通 worker 测试。
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.skipif(
    not os.environ.get("WORKER_TEST_DATABASE_URL"),
    reason="未设置 WORKER_TEST_DATABASE_URL，跳过 PostgreSQL 行锁测试",
)


def test_skip_locked_claim_skips_held_testcase_row():
    """第一连接持有最早的 testcase 时，第二连接领到下一条 testcase，不领 benchmark。"""
    engine = create_engine(os.environ["WORKER_TEST_DATABASE_URL"])
    claim = text(
        "SELECT id FROM claim_probe "
        "WHERE status = 'queued' AND kind = 'testcase' "
        "ORDER BY created_at "
        "FOR UPDATE SKIP LOCKED "
        "LIMIT 1"
    )
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS claim_probe"))
        conn.execute(text(
            "CREATE TABLE claim_probe ("
            "id text PRIMARY KEY, status text NOT NULL, kind text NOT NULL, created_at timestamptz NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO claim_probe (id, status, kind, created_at) VALUES "
            "('a', 'queued', 'testcase', now()), "
            "('b', 'queued', 'benchmark', now() + interval '1 second'), "
            "('c', 'queued', 'testcase', now() + interval '2 seconds')"
        ))
    first = engine.connect()
    second = engine.connect()
    tx1 = first.begin()
    tx2 = second.begin()
    try:
        held = first.execute(claim).scalar_one()
        nxt = second.execute(claim).scalar_one()
        assert held == "a"
        assert nxt == "c"
    finally:
        tx1.rollback()
        tx2.rollback()
        first.close()
        second.close()
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS claim_probe"))
        engine.dispose()
