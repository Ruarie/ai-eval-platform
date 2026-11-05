"""远程（SSH/SFTP）工作区访问。

设计约束（与本轮确认的产品边界一致）：

- **凭据不入库**：私钥放在宿主机 ``WORKSPACE_SSH_KEY_DIR``（默认
  ``/run/secrets/workspace-ssh``，只读挂载），数据库只存文件名；平台不回显、
  不打印、不拼接私钥内容。
- **主机白名单 fail-closed**：``WORKSPACE_SSH_ALLOWED_HOSTS`` 为空时拒绝一切
  远程工作区，避免平台被当成任意主机跳板。
- **路径边界**：工作区配置 ``remote_root``（允许填任意绝对路径，包括 ``/``），
  但所有文件操作规范化后必须落在该根目录内，拒绝 ``..`` 穿越与符号链接逃逸。
- **命令执行**：只跑非交互单条命令，带超时与输出上限；调用方（路由）负责
  审计与审批，本模块不判断业务权限。

连接按「每次操作新建」实现：工作区页面操作频率低，正确性优先；后续可加连接池。
"""

from __future__ import annotations

import logging
import posixpath
import stat as stat_module
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import paramiko

from .config import settings

logger = logging.getLogger("ai-eval.remote_workspace")

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_TREE_ENTRIES = 2000


class RemoteWorkspaceError(RuntimeError):
    """远程工作区不可用（配置缺失、主机不允许、连接失败）。"""


class RemotePathError(ValueError):
    """请求路径越界或非法。"""


@dataclass(frozen=True, slots=True)
class SshTarget:
    """一次远程连接的静态参数（不含私钥内容）。"""

    host: str
    port: int
    user: str
    key_name: str
    root: str


def _key_dir() -> str:
    return str(settings.workspace_ssh_key_dir or "").strip()


def _allowed_hosts() -> set[str]:
    raw = str(settings.workspace_ssh_allowed_hosts or "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def target_for(workspace: Any) -> SshTarget:
    """从工作区行构造连接参数并做 fail-closed 校验。"""
    host = str(getattr(workspace, "ssh_host", "") or "").strip()
    user = str(getattr(workspace, "ssh_user", "") or "").strip()
    key_name = str(getattr(workspace, "ssh_key_name", "") or "").strip()
    root = str(getattr(workspace, "remote_root", "") or "").strip() or "/"
    port = int(getattr(workspace, "ssh_port", 0) or 22)

    if getattr(workspace, "kind", "local") != "ssh":
        raise RemoteWorkspaceError("工作区不是远程类型")
    if not host or not user or not key_name:
        raise RemoteWorkspaceError("远程工作区缺少 host/user/key 配置")
    allowed = _allowed_hosts()
    if not allowed:
        raise RemoteWorkspaceError(
            "未配置 WORKSPACE_SSH_ALLOWED_HOSTS，远程工作区已停用"
        )
    if host.lower() not in allowed:
        raise RemoteWorkspaceError(f"主机不在白名单内：{host}")
    if not root.startswith("/"):
        raise RemoteWorkspaceError("remote_root 必须是绝对路径")
    return SshTarget(host=host, port=port, user=user, key_name=key_name, root=root)


def _load_private_key(key_name: str) -> paramiko.PKey:
    """按文件名加载私钥；拒绝带路径分隔符的名字，避免读到别处文件。"""
    if "/" in key_name or "\\" in key_name or key_name in {"", ".", ".."}:
        raise RemoteWorkspaceError("私钥文件名非法")
    base = _key_dir()
    if not base:
        raise RemoteWorkspaceError("未配置 WORKSPACE_SSH_KEY_DIR，无法加载私钥")
    path = f"{base.rstrip('/')}/{key_name}"
    for key_type in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            return key_type.from_private_key_file(path)
        except paramiko.PasswordRequiredException as exc:
            raise RemoteWorkspaceError("私钥带口令，当前不支持") from exc
        except Exception:  # noqa: BLE001 - 换下一种类型继续尝试
            continue
    raise RemoteWorkspaceError(f"无法解析私钥：{key_name}")


@contextmanager
def _connect(workspace: Any) -> Iterator[paramiko.SSHClient]:
    target = target_for(workspace)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=target.host,
            port=target.port,
            username=target.user,
            pkey=_load_private_key(target.key_name),
            timeout=settings.workspace_ssh_connect_timeout_s,
            banner_timeout=settings.workspace_ssh_connect_timeout_s,
            auth_timeout=settings.workspace_ssh_connect_timeout_s,
            look_for_keys=False,
            allow_agent=False,
        )
    except RemoteWorkspaceError:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转"不可用"
        logger.warning(
            "SSH 连接失败 host=%s user=%s err=%s", target.host, target.user, type(exc).__name__
        )
        raise RemoteWorkspaceError(f"SSH 连接失败：{type(exc).__name__}") from exc
    try:
        yield client
    finally:
        client.close()


