"""API 侧 LLM 调用辅助：Agent 协议档解析与统一调用（AI 生成类端点共用）。

数据集的 AI 合成 / 用例的 AI 生成与补全都复用同一解析链：
``Setting.agent_profile_id`` -> ``ProtocolProfile`` -> 环境文件连接 -> ``call_protocol``。
"""

import json
import logging

from sqlalchemy.orm import Session

from .adapters import AdapterResult, call_protocol
from .errors import AppError, ErrorCode
from .models import ProtocolProfile, Setting
from .routers.profiles import _profile_connection

logger = logging.getLogger("ai-eval.llm_client")

# AI 生成默认超时与 token 上限（生成内容较长，给予充足余量）
DEFAULT_TIMEOUT_S = 120.0
DEFAULT_MAX_TOKENS = 8192
# 截断重试：抬到两倍预算，但不能无限加码（多数供应商单次输出上限 16k–32k）。
TRUNCATION_RETRY_CEILING = 32768


def resolve_agent_profile(db: Session) -> ProtocolProfile:
    """按 Agent 设置解析协议档；未配置/未启用 agent 用途时抛 VALIDATION。"""
    setting = db.query(Setting).filter(Setting.key == "agent_profile_id").first()
    profile_id = setting.value if setting else None
    if not isinstance(profile_id, str) or not profile_id:
        raise AppError(ErrorCode.VALIDATION, "尚未配置 Agent 协议档，无法调用 AI 生成")
    profile = db.query(ProtocolProfile).filter(ProtocolProfile.id == profile_id).first()
    if not profile:
        raise AppError(ErrorCode.VALIDATION, "Agent 协议档不存在")
    if "agent" not in (profile.usages or []):
        raise AppError(ErrorCode.VALIDATION, "协议档未启用 agent 用途")
    return profile


def _truncated(result: AdapterResult) -> bool:
    """输出是否被 max_tokens 截断（两类协议的终止原因已在适配层归一）。"""
    return getattr(result, "finish_reason", None) == "length"


def call_agent_model(
    db: Session,
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> AdapterResult:
    """按当前 Agent 协议档调用模型。双模型对比改走 ``call_profile_model``。"""
    return call_profile_model(
        resolve_agent_profile(db),
        system,
        user,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )


def call_profile_model(
    profile: ProtocolProfile,
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> AdapterResult:
    """按指定协议档调用模型。连接在进入函数时读完，调用本身不再碰数据库会话。

    被 ``max_tokens`` 截断时先抬预算重试一次：截断只会产出半截 JSON，直接
    报「无法解析」既误导用户（看起来像模型乱写），也浪费一次完整调用的成本。
    重试仍截断才以 BUDGET_EXCEEDED 明确告知「减少条数重试」。
    """
    base_url, model, api_key = _profile_connection(profile, allow_global_alias=True)
    if not base_url or not model or not api_key:
        missing = "、".join(
            name for name, value in (("URL", base_url), ("模型", model), ("API Key", api_key)) if not value
        )
        raise AppError(ErrorCode.VALIDATION, f"Agent 协议档「{profile.name}」未配置完整（缺 {missing}）")

    from .profile_env import read_profile_env

    full_url = read_profile_env(profile.id).full_url

    def invoke(budget: int) -> AdapterResult:
        return call_protocol(
            full_url=full_url,
            protocol=profile.protocol,
            base_url=base_url,
            model=model,
            api_key=api_key,
            messages=[{"role": "user", "content": user}],
            system=system,
            temperature=temperature,
            max_tokens=budget,
            anthropic_version=profile.anthropic_version,
            timeout_s=timeout_s,
        )

    try:
        result = invoke(max_tokens)
        if _truncated(result):
            retry_budget = min(TRUNCATION_RETRY_CEILING, max_tokens * 2)
            if retry_budget > max_tokens:
                logger.warning(
                    "AI 生成输出被截断（max_tokens=%s，已用 %s），抬预算重试",
                    max_tokens,
                    (result.usage or {}).get("completion_tokens"),
                )
                result = invoke(retry_budget)
                max_tokens = retry_budget
        if _truncated(result):
            raise AppError(
                ErrorCode.BUDGET_EXCEEDED,
                f"模型输出被长度上限截断（max_tokens={max_tokens}），请减少生成条数或拆分需求后重试",
            )
        return result
    except AppError:
        # 上游 4xx/5xx / 超时 / 协议不支持已归一为 AppError，直接透传
        raise
    except Exception as exc:
        logger.exception("AI 生成调用未预期异常: %s", exc)
        raise AppError(ErrorCode.INTERNAL, "AI 生成调用失败，请稍后重试") from exc


def extract_json_array(text: str) -> list[dict]:
    """容错提取 JSON 数组；解析实现与用例生成共用 ``shared.casegen``。"""
    from shared.casegen import extract_json_array as _extract

    try:
        return _extract(text)
    except ValueError as exc:
        # 保持既有错误码与文案：调用方按 UPSTREAM 展示「模型输出不可解析」。
        raise AppError(ErrorCode.UPSTREAM, str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise AppError(ErrorCode.UPSTREAM, "模型输出无法解析为 JSON 数组") from exc
