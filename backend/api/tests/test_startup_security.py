"""启动安全守卫单测：生产 fail-fast、非生产只告警、存量部署不被误伤。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from app import startup_security as guard

STRONG_SECRET = "a" * 64
STRONG_PASSWORD = "Str0ng-Bootstrap-Pass"


@dataclass
class _Cfg:
    """配置替身：只包含守卫依赖的字段。"""

    app_env: str = "production"
    secret_key: str = STRONG_SECRET
    bootstrap_admin_password: str = STRONG_PASSWORD
    key_encryption_key: str = "kek-configured"
    cookie_secure: bool = True


def _codes(findings: list[guard.SecurityFinding]) -> dict[str, bool]:
    return {item.code: item.fatal for item in findings}


@pytest.mark.parametrize("value", ["production", "PROD", "  Production  "])
def test_is_production_normalizes_value(value: str) -> None:
    assert guard.is_production(value)


@pytest.mark.parametrize("value", ["", None, "development", "test", "staging"])
def test_non_production_values(value: str | None) -> None:
    assert not guard.is_production(value)


def test_safe_production_config_has_no_findings() -> None:
    assert guard.collect_config_findings(_Cfg()) == []
    guard.enforce([])


@pytest.mark.parametrize(
    "secret",
    ["", "dev-secret-change-me", "change_me_to_a_random_secret", "short-but-random-31-chars-xxxxx"],
)
def test_weak_secret_key_is_fatal_in_production(secret: str) -> None:
    findings = guard.collect_config_findings(_Cfg(secret_key=secret))
    assert _codes(findings) == {"SECRET_KEY_WEAK": True}
    with pytest.raises(guard.InsecureStartupError) as exc_info:
        guard.enforce(findings)
    assert "SECRET_KEY_WEAK" in str(exc_info.value)
    # 异常与日志只给检查项编码，不回显密钥原文。
    if secret:
        assert secret not in str(exc_info.value)


def test_weak_secret_key_only_warns_outside_production(caplog: pytest.LogCaptureFixture) -> None:
    findings = guard.collect_config_findings(
        _Cfg(app_env="development", secret_key="dev-secret-change-me", cookie_secure=False)
    )
    # 非生产不提示 Cookie Secure（本地开发通常是 HTTP）。
    assert _codes(findings) == {"SECRET_KEY_WEAK": False}
    with caplog.at_level(logging.WARNING, logger="ai-eval.startup-security"):
        guard.enforce(findings)
    assert "SECRET_KEY_WEAK" in caplog.text
    assert "dev-secret-change-me" not in caplog.text


def test_empty_kek_and_insecure_cookie_never_block_startup() -> None:
    """KEK 为空、Cookie 未开 Secure 只告警：立即拒绝会破坏存量密文或 HTTP 入口。"""
    findings = guard.collect_config_findings(_Cfg(key_encryption_key="", cookie_secure=False))
    assert _codes(findings) == {"KEY_ENCRYPTION_KEY_EMPTY": False, "COOKIE_NOT_SECURE": False}
    guard.enforce(findings)


def test_fresh_admin_with_weak_password_is_fatal_in_production() -> None:
    finding = guard.bootstrap_admin_finding(
        _Cfg(bootstrap_admin_password="admin123"),
        admin_exists=False,
        admin_uses_bootstrap_password=False,
    )
    assert finding is not None and finding.fatal
    with pytest.raises(guard.InsecureStartupError):
        guard.enforce([finding])


def test_fresh_admin_with_weak_password_only_warns_in_development() -> None:
    finding = guard.bootstrap_admin_finding(
        _Cfg(app_env="development", bootstrap_admin_password="admin123"),
        admin_exists=False,
        admin_uses_bootstrap_password=False,
    )
    assert finding is not None and not finding.fatal
    guard.enforce([finding])


def test_existing_admin_still_on_default_password_only_warns() -> None:
    """存量部署：账号已存在且仍用默认口令时只告警，不能让生产起不来。"""
    finding = guard.bootstrap_admin_finding(
        _Cfg(bootstrap_admin_password="admin123"),
        admin_exists=True,
        admin_uses_bootstrap_password=True,
    )
    assert finding is not None
    assert finding.code == "BOOTSTRAP_ADMIN_STILL_DEFAULT"
    assert not finding.fatal


def test_existing_admin_already_changed_password_is_silent() -> None:
    assert guard.bootstrap_admin_finding(
        _Cfg(bootstrap_admin_password="admin123"),
        admin_exists=True,
        admin_uses_bootstrap_password=False,
    ) is None


def test_strong_bootstrap_password_is_silent() -> None:
    assert guard.bootstrap_admin_finding(
        _Cfg(), admin_exists=False, admin_uses_bootstrap_password=False
    ) is None


@pytest.mark.parametrize(
    "value", ["admin123", "ADMIN123", " admin ", "", "123456", "change_me_strong_admin_password"]
)
def test_weak_admin_password_detection(value: str) -> None:
    assert guard.is_weak_admin_password(value)


def test_lifespan_refuses_to_start_with_default_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """接线校验：生产 + 默认签名密钥时 lifespan 在任何引导动作之前即失败。"""
    from fastapi.testclient import TestClient

    from app import main as app_main

    monkeypatch.setattr(app_main.settings, "app_env", "production")
    monkeypatch.setattr(app_main.settings, "secret_key", "dev-secret-change-me")
    bootstrapped: list[str] = []
    monkeypatch.setattr(app_main, "_bootstrap_admin", lambda: bootstrapped.append("admin"))

    with pytest.raises(guard.InsecureStartupError, match="SECRET_KEY_WEAK"):
        with TestClient(app_main.app):
            pass
    assert bootstrapped == []
