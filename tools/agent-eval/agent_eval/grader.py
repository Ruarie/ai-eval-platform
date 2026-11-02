"""用例质量评分器（规则型，零依赖，可复现）。

七个维度加权到 100 分：
- schema      字段完整度（缺字段直接扣分，身份类保留字段出现则扣分）
- coverage    需求点覆盖率（对照夹具声明的 expected_points）
- trace       可追溯性 / 反向防幻觉（用例文本必须能在需求里找到依据）
- action      可执行性（步骤编号、可观察断言）
- specific    具体性与诚实度（拒绝「正常/成功」式断言；模糊需求须标待澄清）
- strategy    策略配比忠实度（与请求的六策略配比做 L1 距离）
- dedupe      去重度（名称/步骤近似的重复对）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STRATEGY_LABELS = {"正向", "反向", "边界", "等价类", "状态迁移", "场景"}
PRIORITY_LABELS = {"HX", "FHX", "BJ", "YC", "ZD", "BL"}
REQUIRED_FIELDS = [
    "strategy", "priority", "module", "submodule", "feature_point",
    "name", "precondition", "steps", "expected", "test_type",
]
RESERVED_FIELDS = ["id", "case_set_id", "mapped", "pending_complete", "extras", "sort_order"]
VAGUE_EXPECTED = {"正常", "成功", "无", "ok", "OK", "正常返回", "功能正常", "符合预期", "结果正确"}
OBSERVABLE = ("提示", "返回", "跳转", "展示", "显示", "状态", "金额", "次数", "日志",
              "接口", "http", "HTTP", "码", "成功", "失败", "错误", "锁定", "置灰",
              "不可", "禁止", "弹出", "刷新", "回调", "导出", "通知", "站内信")

_CN = re.compile(r"[\u4e00-\u9fa5]+")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _case_text(case: dict) -> str:
    return " ".join(
        _norm(case.get(key))
        for key in ("name", "feature_point", "module", "submodule", "precondition", "steps", "expected")
    )


def _bigrams(text: str) -> set[str]:
    """中文按二元组切分，英文/数字按词切分；用于轻量语义近似判断。"""
    text = _norm(text)
    grams: set[str] = set()
    for chunk in _CN.findall(text):
        if len(chunk) == 1:
            grams.add(chunk)
        for i in range(len(chunk) - 1):
            grams.add(chunk[i:i + 2])
    for word in re.findall(r"[A-Za-z0-9_/.]{2,}", text):
        grams.add(word.lower())
    return grams


def _overlap(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


@dataclass
class QualityReport:
    fixture_id: str
    total: int
    score: float
    grade: str
    dimensions: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "total": self.total,
            "score": round(self.score, 1),
            "grade": self.grade,
            "dimensions": {key: round(value, 3) for key, value in self.dimensions.items()},
            "issues": self.issues,
            "stats": self.stats,
        }


def grade(
    cases: list[dict],
    *,
    source_text: str,
    expected_points: list[str],
    weights: dict[str, int],
    max_count: int,
    ambiguity: bool = False,
    fixture_id: str = "",
) -> QualityReport:
    issues: list[str] = []
    total = len(cases)
    if not cases:
        return QualityReport(fixture_id, 0, 0.0, "D", {k: 0.0 for k in
                              ("schema", "coverage", "trace", "action", "specific", "strategy", "dedupe")},
                              ["模型未返回任何用例"], {})

    # ---- schema ----
    filled = 0
    slot = 0
    missing_counter: dict[str, int] = {}
    reserved_hits = 0
    for case in cases:
        pending = "待澄清" in _norm(case.get("test_type"))
        for key in REQUIRED_FIELDS:
            # 模糊需求下「预期结果留空 + 标记待澄清」是正确行为，不计为字段缺失。
            if ambiguity and pending and key == "expected":
                continue
            slot += 1
            if _norm(case.get(key)):
                filled += 1
            else:
                missing_counter[key] = missing_counter.get(key, 0) + 1
        if any(key in case for key in RESERVED_FIELDS):
            reserved_hits += 1
    schema = filled / slot
    if missing_counter:
        top = sorted(missing_counter.items(), key=lambda kv: -kv[1])[:3]
        issues.append("字段缺失：" + "、".join(f"{k}×{v}" for k, v in top))
    if reserved_hits:
        issues.append(f"{reserved_hits} 条用例携带了模型不应输出的保留字段")
        schema *= 0.9

    # ---- coverage ----
    case_grams = [(c, _bigrams(_case_text(c))) for c in cases]
    source_grams = _bigrams(source_text)
    covered = 0
    uncovered: list[str] = []
    for point in expected_points:
        point_grams = _bigrams(point)
        best = max((_overlap(point_grams, grams) for _, grams in case_grams), default=0.0)
        if best >= 0.25:
            covered += 1
        else:
            uncovered.append(point)
    coverage = covered / len(expected_points) if expected_points else 1.0
    if uncovered:
        issues.append("需求点未覆盖：" + "、".join(uncovered[:5]))

    # ---- trace / 防幻觉 ----
    traced = 0
    fabricated: list[str] = []
    for case, grams in case_grams:
        if _overlap(grams, source_grams) >= 0.2:
            traced += 1
        else:
            fabricated.append(_norm(case.get("name"))[:24])
    trace = traced / total
    if ambiguity:
        # 需求本身是「更智能/更快」这类不可测描述，词面追溯无意义，只看是否标待澄清。
        trace = 1.0
        fabricated = []
    if fabricated:
        issues.append(f"{len(fabricated)} 条用例在需求中找不到依据：" + "、".join(fabricated[:3]))

    # ---- actionability ----
    actionable = 0
    for case in cases:
        steps = _norm(case.get("steps"))
        expected = _norm(case.get("expected"))
        step_marks = len(re.findall(r"(?:^|\n)\s*(?:\d+[.、)]|[①②③④⑤]|-|\*)", steps))
        has_steps = step_marks >= 2 or (steps.count("\n") >= 1 and len(steps) >= 12)
        observable = any(word in expected for word in OBSERVABLE)
        if has_steps and observable and len(expected) >= 6:
            actionable += 1
        elif not expected and ambiguity:
            actionable += 1  # 模糊需求允许留空，由 specific 维度判是否标记待澄清
    action = actionable / total
    if action < 0.8:
        issues.append(f"仅 {actionable}/{total} 条用例步骤可执行且断言可观察")

    # ---- specificity / honesty ----
    vague = 0
    for case in cases:
        expected = _norm(case.get("expected"))
        if not expected:
            if ambiguity and "待澄清" in _norm(case.get("test_type")):
                continue
            vague += 1
        elif expected in VAGUE_EXPECTED or len(expected) < 6:
            vague += 1
    if ambiguity:
        pending = sum(1 for c in cases if "待澄清" in _norm(c.get("test_type")) or not _norm(c.get("expected")))
        honesty = pending / total
        if honesty < 0.5:
            issues.append(f"模糊需求下仅 {pending}/{total} 条用例标注待澄清，存在臆造预期结果风险")
    else:
        honesty = 1.0
    specific = max(0.0, 1.0 - vague / total) * 0.5 + honesty * 0.5

    # ---- strategy fidelity ----
    want_total = sum(weights.values()) or 100
    want = {k: v / want_total for k, v in weights.items()}
    got_counts: dict[str, int] = {label: 0 for label in STRATEGY_LABELS}
    unknown_strategy = 0
    for case in cases:
        label = _norm(case.get("strategy"))
        if label in got_counts:
            got_counts[label] += 1
        else:
            unknown_strategy += 1
        priority = _norm(case.get("priority"))
        if priority and priority not in PRIORITY_LABELS:
            issues.append(f"非法优先级取值：{priority}")
            break
    got = {label: count / total for label, count in got_counts.items()}
    l1 = sum(abs(want.get(en, 0) - got.get(zh, 0)) for en, zh in (
        ("positive", "正向"), ("negative", "反向"), ("boundary", "边界"),
        ("equivalence", "等价类"), ("state", "状态迁移"), ("scenario", "场景"),
    ))
    strategy = max(0.0, 1.0 - l1 / 2)
    if unknown_strategy:
        issues.append(f"{unknown_strategy} 条用例策略不在六类枚举内")
    if l1 > 0.5:
        issues.append(f"策略分布与配比偏差较大（L1={l1:.2f}）")

    # ---- dedupe ----
    dup_pairs = 0
    seen: list[set[str]] = []
    for case, grams in case_grams:
        key_grams = _bigrams(_norm(case.get("name")) + " " + _norm(case.get("feature_point")))
        if any(_overlap(key_grams, prev) >= 0.75 for prev in seen):
            dup_pairs += 1
        seen.append(key_grams)
    dedupe = max(0.0, 1.0 - dup_pairs / max(1, total - 1))
    if dup_pairs:
        issues.append(f"{dup_pairs} 条用例与已有用例高度重复")

    dims = {
        "schema": schema,
        "coverage": coverage,
        "trace": trace,
        "action": action,
        "specific": specific,
        "strategy": strategy,
        "dedupe": dedupe,
    }
    weights_map = {
        "schema": 0.20, "coverage": 0.20, "trace": 0.15, "action": 0.20,
        "specific": 0.10, "strategy": 0.10, "dedupe": 0.05,
    }
    score = sum(dims[key] * weight for key, weight in weights_map.items()) * 100

    # ---- 硬伤封顶 ----
    if trace < 0.5:
        issues.append("超过半数用例无法追溯到需求，触发分数封顶")
        score = min(score, 59)
    if coverage < 0.5:
        issues.append("需求点覆盖不足 50%，触发分数封顶")
        score = min(score, 59)
    if schema < 0.85:
        score = min(score, 69)

    if total > max_count:
        score -= 5
        issues.append(f"条数超上限：{total} > {max_count}")

    grade_label = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    stats = {
        "strategy_dist": got_counts,
        "vague_expected": vague,
        "duplicate": dup_pairs,
        "uncovered_points": uncovered,
        "case_count": total,
    }
    return QualityReport(fixture_id, total, score, grade_label, dims, issues[:10], stats)
