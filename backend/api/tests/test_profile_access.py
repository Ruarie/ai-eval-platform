"""协议档归属与账号隔离的最小单元回归（不依赖数据库）。"""

from types import SimpleNamespace

import pytest

from app.errors import AppError, ErrorCode
from app.profile_access import (
    assert_create_scope,
    can_manage_profile,
    can_view_profile,
)


def _user(role: str = "member", user_id: str = "u1") -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=role, disabled=False)


def _profile(visibility: str, owner_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(id="p1", visibility=visibility, owner_id=owner_id)


def test_platform_profile_visible_to_all_but_managed_by_admin_only() -> None:
    """平台模型全员可用；普通成员不能改删管理端维护的模型。"""
    profile = _profile("platform")
    member = _user()
    admin = _user("admin", "u-admin")

    assert can_view_profile(profile, member)
    assert not can_manage_profile(profile, member)
    assert can_manage_profile(profile, admin)


def test_personal_profile_is_owner_scoped() -> None:
    """个人模型只有属主与管理端可见可用，其他成员按不存在处理。"""
    profile = _profile("personal", owner_id="u1")
    owner = _user("member", "u1")
    other = _user("member", "u2")
    admin = _user("admin", "u-admin")

    assert can_view_profile(profile, owner)
    assert can_manage_profile(profile, owner)
    assert not can_view_profile(profile, other)
    assert not can_manage_profile(profile, other)
    assert can_view_profile(profile, admin)
    assert can_manage_profile(profile, admin)


def test_create_scope_defaults_and_denies_member_platform_request() -> None:
    """默认归属：admin 建平台模型，成员建个人模型；成员显式建平台模型拒绝。"""
    assert assert_create_scope(_user("admin"), None) == "platform"
    assert assert_create_scope(_user(), None) == "personal"
    assert assert_create_scope(_user(), "personal") == "personal"
    with pytest.raises(AppError) as caught:
        assert_create_scope(_user(), "platform")
    assert caught.value.code == ErrorCode.DENIED
