"""Cookie 鉴权、改密和 WebSocket 短票接口。"""

import re
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import AuditLog, User
from ..schemas import ChangePasswordRequest, LoginRequest, UserOut
from ..security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_WS,
    create_token,
    hash_password,
    verify_password,
)
from ._common import client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE_NAME = "aieval_session"

# 登录失败限流：账号 + 来源 IP 维度滑动窗口。内存实现只能约束单副本，
# 多副本部署需换成 Redis 计数器（键结构保持不变即可平滑迁移）。
LOGIN_FAILURE_WINDOW_S = 300
LOGIN_MAX_FAILURES = 5
_MAX_TRACKED_IDENTITIES = 1000
_login_failures: dict[str, list[float]] = {}
_login_failures_lock = threading.Lock()


def _login_identity(username: str, ip: str) -> str:
    """限流键：账号 + 来源 IP，避免单账号被多 IP 撞库或单 IP 遍历账号。"""
    return f"{(username or '').strip().lower()}|{ip}"


def _prune_login_failures(now: float) -> None:
    """窗口外记录在读取时清理，避免长期运行累积内存。"""
    expired = [key for key, stamps in _login_failures.items() if not stamps or now - stamps[-1] > LOGIN_FAILURE_WINDOW_S]
    for key in expired:
        _login_failures.pop(key, None)


def _recent_login_failures(key: str) -> list[float]:
    now = time.monotonic()
    with _login_failures_lock:
        if len(_login_failures) > _MAX_TRACKED_IDENTITIES:
            _prune_login_failures(now)
        stamps = [stamp for stamp in _login_failures.get(key, []) if now - stamp < LOGIN_FAILURE_WINDOW_S]
        if stamps:
            _login_failures[key] = stamps
        else:
            _login_failures.pop(key, None)
        return stamps


def _record_login_failure(key: str) -> None:
    now = time.monotonic()
    with _login_failures_lock:
        stamps = [stamp for stamp in _login_failures.get(key, []) if now - stamp < LOGIN_FAILURE_WINDOW_S]
        stamps.append(now)
        _login_failures[key] = stamps


def _clear_login_failures(key: str) -> None:
    with _login_failures_lock:
        _login_failures.pop(key, None)


def _reset_login_rate_limits() -> None:
    """清空限流状态（单测隔离用，不对外暴露）。"""
    with _login_failures_lock:
        _login_failures.clear()


def _validate_password(password: str) -> None:
    """执行密码长度、字母和数字组成的统一校验。"""
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise AppError(ErrorCode.VALIDATION, "密码至少 8 位且包含字母和数字")


def _set_access_cookie(response: Response, user: User) -> None:
    """签发 12 小时 HttpOnly 登录 Cookie，浏览器脚本无法读取其内容。"""
    token = create_token(
        user.id,
        user.auth_version,
        TOKEN_TYPE_ACCESS,
        settings.access_token_expire_minutes,
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """验证账号后写入登录审计，并返回受 Cookie 保护的成员信息。"""
    ip = client_ip(request)
    identity = _login_identity(body.username, ip)
    # 锁定先于校验：命中阈值后即使密码正确也拒绝，避免限流被成功分支绕过。
    if len(_recent_login_failures(identity)) >= LOGIN_MAX_FAILURES:
        raise AppError(ErrorCode.RATE_LIMITED, "登录失败次数过多，请 5 分钟后再试")
    user = db.query(User).filter(User.username == body.username).first()
    if not user or user.disabled or not verify_password(body.password, user.password_hash):
        _record_login_failure(identity)
        db.add(
            AuditLog(
                action="login_failed",
                detail={"username": body.username},
                ip=ip,
            )
        )
        db.commit()
        raise AppError(ErrorCode.UNAUTHORIZED, "用户名或密码错误", status_code=401)

    _clear_login_failures(identity)
    user.last_login_at = datetime.now(UTC)
    user.last_login_ip = ip
    db.add(
        AuditLog(
            user_id=user.id,
            action="login",
            target_type="user",
            target_id=user.id,
            detail={},
            ip=user.last_login_ip,
        )
    )
    db.commit()
    db.refresh(user)
    _set_access_cookie(response, user)
    return user


@router.post("/logout")
def logout(response: Response):
    """清除浏览器 Cookie，不干预已经排队或运行的任务。"""
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """供 SPA 刷新后恢复身份的当前成员接口。"""
    return user


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """校验旧密码后更新哈希并令旧登录 Cookie 立即失效。"""
    _validate_password(body.new_password)
    if not body.old_password or not verify_password(body.old_password, user.password_hash):
        raise AppError(ErrorCode.VALIDATION, "旧密码不正确", fields={"old_password": "旧密码不正确"})
    user.password_hash = hash_password(body.new_password)
    user.auth_version += 1
    db.add(
        AuditLog(
            user_id=user.id,
            action="password_change",
            target_type="user",
            target_id=user.id,
            detail={},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(user)
    _set_access_cookie(response, user)
    return {"ok": True}


@router.post("/ws-ticket")
def ws_ticket(user: User = Depends(get_current_user)):
    """签发五分钟单次短票，长期浏览器 Cookie 不进入 WS query。

    每张票携带唯一 ``jti``，WebSocket 建连时消费一次即作废，
    防止同一票据在有效期内被重复用于建立多个连接。
    """
    ticket = create_token(
        user.id,
        user.auth_version,
        TOKEN_TYPE_WS,
        settings.ws_ticket_expire_minutes,
        jti=uuid4().hex,
    )
    return {"ticket": ticket, "expires_in": settings.ws_ticket_expire_minutes * 60}
