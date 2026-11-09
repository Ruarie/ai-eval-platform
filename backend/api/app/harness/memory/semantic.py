"""Harness 语义记忆：向量工具与召回打分。

生产检索（pgvector / LightRAG）仍是演进项，``retrieve`` 保持显式失败；
本模块先提供与评测共用的纯计算函数：向量归一化、余弦相似度、候选判定与
关键词/语义的融合排序。所有函数都不联网、不写库，便于单测与离线评测复用。
"""

from __future__ import annotations

import math

from app.errors import AppError, ErrorCode

# 低于该余弦相似度的候选不进入语义召回，避免向量噪声污染上下文。
SIMILARITY_THRESHOLD = 0.55
# 融合排序里语义与关键词的权重：语义为主、关键词兜底。
_SEMANTIC_WEIGHT = 0.65
_KEYWORD_WEIGHT = 0.35
# 关键词得分归一到 0–1 时的参考上限（标题权重 3 + 正文命中若干）。
_KEYWORD_SCALE = 6.0


def retrieve(query: str) -> list:
    """语义记忆检索占位：未接入，抛 AppError(VALIDATION)。"""
    raise AppError(ErrorCode.VALIDATION, "RAG 语义记忆未接入")


def as_vector(value: object) -> list[float] | None:
    """把数据库/请求里的向量值收敛成 ``list[float]``；非法值返回 None。

    pgvector 返回的是字符串 ``'[0.1,0.2]'``，隔离测试库用 JSON 列返回 list，
    这里统一处理，避免调用方到处判断类型。
    """
    if value is None:
        return None
    raw: object = value
    if isinstance(raw, bytes | bytearray):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        if not text:
            return None
        parts = [item.strip() for item in text.split(",") if item.strip()]
        try:
            return [float(item) for item in parts]
        except ValueError:
            return None
    if isinstance(raw, list | tuple):
        try:
            return [float(item) for item in raw]
        except (TypeError, ValueError):
            return None
    return None


def cosine(left: object, right: object) -> float:
    """余弦相似度；维数不一致、空向量或零向量返回 0.0（不抛异常）。"""
    a = as_vector(left)
    b = as_vector(right)
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (norm_a * norm_b)))


def is_candidate(keyword_score: float, similarity: float, *, always: bool = False) -> bool:
    """候选判定：偏好类始终入选；否则关键词命中或语义相似度达阈值才入选。"""
    if always:
        return True
    if keyword_score and keyword_score > 0:
        return True
    return similarity >= SIMILARITY_THRESHOLD


def combined_score(keyword_score: float, similarity: float) -> float:
    """融合得分：语义权重更高，关键词做归一化后作为兜底信号。"""
    keyword_norm = min(1.0, max(0.0, float(keyword_score)) / _KEYWORD_SCALE)
    return _SEMANTIC_WEIGHT * max(-1.0, min(1.0, similarity)) + _KEYWORD_WEIGHT * keyword_norm