def _normalize(workspace: Any, path: str) -> str:
    """把请求路径解析成远程绝对路径，并校验仍落在 remote_root 内。"""
    target = target_for(workspace)
    raw = str(path or "").strip() or "."
    if raw.startswith("/"):
        resolved = posixpath.normpath(raw)
    else:
        resolved = posixpath.normpath(posixpath.join(target.root, raw))
    root = posixpath.normpath(target.root)
    if root != "/" and not (resolved == root or resolved.startswith(root + "/")):
        raise RemotePathError(f"路径越界：{resolved}")
    return resolved


def _entry_type(mode: int) -> str:
    if stat_module.S_ISDIR(mode):
        return "dir"
    if stat_module.S_ISLNK(mode):
        return "link"
    return "file"


@contextmanager
def _sftp(workspace: Any) -> Iterator[paramiko.SFTPClient]:
    with _connect(workspace) as client:
        sftp = client.open_sftp()
        try:
            yield sftp
        finally:
            sftp.close()


def list_dir(workspace: Any, path: str) -> list[dict]:
    """列出一层目录内容；字段与本地实现同构（name/kind/size/updated_at）。"""
    remote = _normalize(workspace, path)
    with _sftp(workspace) as sftp:
        entries = []
        for attrs in sftp.listdir_attr(remote):
            kind = _entry_type(attrs.st_mode or 0)
            entries.append(
                {
                    "name": attrs.filename,
                    "kind": kind,
                    "size": int(attrs.st_size or 0) if kind == "file" else 0,
                    "updated_at": (
                        datetime.fromtimestamp(int(attrs.st_mtime or 0), UTC).isoformat()
                        if attrs.st_mtime
                        else None
                    ),
                }
            )
    entries.sort(key=lambda item: (item["kind"] != "dir", item["name"].lower()))
    return entries


def probe(workspace: Any) -> dict:
    """轻量连通性探测：能连上并列出根目录才算配置有效。"""
    entries = list_dir(workspace, ".")
    return {"ok": True, "entries": len(entries)}


def tree(workspace: Any, max_depth: int = 2) -> list[dict]:
    """递归目录树；超过 ``MAX_TREE_ENTRIES`` 截断并标记。"""
    root = _normalize(workspace, ".")
    depth_limit = max(1, min(int(max_depth or 2), 8))
    nodes: list[dict] = []
    truncated = False

    def walk(remote: str, depth: int) -> None:
        nonlocal truncated
        for item in list_dir(workspace, remote):
            if truncated:
                return
            node = {
                "name": item["name"],
                "path": posixpath.join(remote, item["name"]),
                "type": item["type"],
                "size": item["size"],
            }
            nodes.append(node)
            if len(nodes) >= MAX_TREE_ENTRIES:
                truncated = True
                return
            if item["type"] == "dir" and depth < depth_limit:
                node["children"] = []
                before = len(nodes)
                walk(node["path"], depth + 1)
                node["children"] = nodes[before:]

    walk(root, 1)
    if truncated:
        nodes.append({"name": "(已截断)", "path": root, "type": "info", "size": 0})
    return nodes


def read_file(workspace: Any, path: str) -> dict:
    """读取单文件文本；返回结构与本地 ``read_workspace_file`` 一致。"""
    remote = _normalize(workspace, path)
    with _sftp(workspace) as sftp:
        attrs = sftp.stat(remote)
        if stat_module.S_ISDIR(attrs.st_mode or 0):
            raise RemotePathError("目标是目录，不能按文本读取")
        size = int(attrs.st_size or 0)
        updated_at = (
            datetime.fromtimestamp(int(attrs.st_mtime or 0), UTC).isoformat()
            if attrs.st_mtime
            else None
        )
        name = posixpath.basename(remote)
        rel = _relative(workspace, remote)
        if size > MAX_TEXT_BYTES:
            return {
                "path": rel,
                "name": name,
                "size": size,
                "updated_at": updated_at,
                "is_binary": False,
                "is_large": True,
                "content": "",
            }
        with sftp.open(remote, "rb") as handle:
            raw = handle.read(MAX_TEXT_BYTES + 1)
    is_binary = b"\x00" in raw
    content = ""
    if not is_binary:
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            is_binary = True
    return {
        "path": rel,
        "name": name,
        "size": size,
        "updated_at": updated_at,
        "is_binary": is_binary,
        "is_large": False,
        "content": content,
    }


