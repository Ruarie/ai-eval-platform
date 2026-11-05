"""远程命令审批队列：归属校验、一次性消费、过期与容量上限。"""

import time

import pytest

from app import workspace_exec_approval as approval


@pytest.fixture(autouse=True)
def _clean_queue():
    approval.clear()
    yield
    approval.clear()


def _create(**overrides):
    params = {
        "workspace_id": "ws-1",
        "user_id": "u-1",
        "command": "ls -la",
        "timeout_s": 30,
        "host": "build-01",
        "root": "/srv/app",
    }
    params.update(overrides)
    return approval.create(**params)


def test_create_returns_pending_preview():
    item = _create()

    assert item.approval_id
    assert item.host == "build-01"
    assert item.root == "/srv/app"
    assert 0 < item.expires_in_s <= approval.APPROVAL_TTL_S


def test_get_requires_same_workspace_and_user():
    item = _create()

    assert approval.get(item.approval_id, workspace_id="ws-1", user_id="u-1") is not None
    # 跨工作区/跨用户一律视为不存在，不泄露是否存在
    assert approval.get(item.approval_id, workspace_id="ws-2", user_id="u-1") is None
    assert approval.get(item.approval_id, workspace_id="ws-1", user_id="u-2") is None


def test_pop_is_one_shot():
    item = _create()

    assert approval.pop(item.approval_id, workspace_id="ws-1", user_id="u-1") is not None
    # 第二次消费必须失败：确认/拒绝后不允许重复执行
    assert approval.pop(item.approval_id, workspace_id="ws-1", user_id="u-1") is None


def test_expired_item_is_not_returned(monkeypatch):
    item = _create()
    item.created_at = time.monotonic() - approval.APPROVAL_TTL_S - 1

    assert approval.get(item.approval_id, workspace_id="ws-1", user_id="u-1") is None


def test_queue_evicts_oldest_when_full(monkeypatch):
    monkeypatch.setattr(approval, "MAX_PENDING", 2)
    first = _create(command="echo 1")
    second = _create(command="echo 2")
    third = _create(command="echo 3")

    assert approval.get(first.approval_id, workspace_id="ws-1", user_id="u-1") is None
    assert approval.get(second.approval_id, workspace_id="ws-1", user_id="u-1") is not None
    assert approval.get(third.approval_id, workspace_id="ws-1", user_id="u-1") is not None
