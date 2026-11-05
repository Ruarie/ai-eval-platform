"""远程 SSH 工作区契约测试：白名单 fail-closed、路径边界、私钥引用安全。

不做真实 SSH 连接：只覆盖"不连网也必须成立"的判定，连接层由部署环境验证。
"""

from types import SimpleNamespace

import pytest

from app import remote_workspace as rw


def _row(**overrides) -> SimpleNamespace:
    base = {
        "kind": "ssh",
        "ssh_host": "build-01",
        "ssh_port": 22,
        "ssh_user": "deploy",
        "ssh_key_name": "id_ed25519",
        "remote_root": "/srv/workspace",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_target_allows_any_host_when_allowlist_empty(monkeypatch):
    """白名单留空表示不限制目标主机：能否连上由目标机是否接受该私钥决定。"""
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "")

    target = rw.target_for(_row(ssh_host="203.0.113.20"))

    assert target.host == "203.0.113.20"


def test_target_rejects_host_outside_allowlist(monkeypatch):
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "build-02, build-03")

    with pytest.raises(rw.RemoteWorkspaceError, match="白名单"):
        rw.target_for(_row())


def test_target_requires_absolute_root(monkeypatch):
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "build-01")

    with pytest.raises(rw.RemoteWorkspaceError, match="绝对路径"):
        rw.target_for(_row(remote_root="srv/workspace"))


def test_target_accepts_whitelisted_host(monkeypatch):
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "build-01")

    target = rw.target_for(_row(remote_root="/"))

    assert target.host == "build-01"
    assert target.port == 22
    assert target.root == "/"


def test_normalize_blocks_traversal(monkeypatch):
    """即使 remote_root 允许任意路径，`..` 也不能逃出根目录。"""
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "build-01")

    assert rw._normalize(_row(), "logs/app.log") == "/srv/workspace/logs/app.log"
    with pytest.raises(rw.RemotePathError, match="越界"):
        rw._normalize(_row(), "../../etc/passwd")


def test_normalize_allows_absolute_inside_root(monkeypatch):
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "build-01")

    assert rw._normalize(_row(), "/srv/workspace/src/main.py") == "/srv/workspace/src/main.py"
    with pytest.raises(rw.RemotePathError, match="越界"):
        rw._normalize(_row(), "/etc/hosts")


def test_normalize_root_slash_permits_any_absolute(monkeypatch):
    """remote_root=/ 时允许任意绝对路径（本轮产品选择），但仍拒绝 `..` 逃逸。"""
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "build-01")

    assert rw._normalize(_row(remote_root="/"), "/opt/app/config.yml") == "/opt/app/config.yml"


def test_key_name_rejects_path_segments(monkeypatch):
    monkeypatch.setattr(rw.settings, "workspace_ssh_allowed_hosts", "build-01")
    monkeypatch.setattr(rw.settings, "workspace_ssh_key_dir", "/run/secrets/workspace-ssh")

    for key_name in ("../id_rsa", "dir/id_ed25519", ".."):
        with pytest.raises(rw.RemoteWorkspaceError, match="非法"):
            rw._load_private_key(key_name)


def test_key_dir_missing_is_reported(monkeypatch):
    monkeypatch.setattr(rw.settings, "workspace_ssh_key_dir", "")

    with pytest.raises(rw.RemoteWorkspaceError, match="WORKSPACE_SSH_KEY_DIR"):
        rw._load_private_key("id_ed25519")


def test_local_workspace_is_not_treated_as_ssh():
    with pytest.raises(rw.RemoteWorkspaceError, match="不是远程"):
        rw.target_for(_row(kind="local"))
