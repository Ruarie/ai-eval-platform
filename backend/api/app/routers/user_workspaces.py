"""用户工作区域路由（F1/G1，设计文档 A V0.4.1 §4）。

- 工作区 = 用户自管数据域：列表/创建/改名/注销（软删）/purge（真删）；
- 注销 = 软删（``deleted_at`` 标记），purge 事务内先显式解绑
  ``sessions.workspace_id`` 引用（FK RESTRICT 兜底，禁 SET NULL），再删行删目录；
- 目录浏览/建文件夹经 ``workspace_service`` 的路径安全单一实现（防穿越 +
  逐段 realpath 前缀重验 + 符号链接拒绝）；
- 全部写操作落 AuditLog；删除竞态守卫见 §4.2（workspace 行锁先行，S 列为
  UPDATE 行锁随后——全局锁序 workspace → sessions）。
"""

from __future__ import annotations

import base64
import mimetypes
import os
import shutil
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import remote_workspace, workspace_exec_approval
from ..config import settings
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import Session as AgentSession
from ..models import User, Workspace
from ..workspace_service import (
    create_child_dir,
    create_workspace_file,
    delete_workspace_path,
    folder_summary,
    get_file_tree,
    list_dir_level,
    read_workspace_file,
    rename_workspace_path,
    resolve_scope_dir,
    resolve_scope_file,
    save_workspace_file_stream,
    validate_segment,
    workspace_dir_for,
    write_workspace_file,
)
from ._common import write_audit

router = APIRouter(prefix="/api/workspaces", tags=["user-workspaces"])


class _NameBody(BaseModel):
    """工作区创建/改名请求（name 每属主活跃唯一）。

    创建时可选 ``kind=ssh`` 打开远程工作区；改名只读取 ``name``。
    """

    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(default="local", max_length=16)
    # key_file：用服务端预置私钥；password：连接时由页面临时提供密码（不落库）。
    auth_type: str = Field(default="key_file", max_length=16)
    ssh_host: str | None = Field(default=None, max_length=200)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_user: str | None = Field(default=None, max_length=100)
    ssh_key_name: str | None = Field(default=None, max_length=200)
    remote_root: str | None = Field(default=None, max_length=500)


class _ExecBody(BaseModel):
    """远程命令执行请求（仅 ssh 工作区）。"""

    command: str = Field(min_length=1, max_length=4000)
    timeout_s: int = Field(default=60, ge=1, le=600)


class _FileBody(BaseModel):
    """新建文件夹请求：父目录相对路径（默认根）+ 单段目录名。"""

    path: str = Field(default="", max_length=1024)
    name: str = Field(min_length=1, max_length=255)


class _FileContentBody(BaseModel):
    """写回/更新文件内容请求。"""

    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(default="")


class _CreateFileBody(BaseModel):
    """新建单文件请求。"""

    path: str = Field(default="", max_length=1024)
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(default="")


class _RenamePathBody(BaseModel):
    """重命名文件或目录请求。"""

    path: str = Field(min_length=1, max_length=1024)
    new_name: str = Field(min_length=1, max_length=255)



def _owned_workspace(
    db: Session, user: User, workspace_id: str, *, require_active: bool = True, lock: bool = False
) -> Workspace:
    """按属主取工作区；非属主 403（UNAUTHORIZED），不存在 404。"""
    query = db.query(Workspace).filter(Workspace.id == workspace_id)
    if lock:
        # 上传与注销共用行锁，避免并发上传各自通过同一份剩余容量检查。
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "工作区不存在")
    if row.owner_id != user.id:
        raise AppError(ErrorCode.UNAUTHORIZED, "无权访问该工作区")
    if require_active and row.deleted_at is not None:
        raise AppError(ErrorCode.VALIDATION, "工作区已注销，不可操作（可在 legacy 目录中复活，随 F3）")
    return row


def _remote_app_error(exc: Exception) -> AppError:
    """远程错误映射：需要用户补齐的（密码/私钥/白名单）→ 400，连接类 → 502。"""
    message = str(exc)
    fixable = ("输入 SSH 密码", "白名单", "私钥", "缺少", "不支持", "非法")
    code = ErrorCode.VALIDATION if any(token in message for token in fixable) else ErrorCode.UPSTREAM
    return AppError(code, message)


