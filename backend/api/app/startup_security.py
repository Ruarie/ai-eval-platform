"""生产启动安全守卫：拦截默认密钥、弱引导口令等「能跑但不安全」的配置。

背景（代码质量报告 S1/S2/S3）：``SECRET_KEY``、引导管理员口令等都有可直接
启动的默认值，生产是否安全完全取决于运维是否记得修改。本模块在 lifespan
早期统一检查，按严重程度分两档：

- **致命（fatal）**：生产环境下直接阻止启动（fail-fast），例如 JWT 签名密钥
  仍为公开默认值、全新部署要用弱口令创建引导管理员；
- **告警（warning）**：只记日志，不阻止启动。用于「立即拒绝会破坏存量部署
  或存量数据」的项，例如 KEK 为空（已有密文由派生密钥加密，贸然切换会解不开）、
  Cookie 未开 Secure（HTTP 入口仍在使用）、存量管理员仍在用默认口令。

非生产环境（``APP_ENV`` 不是 production/prod）只告警，不阻止本地开发与测试。
本模块只输出检查项编码与说明，**绝不**把密钥或口令原文写进日志或异常。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("ai-eval.startup-security")

# 公开出现在仓库（config 默认值、compose 默认值、.env.example 占位）中的签名密钥。
KNOWN_WEAK_SECRET_KEYS = frozenset({
    "",
    "dev-secret-change-me",
    "change_me_to_a_random_secret",
})
# JWT HS256 签名密钥最短长度；server-setup 生成的 hex(32) 为 64 位。
MIN_SECRET_KEY_LENGTH = 32
# 公开出现在仓库或常见弱口令中的引导管理员口令。
KNOWN_WEAK_ADMIN_PASSWORDS = frozenset({
    "",
    "admin",
    "admin123",
    "password",
    "123456",
    "12345678",
    "change_me",
    # .env.example 中的占位值：原样复制示例文件即视为未修改。
    "change_me_strong_admin_password",
})
PRODUCTION_ENVS = frozenset({"production", "prod"})


class _SecuritySettings(Protocol):
    """守卫只依赖的配置字段（便于单测传入替身对象）。"""

    app_env: str
    secret_key: str
    bootstrap_admin_password: str
    key_encryption_key: str
    cookie_secure: bool


@dataclass(frozen=True)
class SecurityFinding:
    """一条启动安全检查结果；``message`` 不得包含任何密钥或口令原文。"""

    code: str
    message: str
    fatal: bool


class InsecureStartupError(RuntimeError):
    """生产环境存在致命安全配置时抛出，阻止 API 进程启动。"""


def is_production(app_env: str | None) -> bool:
    """``APP_ENV`` 是否为生产环境（大小写与首尾空白不敏感）。"""
    return str(app_env or "").strip().lower() in PRODUCTION_ENVS


def is_weak_secret_key(value: str | None) -> bool:
    """签名密钥是否为公开默认值或长度不足。"""
    key = (value or "").strip()
    return key in KNOWN_WEAK_SECRET_KEYS or len(key) < MIN_SECRET_KEY_LENGTH


def is_weak_admin_password(value: str | None) -> bool:
    """引导管理员口令是否为公开默认值或常见弱口令（不做强度打分，只拦已知值）。"""
    return (value or "").strip().lower() in KNOWN_WEAK_ADMIN_PASSWORDS


def collect_config_findings(cfg: _SecuritySettings) -> list[SecurityFinding]:
    """检查与数据库无关的静态配置项。

    致命性只在生产环境生效；非生产环境所有项一律降级为告警。
    """
    production = is_production(cfg.app_env)
    findings: list[SecurityFinding] = []
    if is_weak_secret_key(cfg.secret_key):
        findings.append(SecurityFinding(
            code="SECRET_KEY_WEAK",
            message=(
                f"SECRET_KEY 为公开默认值或短于 {MIN_SECRET_KEY_LENGTH} 位，"
                "任何人都可伪造登录 Cookie；请用 `openssl rand -hex 32` 生成"
            ),
            fatal=production,
        ))
    if not (cfg.key_encryption_key or "").strip():
        # 不升级为致命：存量协议档密文由 SECRET_KEY 派生密钥加密，直接切换 KEK 会导致
        # 解密失败；需先按迁移方案重新加密后再配置。
        findings.append(SecurityFinding(
            code="KEY_ENCRYPTION_KEY_EMPTY",
            message="KEY_ENCRYPTION_KEY 未配置，协议档 API Key 由 SECRET_KEY 派生密钥加密；生产应配置独立 Fernet 密钥",
            fatal=False,
        ))
    if production and not cfg.cookie_secure:
        # 不升级为致命：生产同时存在 HTTP(80) 与 HTTPS(8443) 入口，强制 Secure 会让
        # HTTP 入口无法登录；只在确认全站 HTTPS 后由运维显式开启。
        findings.append(SecurityFinding(
            code="COOKIE_NOT_SECURE",
            message="COOKIE_SECURE=false，登录 Cookie 可能经明文 HTTP 传输；全站 HTTPS 后请设为 true",
            fatal=False,
        ))
    return findings


def bootstrap_admin_finding(
    cfg: _SecuritySettings,
    *,
    admin_exists: bool,
    admin_uses_bootstrap_password: bool,
) -> SecurityFinding | None:
    """检查引导管理员口令。

    - 全新部署（账号不存在）且口令为弱值：生产致命，避免用公开口令创建管理员；
    - 存量账号仍能用弱引导口令登录：只告警（立即拒绝会让存量部署无法启动）。
    """
    if not is_weak_admin_password(cfg.bootstrap_admin_password):
        return None
    if not admin_exists:
        return SecurityFinding(
            code="BOOTSTRAP_ADMIN_PASSWORD_WEAK",
            message="BOOTSTRAP_ADMIN_PASSWORD 为公开默认值或常见弱口令，拒绝用它创建引导管理员；请先设置强口令",
            fatal=is_production(cfg.app_env),
        )
    if admin_uses_bootstrap_password:
        return SecurityFinding(
            code="BOOTSTRAP_ADMIN_STILL_DEFAULT",
            message="引导管理员仍在使用默认/弱口令，请立即登录修改密码",
            fatal=False,
        )
    return None


def enforce(findings: list[SecurityFinding]) -> None:
    """记录全部检查结果；存在致命项时抛 :class:`InsecureStartupError` 阻止启动。"""
    fatal = [item for item in findings if item.fatal]
    for item in findings:
        level = logging.ERROR if item.fatal else logging.WARNING
        logger.log(level, "启动安全检查 %s：%s", item.code, item.message)
    if fatal:
        codes = ", ".join(item.code for item in fatal)
        raise InsecureStartupError(
            f"生产环境存在不安全配置（{codes}），已阻止启动；"
            "修正 .env 后重新部署，仅本地开发可设 APP_ENV=development"
        )
