"""双模型用例对比的纯函数与请求校验。"""

import pytest
from pydantic import ValidationError
from shared.case_compare import compare_case_runs, score_cases

from app.schemas import CaseAiCompareIn


def _case(**overrides):
    """一份字段齐全、步骤可执行的正向样本。"""
    item = {
        "name": "验证码登录成功",
        "strategy": "正向",
        "priority": "HX",
        "module": "登录",
        "submodule": "验证码",
        "feature_point": "验证码登录",
        "precondition": "已获取验证码",
        "steps": "1. 输入验证码\n2. 点击登录",
        "expected": "登录成功并跳转首页",
        "test_type": "核心业务",
    }
    item.update(overrides)
    return item


def test_score_empty_cases_is_zero():
    scored = score_cases([], {"positive": 100})
    assert scored["score"] == 0
    assert scored["grade"] == "D"
    assert scored["issues"] == ["未得到有效用例"]


def test_missing_p0_cannot_keep_grade_a():
    """结构分再高，需求里的 P0 编号没有对应用例时也不能显示 A。"""
    source = "| FR-101 | 提交报销 | P0 |\n| FR-204 | 待审批可撤回 | P0 |"
    weights = {"positive": 50, "negative": 50}
    covered = score_cases([
        _case(name="提交成功", feature_point="FR-101 提交报销"),
        _case(name="撤回单据", feature_point="FR-204 待审批可撤回", strategy="反向"),
    ], weights, source_text=source)
    missing = score_cases([
        _case(name="提交成功", feature_point="FR-101 提交报销"),
        _case(name="附件缺失", feature_point="FR-101 必须上传附件", strategy="反向"),
    ], weights, source_text=source)
    assert covered["grade"] == "A"
    assert missing["grade"] == "B"
    assert missing["score"] <= 84.9
    assert missing["dimensions"]["review"] == 0
    assert any("FR-204" in issue for issue in missing["issues"])


def test_richer_case_outranks_name_only_case():
    left = score_cases([_case()], {"positive": 100})
    right = score_cases([{"name": "只有名称", "strategy": "正向"}], {"positive": 100})
    assert left["score"] > right["score"]
    assert left["dimensions"]["actionable"] == 1


def test_compare_marks_tie_and_shared_feature_point():
    compared = compare_case_runs(
        [_case(feature_point="验证码登录成功")],
        [_case(name="短信验证码登录", feature_point="验证码登录通过")],
        {"positive": 100},
        left_name="甲",
        right_name="乙",
    )
    assert compared["winner"] == "tie"
    assert compared["shared_points"]
    assert "甲" in compared["summary"]


def test_failed_side_does_not_count_as_a_low_score():
    compared = compare_case_runs(
        [_case()],
        [],
        {"positive": 100},
        left_ok=True,
        right_ok=False,
        right_name="乙",
    )
    assert compared["winner"] == "a"
    assert compared["scores"][1]["score"] is None
    assert "乙没有生成" in compared["summary"]


def test_compare_request_requires_two_distinct_profiles():
    with pytest.raises(ValidationError):
        CaseAiCompareIn(source_text="登录需求", profile_ids=["same", "same"])
    body = CaseAiCompareIn(source_text="登录需求", profile_ids=[" left ", "right"])
    assert body.profile_ids == ["left", "right"]
