"""召回质量评测口径回归：hit@1 / hit@5 / MRR 与两条路径的对比。"""

import pytest

from app.harness.memory.eval import evaluate, keyword_ranking, semantic_ranking

ROWS = [
    {"id": "near", "title": "迭代节奏", "content": "每次迭代都要回归测试",
     "category": "fact", "embedding": [1.0, 0.0, 0.0]},
    {"id": "kw", "title": "部署口令", "content": "上线前必须核对检查清单",
     "category": "fact", "embedding": [0.0, 1.0, 0.0]},
    {"id": "other", "title": "报销流程", "content": "差旅报销需要发票",
     "category": "fact", "embedding": [0.0, 0.0, 1.0]},
]
QUERY = "上线前要检查什么"


def test_rankings_differ_on_same_query() -> None:
    """同一查询：关键词只认字面，语义认向量近邻。"""
    assert keyword_ranking(ROWS, QUERY)[0] == "kw"
    assert semantic_ranking(ROWS, QUERY, [1.0, 0.0, 0.0])[0] == "near"


def test_evaluate_reports_delta() -> None:
    """评测输出两条路径的指标与逐查询明细。"""
    report = evaluate(ROWS, [{"query": QUERY, "expected": ["near"]}], [[1.0, 0.0, 0.0]])
    assert report["queries"] == 1
    assert report["keyword"]["hit_at_1"] == 0.0
    assert report["semantic"]["hit_at_1"] == 1.0
    assert report["semantic"]["mrr"] == 1.0
    assert report["cases"][0]["semantic"][0] == "near"
    assert report["degraded"] == 0


def test_evaluate_marks_degraded_queries() -> None:
    """缺少查询向量时语义列退化为关键词，并计入 degraded。"""
    report = evaluate(ROWS, [{"query": QUERY, "expected": ["kw"]}], [None])
    assert report["degraded"] == 1
    assert report["semantic"] == report["keyword"]
    assert report["cases"][0]["degraded"] is True


def test_evaluate_rejects_mismatched_vectors() -> None:
    """向量条数与查询数量不一致属于调用方错误，直接拒绝。"""
    with pytest.raises(ValueError):
        evaluate(ROWS, [{"query": QUERY, "expected": ["kw"]}], [])


def test_metric_ignores_missing_expected() -> None:
    """没有预期答案的查询记 0 分，不因除零放大指标。"""
    report = evaluate(ROWS, [{"query": QUERY, "expected": []}], [None])
    assert report["keyword"]["hit_at_5"] == 0.0
    assert report["keyword"]["mrr"] == 0.0
