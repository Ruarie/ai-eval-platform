"""对话回合结束后的个人记忆自动抽取（默认关闭）。

边界（PRD V1.69）：

- 只处理**本人私有会话**，团队共享、子运行与他人会话一律跳过；
- 回合结束后后台执行，任何失败只记 trace，绝不影响已完成的对话；
- 模型只提供候选，落库前必须经代码侧强校验（条数、长度、枚举）与去重
  （精确文本 + 语义向量），并复用个人记忆的凭据拒绝、配额与 ACL；
- 未开启 ``AGENT_MEMORY_AUTO_EXTRACT_ENABLED`` 时不读对话、不调模型、不写库。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict

from ...config import settings
from ...db import SessionLocal
from ...errors import AppError
from ...llm_client import call_agent_model
from ...models import Message, Session, User
from ..security.loop_redaction import contains_credential
from .personal import store_extracted_memories

logger = logging.getLogger("harness.memory.extract")

EXTRACT_SYSTEM_PROMPT = """你是个人长期记忆整理助手。阅读本轮对话，抽取值得跨会话记住的稳定信息，只输出一个 JSON 数组。
规则：
1. 只抽取用户明确表达、且未来仍然成立的偏好或事实（例如“回答先给结论”“我负责订单模块”）；
2. 不抽取临时任务、一次性要求、寒暄、助手的主观判断或模型猜测；
3. 每条 title 不超过 20 字，content 不超过 200 字，category 只能是 "preference" 或 "fact"；
4. 最多 3 条；没有值得记住的内容时输出 []；
5. 禁止输出密码、密钥、令牌、身份证、手机号、银行卡等敏感信息；
6. 只输出 JSON 数组，不要解释、前缀或代码围栏。
输出格式：[{"title": "...", "content": "...", "category": "preference"}]"""

MAX_ITEMS = 3
MAX_TITLE_CHARS = 20
MAX_CONTENT_CHARS = 200
PROMPT_TEXT_MAX_CHARS = 2000
EXTRACT_TIMEOUT_S = 30.0
EXTRACT_MAX_TOKENS = 600

# 进程内去重：同一助手消息只处理一次（重启后由内容去重兜底）。
_PROCESSED_MESSAGES: OrderedDict[str, None] = OrderedDict()
_PROCESSED_LIMIT = 512


def parse_extraction(raw: str) -> list[dict]:
    """强校验模型输出；任何契约不符只返回空列表，不把原文写入记忆。"""
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            line for line in cleaned.splitlines() if not line.strip().startswith("```")
        ).strip()
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(cleaned[start : end + 1])
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items: list[dict] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        title = entry.get("title")
        content = entry.get("content")
        category = entry.get("category")
        if not isinstance(title, str) or not isinstance(content, str):
            continue
        title = " ".join(title.split())[:MAX_TITLE_CHARS]
        content = " ".join(content.split())[:MAX_CONTENT_CHARS]
        if not title or not content or category not in ("preference", "fact"):
            continue
        items.append({"title": title, "content": content, "category": category})
        if len(items) >= MAX_ITEMS:
            break
    return items


def build_prompt(user_text: str, assistant_text: str) -> str:
    """把本轮对话压成有界提示词；超长只截断，不做摘要调用。"""
    return (
        "本轮对话：\n"
        f"用户：{user_text[:PROMPT_TEXT_MAX_CHARS]}\n"
        f"助手：{assistant_text[:PROMPT_TEXT_MAX_CHARS]}"
    )


def _mark_processed(message_id: str) -> bool:
    """记录已处理的助手消息；返回 True 表示可继续处理。"""
    if message_id in _PROCESSED_MESSAGES:
        return False
    _PROCESSED_MESSAGES[message_id] = None
    while len(_PROCESSED_MESSAGES) > _PROCESSED_LIMIT:
        _PROCESSED_MESSAGES.popitem(last=False)
    return True


def _load_turn_text(db, session_id: str) -> tuple[str, str, str, str | None] | None:
    """读取最近一轮用户/助手文本；返回 (assistant_id, user_text, assistant_text, workspace_id)。"""
    assistant = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role == "assistant", Message.content != "")
        .order_by(Message.created_at.desc())
        .first()
    )
    if assistant is None:
        return None
    user_message = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role == "user",
                Message.created_at <= assistant.created_at)
        .order_by(Message.created_at.desc())
        .first()
    )
    if user_message is None:
        return None
    session = db.query(Session).filter(Session.id == session_id).first()
    if session is None:
        return None
    return assistant.id, user_message.content or "", assistant.content or "", session.workspace_id


async def extract_after_turn(session_id: str, user_id: str) -> int:
    """回合结束后抽取并落库；返回新建条数，任何异常都返回 0。"""
    if not settings.agent_memory_auto_extract_enabled:
        return 0
    db = SessionLocal()
    try:
        session = db.query(Session).filter(Session.id == session_id).first()
        if (
            session is None
            or session.deleted_at is not None
            or session.visibility != "private"
            or session.user_id != user_id
        ):
            return 0
        user = db.query(User).filter(User.id == user_id).first()
        if user is None or user.disabled:
            return 0
        loaded = _load_turn_text(db, session_id)
        if loaded is None:
            return 0
        assistant_id, user_text, assistant_text, workspace_id = loaded
        if not user_text.strip() or not assistant_text.strip() or not _mark_processed(assistant_id):
            return 0
        # 任一侧出现凭据形态都不送入模型，也不落库。
        if contains_credential(user_text) or contains_credential(assistant_text):
            return 0
        result = await asyncio.to_thread(
            call_agent_model,
            db,
            EXTRACT_SYSTEM_PROMPT,
            build_prompt(user_text, assistant_text),
            max_tokens=EXTRACT_MAX_TOKENS,
            timeout_s=EXTRACT_TIMEOUT_S,
        )
        items = parse_extraction(result.text)
        if not items:
            return 0
        created = store_extracted_memories(
            db, user_id, workspace_id, items,
            max_items=settings.agent_memory_auto_extract_max_items,
        )
        db.commit()
        return len(created)
    except AppError as exc:
        db.rollback()
        logger.info("memory extract skipped code=%s", exc.code.value)
        return 0
    except Exception as exc:  # 抽取失败不得影响对话
        db.rollback()
        logger.warning("memory extract failed type=%s", type(exc).__name__)
        return 0
    finally:
        db.close()


def _log_task_failure(task: asyncio.Task) -> None:
    """后台任务异常只记类型：任务已被取消时不读取异常（会抛 CancelledError）。"""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.warning("memory extract task failed type=%s", type(error).__name__)


def schedule_extraction(session_id: str, user_id: str) -> None:
    """fire-and-forget 入口：调用方不 await，也不依赖其结果。"""
    if not settings.agent_memory_auto_extract_enabled or not user_id:
        return
    task = asyncio.create_task(
        extract_after_turn(session_id, user_id), name=f"memory-extract-{session_id}"
    )
    task.add_done_callback(_log_task_failure)