def _remote_call(fn: Any, *args: Any) -> Any:
    """统一的远程调用包装：把 SSH 层的两类异常映射成平台错误码。"""
    try:
        return fn(*args)
    except remote_workspace.RemotePathError as exc:
        raise AppError(ErrorCode.VALIDATION, str(exc)) from exc
    except remote_workspace.RemoteWorkspaceError as exc:
        raise _remote_app_error(exc) from exc


def _ssh_password(encoded: str | None) -> str:
    """解析请求头里的临时 SSH 密码（base64 传输，避免 header 非法字符）。

    密码**不落库、不写日志**：只在本次请求内传给 remote_workspace。
    """
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode("ascii"), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise AppError(ErrorCode.VALIDATION, "SSH 密码编码非法（需 base64）") from None


def _is_ssh(row: Workspace) -> bool:
    """工作区是否为远程 SSH 类型（旧行没有该列值时按 local 处理）。"""
    return getattr(row, "kind", "local") == "ssh"


def _require_local(row: Workspace, action: str) -> None:
    """本地专属操作遇到远程工作区时明确拒绝，绝不回落到本地空目录。"""
    if _is_ssh(row):
        raise AppError(ErrorCode.VALIDATION, f"远程工作区暂不支持{action}")


def _workspace_item(row: Workspace) -> dict[str, Any]:
    """投影工作区元数据、实际配置配额与目录用量（远程库不统计本地目录）。"""
    remote = _is_ssh(row)
    summary = {"files": 0, "bytes": 0} if remote else folder_summary(workspace_dir_for(row.id))
    return {
        "id": row.id,
        "name": row.name,
        "owner_id": row.owner_id,
        "kind": "ssh" if remote else "local",
        "auth_type": getattr(row, "auth_type", None) or "key_file",
        # 旧行/测试夹具可能没有这些列，用 getattr 兜底，避免投影直接炸。
        "ssh_host": getattr(row, "ssh_host", None),
        "ssh_port": getattr(row, "ssh_port", None),
        "ssh_user": getattr(row, "ssh_user", None),
        "ssh_key_name": getattr(row, "ssh_key_name", None),
        "remote_root": getattr(row, "remote_root", None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "deleted": row.deleted_at is not None,
        "quota_bytes": settings.workspace_quota_bytes,
        "folder": summary,
    }


@router.get("")
def list_workspaces(
    include_deleted: bool = Query(default=False, description="是否包含已注销工作区"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """列出当前用户的工作区（默认活跃行；行态随 deleted 字段暴露）。"""
    query = db.query(Workspace).filter(Workspace.owner_id == user.id)
    if not include_deleted:
        query = query.filter(Workspace.deleted_at.is_(None))
    total = query.count()
    rows = query.order_by(Workspace.updated_at.desc(), Workspace.id.asc()).offset(offset).limit(limit).all()
    return {"items": [_workspace_item(row) for row in rows], "total": total}


@router.post("", status_code=201)
def create_workspace(
    body: _NameBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """新建工作区：表 + 数据目录（``data/workspaces/<uuid>``）原子创建。"""
    name = body.name.strip()
    if not name:
        raise AppError(ErrorCode.VALIDATION, "工作区名称不能为空")
    # 活跃同名预检（每属主活跃唯一；软删同名行允许存在——复活路径 F3 语义）
    duplicate = (
        db.query(Workspace.id)
        .filter(
            Workspace.owner_id == user.id,
            Workspace.name == name,
            Workspace.deleted_at.is_(None),
        )
        .first()
    )
    if duplicate:
        raise AppError(ErrorCode.VALIDATION, "已存在同名工作区")
    kind = (body.kind or "local").strip().lower()
    if kind not in {"local", "ssh"}:
        raise AppError(ErrorCode.VALIDATION, "工作区类型无效")
    if kind == "ssh":
        return _create_remote_workspace(db, request, user, name, body)

    row = Workspace(owner_id=user.id, name=name)
    directory = ""
    try:
        db.add(row)
        db.flush()
        directory = workspace_dir_for(row.id)
        os.makedirs(directory, exist_ok=False)
        write_audit(db, request, user, action="workspace_create", target_type="workspace", target_id=row.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        if directory:
            shutil.rmtree(directory, ignore_errors=True)
        raise AppError(ErrorCode.VALIDATION, "已存在同名工作区") from None
    except OSError as exc:
        db.rollback()
        raise AppError(ErrorCode.INTERNAL, "工作区目录创建失败") from exc
    return _workspace_item(row)


def _create_remote_workspace(
    db: Session, request: Request, user: User, name: str, body: _NameBody
) -> dict[str, Any]:
    """创建 SSH 工作区：先校验白名单与私钥可用性，再落库（不建本地目录）。"""
    host = (body.ssh_host or "").strip()
    ssh_user = (body.ssh_user or "").strip()
    key_name = (body.ssh_key_name or "").strip()
    root = (body.remote_root or "").strip() or "/"
    auth_type = (body.auth_type or "key_file").strip().lower()
    if auth_type not in {"key_file", "password"}:
        raise AppError(ErrorCode.VALIDATION, "认证方式无效")
    if not host or not ssh_user:
        raise AppError(ErrorCode.VALIDATION, "远程工作区需要填写主机与登录用户")
    if auth_type == "key_file" and not key_name:
        raise AppError(ErrorCode.VALIDATION, "私钥认证需要填写私钥文件名")

    row = Workspace(
        owner_id=user.id,
        name=name,
        kind="ssh",
        auth_type=auth_type,
        ssh_host=host,
        ssh_port=body.ssh_port or 22,
        ssh_user=ssh_user,
        ssh_key_name=key_name or None,
        remote_root=root,
    )
    if auth_type == "key_file":
        try:
            # 私钥模式创建时就能验证连通性；密码模式要等用户首次输入密码再验。
            remote_workspace.probe(row)
        except remote_workspace.RemoteWorkspaceError as exc:
            raise AppError(ErrorCode.VALIDATION, str(exc)) from exc
        except remote_workspace.RemotePathError as exc:
            raise AppError(ErrorCode.VALIDATION, f"远程目录不可用：{exc}") from exc

    try:
        db.add(row)
        db.flush()
        write_audit(
            db, request, user,
            action="workspace_create",
            target_type="workspace", target_id=row.id,
            detail={"kind": "ssh", "host": host},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(ErrorCode.VALIDATION, "已存在同名工作区") from None
    return _workspace_item(row)


@router.put("/{workspace_id}")
def rename_workspace(
    workspace_id: str,
    body: _NameBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """工作区改名（活跃行；每属主活跃唯一）。"""
    row = _owned_workspace(db, user, workspace_id)
    name = body.name.strip()
    if not name:
        raise AppError(ErrorCode.VALIDATION, "工作区名称不能为空")
    duplicate = (
        db.query(Workspace.id)
        .filter(
            Workspace.owner_id == user.id,
            Workspace.name == name,
            Workspace.deleted_at.is_(None),
            Workspace.id != workspace_id,
        )
        .first()
    )
    if duplicate:
        raise AppError(ErrorCode.VALIDATION, "已存在同名工作区")
    row.name = name
    write_audit(db, request, user, action="workspace_rename", target_type="workspace", target_id=row.id)
    db.commit()
    return _workspace_item(row)


@router.delete("/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    request: Request,
    purge: bool = Query(default=False, description="purge=true 真删行与目录（需先注销）"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """注销 = 软删（默认）；purge = 显式解绑引用后真删行 + 目录树。"""
    row = (
        db.query(Workspace)
        .filter(Workspace.id == workspace_id)
        .with_for_update()
        .first()
    )
    if row is None:
        raise AppError(ErrorCode.NOT_FOUND, "工作区不存在")
    if row.owner_id != user.id:
        raise AppError(ErrorCode.UNAUTHORIZED, "无权访问该工作区")

    if not purge:
        if row.deleted_at is not None:
            return {"ok": True, "id": workspace_id, "deleted": True}
        row.deleted_at = datetime.now(UTC)
        write_audit(db, request, user, action="workspace_delete", target_type="workspace", target_id=workspace_id)
        db.commit()
        return {"ok": True, "id": workspace_id, "deleted": True}

    # purge：须先经软删（防误触）；行锁已取（workspace → sessions 锁序首行）。
    if row.deleted_at is None:
        raise AppError(ErrorCode.VALIDATION, "purge 前必须先注销工作区（软删）")
    active_bound = (
        db.query(AgentSession.id)
        .filter(
            AgentSession.workspace_id == workspace_id,
            AgentSession.deleted_at.is_(None),
        )
        .first()
    )
    if active_bound:
        raise AppError(
            ErrorCode.CONCURRENCY, "存在活跃绑定会话，禁止 purge（请先结束相关会话）"
        )
    # 显式解绑全部引用（含软删会话行；FK RESTRICT 兜底，绝不用 SET NULL）。
    # 先取解绑会话 id 清单供审计追溯（P2：补 workspace_unbind 语义到 detail）。
    bound_rows = (
        db.query(AgentSession.id)
        .filter(AgentSession.workspace_id == workspace_id)
        .all()
    )
    unbound_ids = [str(row[0]) for row in bound_rows]
    if unbound_ids:
        db.execute(
            update(AgentSession)
            .where(AgentSession.workspace_id == workspace_id)
            .values(workspace_id=None, scope_path=None)
        )
    directory = workspace_dir_for(workspace_id)
    write_audit(
        db,
        request,
        user,
        action="workspace_purge",
        target_type="workspace", target_id=workspace_id,
        detail={
            "unbound_sessions": len(unbound_ids),
            "session_ids": unbound_ids,
            "path": directory,
        },
    )
    db.delete(row)
    db.commit()
    # 事务提交后再清理目录（P5 修复）：行删除是唯一事务事实；目录删除失败
    # 不伪装成功——残留目录进入孤儿清理面兜底，响应明示 residual_dir。
    residual_dir = False
    try:
        shutil.rmtree(directory)
    except OSError:
        residual_dir = True
    return {
        "ok": True,
        "id": workspace_id,
        "purged": True,
        "unbound_sessions": len(unbound_ids),
        "residual_dir": residual_dir,
    }


@router.get("/{workspace_id}/files")
def list_files(
    workspace_id: str,
    path: str = Query(default="", description="相对 scope（空=根）"),
    db: Session = Depends(get_db),
    ssh_password: str | None = Header(default=None, alias="X-Workspace-SSH-Password"),
    user: User = Depends(get_current_user),
):
    """一层目录列表 + 当前相对路径（目录进入式浏览，防穿越）。"""
    row = _owned_workspace(db, user, workspace_id)
    if _is_ssh(row):
        entries = _remote_call(remote_workspace.list_dir, row, path, _ssh_password(ssh_password))
        return {
            "workspace_id": workspace_id,
            "path": path,
            "entries": entries,
            "total": len(entries),
        }
    directory = workspace_dir_for(row.id)
    entries = list_dir_level(directory, path)
    return {
        "workspace_id": workspace_id,
        "path": path,
        "entries": entries,
        "total": len(entries),
    }


@router.post("/{workspace_id}/files", status_code=201)
def create_folder(
    workspace_id: str,
    body: _FileBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """在工作区相对路径下新建单段文件夹（父目录须已存在）。"""
    row = _owned_workspace(db, user, workspace_id)
    _require_local(row, "新建文件夹")
    directory = workspace_dir_for(row.id)
    parent = resolve_scope_dir(directory, body.path)
    target = create_child_dir(parent, body.name.strip() or body.name)
    write_audit(
        db,
        request,
        user,
        action="workspace_folder_create",
        target_type="workspace", target_id=workspace_id,
        detail={"path": os.path.join(body.path, body.name).lstrip("./")},
    )
    db.commit()
    rel = os.path.join(body.path, os.path.basename(target)).replace("\\", "/")
    return {"ok": True, "path": rel.lstrip("./")}


@router.get("/{workspace_id}/files/tree")
def get_tree(
    workspace_id: str,
    max_depth: int = Query(default=4, ge=1, le=8),
    db: Session = Depends(get_db),
    ssh_password: str | None = Header(default=None, alias="X-Workspace-SSH-Password"),
    user: User = Depends(get_current_user),
):
    """获取工作区目录树结构。"""
    row = _owned_workspace(db, user, workspace_id)
    if _is_ssh(row):
        return {
            "workspace_id": workspace_id,
            "tree": _remote_call(remote_workspace.tree, row, max_depth, _ssh_password(ssh_password)),
        }
    directory = workspace_dir_for(row.id)
    tree = get_file_tree(directory, max_depth=max_depth)
    return {"workspace_id": workspace_id, "tree": tree}


@router.get("/{workspace_id}/files/content")
def get_file_content(
    workspace_id: str,
    path: str = Query(..., min_length=1, description="文件相对路径"),
    db: Session = Depends(get_db),
    ssh_password: str | None = Header(default=None, alias="X-Workspace-SSH-Password"),
    user: User = Depends(get_current_user),
):
    """获取单文件文本内容与元信息。超大或二进制文件安全标记。"""
    row = _owned_workspace(db, user, workspace_id)
    if _is_ssh(row):
        return {
            "workspace_id": workspace_id,
            **_remote_call(remote_workspace.read_file, row, path, _ssh_password(ssh_password)),
        }
    directory = workspace_dir_for(row.id)
    result = read_workspace_file(directory, path)
    return {"workspace_id": workspace_id, **result}


@router.put("/{workspace_id}/files/content")
def update_file_content(
    workspace_id: str,
    body: _FileContentBody,
    request: Request,
    db: Session = Depends(get_db),
    ssh_password: str | None = Header(default=None, alias="X-Workspace-SSH-Password"),
    user: User = Depends(get_current_user),
):
    """写回/保存文件内容。"""
    row = _owned_workspace(db, user, workspace_id)
    if _is_ssh(row):
        res = _remote_call(
            remote_workspace.write_text,
            row, body.path, body.content, _ssh_password(ssh_password),
        )
        write_audit(
            db, request, user,
            action="workspace_file_update",
            target_type="workspace", target_id=workspace_id,
            detail={"path": res["path"], "size": res["size"], "kind": "ssh"},
        )
        db.commit()
        return {"ok": True, "workspace_id": workspace_id, **res}
    directory = workspace_dir_for(row.id)
    res = write_workspace_file(directory, body.path, body.content)
    write_audit(
        db,
        request,
        user,
        action="workspace_file_update",
        target_type="workspace", target_id=workspace_id,
        detail={"path": res["path"], "size": res["size"]},
    )
    db.commit()
    return {"ok": True, "workspace_id": workspace_id, **res}


@router.post("/{workspace_id}/files/file", status_code=201)
def create_file(
    workspace_id: str,
    body: _CreateFileBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """在指定相对路径下新建单文件。"""
    row = _owned_workspace(db, user, workspace_id)
    _require_local(row, "新建文件")
    directory = workspace_dir_for(row.id)
    res = create_workspace_file(directory, body.path, body.name.strip(), body.content)
    write_audit(
        db,
        request,
        user,
        action="workspace_file_create",
        target_type="workspace", target_id=workspace_id,
        detail={"path": res["path"], "name": res["name"]},
    )
    db.commit()
    return {"ok": True, "workspace_id": workspace_id, **res}


@router.patch("/{workspace_id}/files/rename")
def rename_item(
    workspace_id: str,
    body: _RenamePathBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """重命名工作区内的文件或目录。"""
    row = _owned_workspace(db, user, workspace_id)
    _require_local(row, "重命名")
    directory = workspace_dir_for(row.id)
    res = rename_workspace_path(directory, body.path, body.new_name.strip())
    write_audit(
        db,
        request,
        user,
        action="workspace_file_rename",
        target_type="workspace", target_id=workspace_id,
        detail={"old_path": res["old_path"], "new_path": res["new_path"]},
    )
    db.commit()
    return {"ok": True, "workspace_id": workspace_id, **res}


@router.delete("/{workspace_id}/files")
def delete_item(
    workspace_id: str,
    path: str = Query(..., min_length=1, description="相对路径"),
    request: Request = None,
    db: Session = Depends(get_db),
    ssh_password: str | None = Header(default=None, alias="X-Workspace-SSH-Password"),
    user: User = Depends(get_current_user),
):
    """删除工作区内的文件或目录（拒绝删除工作区根）。"""
    row = _owned_workspace(db, user, workspace_id)
    if _is_ssh(row):
        _remote_call(remote_workspace.delete, row, path, _ssh_password(ssh_password))
        write_audit(
            db, request, user,
            action="workspace_file_delete",
            target_type="workspace", target_id=workspace_id,
            detail={"path": path, "kind": "ssh"},
        )
        db.commit()
        return {"ok": True, "workspace_id": workspace_id}
    directory = workspace_dir_for(row.id)
    res = delete_workspace_path(directory, path)
    write_audit(
        db,
        request,
        user,
        action="workspace_file_delete",
        target_type="workspace", target_id=workspace_id,
        detail={"path": res["path"]},
    )
    db.commit()
    return {"ok": True, "workspace_id": workspace_id, **res}


VIDEO_AUDIO_MIME_MAP: dict[str, str] = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "webm": "video/webm",
    "ogv": "video/ogg",
    "ogg": "video/ogg",
    "mov": "video/quicktime",
    "mkv": "video/x-matroska",
    "avi": "video/x-msvideo",
    "flv": "video/x-flv",
    "wmv": "video/x-ms-wmv",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "flac": "audio/flac",
    "aac": "audio/aac",
    "m4a": "audio/mp4",
    "weba": "audio/webm",
}


@router.get("/{workspace_id}/files/raw")
def get_raw_file(
    workspace_id: str,
    path: str = Query(..., min_length=1, description="相对路径"),
    download: bool = Query(False, description="是否强制以附件形式下载"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """以原始二进制/文件流方式返回文件（供图片/音视频预览或文件下载）。"""
    row = _owned_workspace(db, user, workspace_id)
    _require_local(row, "原文件下载")
    directory = workspace_dir_for(row.id)
    abs_path = resolve_scope_file(directory, path, must_exist=True)

    media_type, _ = mimetypes.guess_type(abs_path)
    ext = os.path.splitext(abs_path)[1].lower().lstrip(".")
    if ext in VIDEO_AUDIO_MIME_MAP:
        media_type = VIDEO_AUDIO_MIME_MAP[ext]

    disposition = "attachment" if download else "inline"
    return FileResponse(
        abs_path,
        filename=os.path.basename(abs_path),
        media_type=media_type or "application/octet-stream",
        content_disposition_type=disposition,
        # 用户文件可含 HTML/SVG；文档直接打开时禁止脚本与平台同源权限。
        headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{workspace_id}/files/upload", status_code=201)
def upload_file(
    workspace_id: str,
    file: UploadFile = File(..., description="上传的文件对象"),
    path: str = Form(default="", description="保存的目标父目录相对路径"),
    request: Request = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """在线程池中分块保存上传文件，工作区行锁保护上传配额核验与替换。"""
    row = _owned_workspace(db, user, workspace_id, lock=True)
    _require_local(row, "上传")
    directory = workspace_dir_for(row.id)

    raw_filename = file.filename or "uploaded_file"
    clean_name = os.path.basename(raw_filename.replace("\\", "/")).strip()
    if not clean_name or clean_name in (".", ".."):
        raise AppError(ErrorCode.VALIDATION, "非法的文件名称")
    validate_segment(clean_name)

    clean_parent = (path or "").strip("/").replace("\\", "/")

    target_item = resolve_scope_file(directory, f"{clean_parent}/{clean_name}", must_exist=False)
    if os.path.isdir(target_item):
        raise AppError(ErrorCode.VALIDATION, "目标为目录而非文件")
    quota = int(getattr(settings, "workspace_quota_bytes", 1024 * 1024 * 1024))
    available_bytes = None
    if quota > 0:
        summary = folder_summary(directory) or {"total_bytes": 0}
        existing_file_size = os.path.getsize(target_item) if os.path.isfile(target_item) else 0
        available_bytes = quota - summary["total_bytes"] + existing_file_size
        if available_bytes < 0 or (file.size is not None and file.size > available_bytes):
            raise AppError(ErrorCode.VALIDATION, f"工作区容量超出配额上限（上限 {quota // (1024 * 1024)}MB）")

    res = save_workspace_file_stream(directory, clean_parent, clean_name, file.file, max_bytes=available_bytes)
    write_audit(
        db,
        request,
        user,
        action="workspace_file_upload",
        target_type="workspace",
        target_id=workspace_id,
        detail={"path": res["path"], "name": res["name"], "size": res["size"]},
    )
    db.commit()
    return {"ok": True, "workspace_id": workspace_id, **res}


@router.post("/{workspace_id}/exec", status_code=202)
def request_remote_exec(
    workspace_id: str,
    body: _ExecBody,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """登记一条待确认的远程命令（不执行）。

    远程 `exec` 等价于在该主机上开一个 shell：必须让用户先看到「主机 + 根目录 +
    完整命令」再确认，避免一次误调用就把命令下发到生产机。
    """
    row = _owned_workspace(db, user, workspace_id)
    if not _is_ssh(row):
        raise AppError(ErrorCode.VALIDATION, "仅远程工作区支持命令执行")
    try:
        target = remote_workspace.target_for(row)
    except remote_workspace.RemoteWorkspaceError as exc:
        raise AppError(ErrorCode.VALIDATION, str(exc)) from exc

    pending = workspace_exec_approval.create(
        workspace_id=workspace_id,
        user_id=user.id,
        command=body.command,
        timeout_s=body.timeout_s,
        host=target.host,
        root=target.root,
    )
    write_audit(
        db, request, user,
        action="workspace_remote_exec_request",
        target_type="workspace", target_id=workspace_id,
        detail={
            "approval_id": pending.approval_id,
            "command": body.command[:200],
            "host": target.host,
        },
    )
    db.commit()
    return {
        "approval_id": pending.approval_id,
        "status": "pending",
        "expires_in_s": pending.expires_in_s,
        "preview": {
            "host": target.host,
            "root": target.root,
            "command": body.command,
            "timeout_s": body.timeout_s,
        },
    }


@router.post("/{workspace_id}/exec/{approval_id}/confirm")
def confirm_remote_exec(
    workspace_id: str,
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    ssh_password: str | None = Header(default=None, alias="X-Workspace-SSH-Password"),
    user: User = Depends(get_current_user),
):
    """确认并执行待审批命令；一条命令只能被执行一次。"""
    pending = workspace_exec_approval.pop(
        approval_id, workspace_id=workspace_id, user_id=user.id
    )
    if pending is None:
        raise AppError(ErrorCode.VALIDATION, "待确认命令不存在、已执行或已过期")
    row = _owned_workspace(db, user, workspace_id)
    if not _is_ssh(row):
        raise AppError(ErrorCode.VALIDATION, "仅远程工作区支持命令执行")
    result = _remote_call(
        remote_workspace.exec_command,
        row, pending.command, pending.timeout_s, _ssh_password(ssh_password),
    )
    write_audit(
        db, request, user,
        action="workspace_remote_exec",
        target_type="workspace", target_id=workspace_id,
        detail={
            "approval_id": approval_id,
            "command": pending.command[:200],
            "exit_code": result["exit_code"],
            "host": result["host"],
        },
    )
    db.commit()
    return {"approval_id": approval_id, "workspace_id": workspace_id, **result}


@router.post("/{workspace_id}/exec/{approval_id}/reject")
def reject_remote_exec(
    workspace_id: str,
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """拒绝待确认命令（不执行，写审计）。"""
    pending = workspace_exec_approval.pop(
        approval_id, workspace_id=workspace_id, user_id=user.id
    )
    if pending is None:
        raise AppError(ErrorCode.VALIDATION, "待确认命令不存在、已执行或已过期")
    write_audit(
        db, request, user,
        action="workspace_remote_exec_reject",
        target_type="workspace", target_id=workspace_id,
        detail={"approval_id": approval_id, "command": pending.command[:200]},
    )
    db.commit()
    return {"approval_id": approval_id, "status": "rejected"}
