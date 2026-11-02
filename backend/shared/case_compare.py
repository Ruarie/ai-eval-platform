"""同一需求下两份候选用例的结构对比。

只比较本轮已经解析、去重、按策略裁剪后的候选，不访问模型、不落库。
分数描述这一次生成的完整度、可执行性和配比贴合度，不是模型的长期排名。
"""

from __future__ import annotations

import re

from shared.casegen import STRATEGY_NAMES, selfcheck, validate_strategy_weights

REQUIRED_FIELDS = (
    "strategy", "priority", "module", "submodule", "feature_point",
    "name", "precondition", "steps", "expected", "test_type",
)
OBSERVABLE = (
    "提示", "返回", "跳转", "展示", "显示", "状态", "金额", "次数",
    "接口", "码", "锁定", "置灰", "禁止", "弹出", "刷新", "回调",
)
_CN = re.compile(r"[\u4e00-\u9fff]+")
_STEP_MARK = re.compile(r"(?:^|\n)\s*(?:\d+[.、)]|[①②③④⑤]|-|\*)")
_POINT_OVERLAP = 0.6


def _text(value: object) -> str:
    return str(value or "").strip()


def _bigrams(text: str) -> set[str]:
    """中文二元组，用来判断两个功能点是不是同一条规则。"""
    grams: set[str] = set()
    for chunk in _CN.findall(text):
        if len(chunk) == 1:
            grams.add(chunk)
            continue
        for index in range(len(chunk) - 1):
            grams.add(chunk[index:index + 2])
    return grams


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _actionable(case: dict) -> bool:
    steps = _text(case.get("steps"))
    expected = _text(case.get("expected"))
    step_marks = len(_STEP_MARK.findall(steps))
    has_steps = step_marks >= 2 or (steps.count("\n") >= 1 and len(steps) >= 12)
    return has_steps and len(expected) >= 6 and any(word in expected for word in OBSERVABLE)


def _strategy_fit(cases: list[dict], weights: dict[str, int]) -> float:
    if not cases:
        return 0.0
    total_weight = sum(weights.values()) or 100
    want = {key: value / total_weight for key, value in weights.items()}
    counts = {label: 0 for label in STRATEGY_NAMES.values()}
    for case in cases:
        label = _text(case.get("strategy"))
        if label in counts:
            counts[label] += 1
    got = {label: count / len(cases) for label, count in counts.items()}
    distance = sum(
        abs(want.get(key, 0) - got.get(label, 0))
        for key, label in STRATEGY_NAMES.items()
    )
    return max(0.0, 1.0 - distance / 2)


def score_cases(cases: list[dict], weights: dict[str, int] | None = None) -> dict:
    """给一份候选打结构分。没有用例时各维为 0。"""
    weights = validate_strategy_weights(weights)
    total = len(cases)
    if not total:
        dimensions = {"complete": 0.0, "actionable": 0.0, "strategy": 0.0, "review": 0.0}
        return {
            "score": 0.0,
            "grade": "D",
            "case_count": 0,
            "dimensions": dimensions,
            "issues": ["未得到有效用例"],
        }
    filled = 0
    slots = 0
    for case in cases:
        for key in REQUIRED_FIELDS:
            slots += 1
            if _text(case.get(key)):
                filled += 1
    complete = filled / slots
    actionable_count = sum(1 for case in cases if _actionable(case))
    actionable = actionable_count / total
    strategy = _strategy_fit(cases, weights)
    checks = selfcheck(cases, weights=weights)
    review = 1.0 if not checks else 0.0
    dimensions = {
        "complete": round(complete, 3),
        "actionable": round(actionable, 3),
        "strategy": round(strategy, 3),
        "review": review,
    }
    score = (
        complete * 0.35 + actionable * 0.35 + strategy * 0.20 + review * 0.10
    ) * 100
    issues: list[str] = []
    if complete < 0.9:
        issues.append(f"字段完整度 {complete:.0%}")
    if actionable < 0.8:
        issues.append(f"仅 {actionable_count}/{total} 条步骤可执行且预期可观察")
    issues.extend(check["message"] for check in checks)
    grade = "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D"
    return {
        "score": round(score, 1),
        "grade": grade,
        "case_count": total,
        "dimensions": dimensions,
        "issues": issues[:6],
    }


