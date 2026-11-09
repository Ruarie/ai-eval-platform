"""个人记忆召回质量评测：关键词与语义两条路径的离线对比。

只做计算，不联网、不写库：调用方提供候选行与查询向量，返回 hit@1 / hit@5 /
MRR。分词与打分直接复用生产实现（`personal._keywords`、`semantic.*`），避免
评测口径与线上漂移。
"""

from __future__ import annotations

from .personal import _keywords
from .semantic import combined_score, cosine, is_candidate

DEFAULT_LIMIT = 5


def keyword_ranking(rows: list[dict], query: str, *, limit: int = DEFAULT_LIMIT) -> list[str]:
    """关键词 + 时间序排序（与生产 `_rank_keyword` 同口径）。"""
    words = _keywords((query or "")[:2000])
    scored = []
    for row in rows:
        title = str(row.get("title") or "")
        content = str(row.get("content") or "")
        if not title or not content:
            continue
        score = 3 * len(words & _keywords(title)) + len(words & _keywords(content))
        if score or row.get("category") == "preference":
            scored.append((float(score), row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [str(row["id"]) for _, row in scored[:limit]]


def semantic_ranking(rows: list[dict], query: str, vector: list[float] | None,
                     *, limit: int = DEFAULT_LIMIT) -> list[str]:
    """语义排序；缺少查询向量时退化为关键词排序，便于标注降级样本。"""
    if not vector:
        return keyword_ranking(rows, query, limit=limit)
    words = _keywords((query or "")[:2000])
    scored = []
    for row in rows:
        title = str(row.get("title") or "")
        content = str(row.get("content") or "")
        if not title or not content:
            continue
        score = 3 * len(words & _keywords(title)) + len(words & _keywords(content))
        similarity = cosine(vector, row.get("embedding"))
        if is_candidate(score, similarity, always=row.get("category") == "preference"):
            scored.append((combined_score(score, similarity), float(score), row))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [str(row["id"]) for _, _, row in scored[:limit]]


def _score(ranking: list[str], expected: set[str]) -> tuple[float, float, float]:
    """返回 (hit@1, hit@5, RR)；没有预期答案时记 0，避免除零放大。"""
    if not expected:
        return 0.0, 0.0, 0.0
    hit1 = 1.0 if ranking[:1] and ranking[0] in expected else 0.0
    hit5 = 1.0 if any(item in expected for item in ranking[:5]) else 0.0
    reciprocal = 0.0
    for index, item in enumerate(ranking):
        if item in expected:
            reciprocal = 1.0 / (index + 1)
            break
    return hit1, hit5, reciprocal


def evaluate(rows: list[dict], queries: list[dict], vectors: list[list[float] | None],
             *, limit: int = DEFAULT_LIMIT) -> dict:
    """逐查询对比两条路径；``queries[i]["expected"]`` 为预期记忆 ID 列表。"""
    if len(vectors) != len(queries):
        raise ValueError("查询向量条数与查询数量不一致")
    totals = {"keyword": [0.0, 0.0, 0.0], "semantic": [0.0, 0.0, 0.0]}
    cases = []
    degraded = 0
    for query, vector in zip(queries, vectors):
        text = str(query.get("query") or "")
        expected = {str(item) for item in (query.get("expected") or [])}
        keyword_hits = keyword_ranking(rows, text, limit=limit)
        semantic_hits = semantic_ranking(rows, text, vector, limit=limit)
        if not vector:
            degraded += 1
        for name, ranking in (("keyword", keyword_hits), ("semantic", semantic_hits)):
            scores = _score(ranking, expected)
            totals[name] = [left + right for left, right in zip(totals[name], scores)]
        cases.append({
            "query": text,
            "expected": sorted(expected),
            "keyword": keyword_hits,
            "semantic": semantic_hits,
            "degraded": not vector,
        })
    count = max(len(queries), 1)
    return {
        "queries": len(queries),
        "limit": limit,
        "degraded": degraded,
        "keyword": {
            "hit_at_1": round(totals["keyword"][0] / count, 4),
            "hit_at_5": round(totals["keyword"][1] / count, 4),
            "mrr": round(totals["keyword"][2] / count, 4),
        },
        "semantic": {
            "hit_at_1": round(totals["semantic"][0] / count, 4),
            "hit_at_5": round(totals["semantic"][1] / count, 4),
            "mrr": round(totals["semantic"][2] / count, 4),
        },
        "cases": cases,
    }