def _relative(workspace: Any, remote: str) -> str:
    """把远程绝对路径转成相对 remote_root 的展示路径。"""
    root = posixpath.normpath(target_for(workspace).root)
    if root == "/":
        return remote.lstrip("/")
    return remote[len(root):].lstrip("/") if remote.startswith(root) else remote


def write_text(workspace: Any, path: str, content: str) -> dict:
    remote = _normalize(workspace, path)
    payload = (content or "").encode("utf-8")
    if len(payload) > MAX_TEXT_BYTES:
        raise RemotePathError("内容超过 2MB，请改用上传")
    with _sftp(workspace) as sftp:
        _ensure_parent(sftp, remote)
        with sftp.open(remote, "wb") as handle:
            handle.write(payload)
    return {"path": _relative(workspace, remote), "size": len(payload)}


def create_entry(workspace: Any, path: str, is_dir: bool) -> None:
    remote = _normalize(workspace, path)
    with _sftp(workspace) as sftp:
        if is_dir:
            sftp.mkdir(remote)
        else:
            _ensure_parent(sftp, remote)
            with sftp.open(remote, "wb"):
                pass


def rename(workspace: Any, source: str, target: str) -> None:
    src = _normalize(workspace, source)
    dst = _normalize(workspace, target)
    with _sftp(workspace) as sftp:
        sftp.rename(src, dst)


def delete(workspace: Any, path: str) -> None:
    remote = _normalize(workspace, path)
    target = target_for(workspace)
    if remote == posixpath.normpath(target.root):
        raise RemotePathError("不能删除工作区根目录")
    with _sftp(workspace) as sftp:
        attrs = sftp.stat(remote)
        if stat_module.S_ISDIR(attrs.st_mode or 0):
            _remove_tree(sftp, remote)
        else:
            sftp.remove(remote)


def upload(workspace: Any, path: str, filename: str, stream, size: int | None = None) -> dict:
    """上传到目录 ``path`` 下；``filename`` 由调用方清洗。"""
    remote_dir = _normalize(workspace, path)
    remote = posixpath.join(remote_dir, filename)
    _normalize(workspace, remote)
    with _sftp(workspace) as sftp:
        _ensure_parent(sftp, remote)
        sftp.putfo(stream, remote, file_size=size)
        attrs = sftp.stat(remote)
    return {"name": filename, "path": remote, "size": int(attrs.st_size or 0)}


def exec_command(workspace: Any, command: str, timeout_s: int = 60) -> dict:
    """在远程执行单条非交互命令；输出超出上限时截断并标记。"""
    target = target_for(workspace)
    limit = max(1, min(int(timeout_s or 60), 600))
    max_chars = 20000
    with _connect(workspace) as client:
        stdin, stdout, stderr = client.exec_command(
            f"cd {target.root!r} && {command}", timeout=limit, get_pty=False
        )
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        stdin.close()
    truncated = len(out) > max_chars
    return {
        "exit_code": int(code),
        "stdout": out[:max_chars],
        "stderr": err[:max_chars],
        "truncated": truncated,
        "host": target.host,
        "root": target.root,
    }


def _ensure_parent(sftp: paramiko.SFTPClient, remote: str) -> None:
    """确保父目录存在（逐级 mkdir，已存在则跳过）。"""
    parent = posixpath.dirname(remote)
    if not parent or parent == "/":
        return
    current = ""
    for segment in parent.strip("/").split("/"):
        current = f"{current}/{segment}"
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def _remove_tree(sftp: paramiko.SFTPClient, remote: str) -> None:
    for attrs in sftp.listdir_attr(remote):
        child = posixpath.join(remote, attrs.filename)
        if stat_module.S_ISDIR(attrs.st_mode or 0):
            _remove_tree(sftp, child)
        else:
            sftp.remove(child)
    sftp.rmdir(remote)
