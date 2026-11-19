"""协议档归属与可见性守卫（平台模型 = 全员可用，个人模型 = 仅属主与管理端）。

约定：
- ``visibility == "platform"``：管理端维护的公共模型，所有成员可用，仅 admin 可改删；
- ``visibility == "personal"``：成员私有模型，仅属主可见/可用，admin 可治理（排障/清理）；
- 凭据只存在于受控环境文件，按 profile id 隔离，本模块只做访问控制，不读取 Key。
"""

from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from .errors import AppError, ErrorCode
from .models import ProtocolProfile, User

PLATFORM = "platform"
PERSONAL = "personal"


def is_admin(user: User | None) -> bool:
    """管理端账号判定：角色为 admin；历史行缺字段时按普通成员处理。"""
    return bool(user is not None and getattr(user, "role", None) == "admin")


def profile_visibility(profile: ProtocolProfile) -> str:
    """归一未落库 ORM 实例的 None 默认值；历史行缺少字段时按平台模型处理。"""
    return getattr(profile, "visibility", None) or PLATFORM


def can_view_profile(profile: ProtocolProfile, user: User | None) -> bool:
    """可见即可用：平台模型全员可见，个人模型仅属主可见，admin 可见全部。"""
    if is_admin(user):
        return True
    if profile_visibility(profile) == PLATFORM:
        return True
    return bool(user is not None and profile.owner_id == user.id)


def can_manage_profile(profile: ProtocolProfile, user: User | None) -> bool:
    """改删权限：平台模型只允许管理端，个人模型允许属主与管理端。"""
    if is_admin(user):
        return True
    return bool(
        user is not None
        and profile_visibility(profile) == PERSONAL
        and profile.owner_id == user.id
    )


def visible_profiles_query(db: Session, user: User) -> Query:
    """列表查询裁剪：平台模型 + 本人模型；管理端不过滤，便于统一治理。"""
    query = db.query(ProtocolProfile)
    if is_admin(user):
        return query
    return query.filter(
        or_(
            ProtocolProfile.visibility == PLATFORM,
            ProtocolProfile.owner_id == user.id,
        )
    )


def _load_profile(db: Session, profile_id: str) -> ProtocolProfile | None:
    """优先走 Session.get；最小测试替身只实现 query 链时保持兼容。"""
    getter = getattr(db, "get", None)
    if callable(getter):
        return getter(ProtocolProfile, profile_id)
    return db.query(ProtocolProfile).filter(ProtocolProfile.id == profile_id).first()


def require_visible_profile(db: Session, profile_id: str, user: User) -> ProtocolProfile:
    """按 ID 读取可见协议档；不可见与不存在统一返回 NOT_FOUND，避免侧信道。"""
    profile = _load_profile(db, profile_id)
    if profile is None or not can_view_profile(profile, user):
        raise AppError(ErrorCode.NOT_FOUND, "协议档不存在")
    return profile


def require_manageable_profile(db: Session, profile_id: str, user: User) -> ProtocolProfile:
    """按 ID 读取可改删协议档；无权操作返回 FORBIDDEN 语义的 DENIED。"""
    profile = require_visible_profile(db, profile_id, user)
    if not can_manage_profile(profile, user):
        raise AppError(ErrorCode.DENIED, "无权修改该协议档")
    return profile


def require_profile_usable(db: Session, profile_id: str, user_id: str) -> ProtocolProfile:
    """任务/对比入口只拿到 user_id 时的归属校验。"""
    user = db.get(User, user_id)
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户不可用", status_code=401)
    return require_visible_profile(db, profile_id, user)


def assert_create_scope(user: User, requested: str | None) -> str:
    """创建归属收敛：管理端可选平台/个人，普通成员只能创建个人模型。"""
    if requested is None:
        return PLATFORM if is_admin(user) else PERSONAL
    if requested not in {PLATFORM, PERSONAL}:
        raise AppError(ErrorCode.VALIDATION, "协议档归属不合法")
    if requested == PLATFORM and not is_admin(user):
        raise AppError(ErrorCode.DENIED, "仅管理端可创建平台模型")
    return requested