def _points(cases: list[dict]) -> list[str]:
    seen: list[str] = []
    for case in cases:
        point = _text(case.get("feature_point")) or _text(case.get("name"))
        if point and point not in seen:
            seen.append(point)
    return seen


def _split_points(left: list[str], right: list[str]) -> tuple[list[str], list[str], list[str]]:
    """按功能点词面重合分成共有、仅左侧、仅右侧。"""
    right_grams = [(point, _bigrams(point)) for point in right]
    shared: list[str] = []
    only_left: list[str] = []
    matched_right: set[int] = set()
    for point in left:
        grams = _bigrams(point)
        hit = next(
            (index for index, (_name, other) in enumerate(right_grams) if _overlap(grams, other) >= _POINT_OVERLAP),
            None,
        )
        if hit is None:
            only_left.append(point)
            continue
        matched_right.add(hit)
        shared.append(point)
    only_right = [point for index, (point, _grams) in enumerate(right_grams) if index not in matched_right]
    return shared[:8], only_left[:8], only_right[:8]


def compare_case_runs(
    left: list[dict],
    right: list[dict],
    weights: dict[str, int] | None = None,
    *,
    left_name: str = "模型 A",
    right_name: str = "模型 B",
    left_ok: bool = True,
    right_ok: bool = True,
) -> dict:
    """对比两份候选并写出本轮结论。任一侧失败时不拿空列表冒充低分。"""
    left_score = score_cases(left, weights) if left_ok else None
    right_score = score_cases(right, weights) if right_ok else None
    shared, only_left, only_right = _split_points(
        _points(left) if left_ok else [],
        _points(right) if right_ok else [],
    )
    winner: str | None
    if left_ok and right_ok and left_score and right_score:
        gap = left_score["score"] - right_score["score"]
        winner = "tie" if abs(gap) < 1 else ("a" if gap > 0 else "b")
    elif left_ok and not right_ok:
        winner = "a"
    elif right_ok and not left_ok:
        winner = "b"
    else:
        winner = None
    summary = _summary(left_name, right_name, left_score, right_score, winner, len(shared), len(only_left), len(only_right))
    return {
        "winner": winner,
        "summary": summary,
        "scores": [
            {"side": "a", **(left_score or _empty_score())},
            {"side": "b", **(right_score or _empty_score())},
        ],
        "shared_points": shared,
        "only_a": only_left,
        "only_b": only_right,
    }


def _empty_score() -> dict:
    return {
        "score": None,
        "grade": None,
        "case_count": 0,
        "dimensions": {"complete": 0.0, "actionable": 0.0, "strategy": 0.0, "review": 0.0},
        "issues": ["本侧未生成成功"],
    }


def _summary(
    left_name: str,
    right_name: str,
    left_score: dict | None,
    right_score: dict | None,
    winner: str | None,
    shared: int,
    only_left: int,
    only_right: int,
) -> str:
    """用本轮分数和功能点差异写一句结论，不外推成模型总排名。"""
    coverage = f"共同功能点 {shared} 个，{left_name} 独有 {only_left} 个，{right_name} 独有 {only_right} 个。"
    if winner is None or left_score is None or right_score is None:
        failed = "两侧都" if winner is None else (left_name if winner == "b" else right_name)
        return f"本轮{failed}没有生成出可对比的用例。{coverage}"
    if winner == "tie":
        lead = f"{left_name}与{right_name}本轮结构分接近（{left_score['score']} / {right_score['score']}）。"
    elif winner == "a":
        lead = f"本轮同一需求上，{left_name} {left_score['score']} 分，高于 {right_name} 的 {right_score['score']} 分。"
    else:
        lead = f"本轮同一需求上，{right_name} {right_score['score']} 分，高于 {left_name} 的 {left_score['score']} 分。"
    return lead + coverage
