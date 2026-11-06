"""用例生成 Skill 纯函数单测（M2 W8 / PRD 5.4.1）。

正本位于 shared 包（纯函数零依赖），按文件路径加载，CI 覆盖 worker
与 api 共用的生成口径；覆盖 prompt 组装、容错解析、配比校正与自检红字规则。
"""

import importlib.util
import json
from pathlib import Path

import pytest

# 共用用例生成纯函数路径：backend/shared/casegen.py
_CASEGEN_PATH = Path(__file__).resolve().parents[2] / "shared" / "casegen.py"
_spec = importlib.util.spec_from_file_location("shared_casegen", _CASEGEN_PATH)
casegen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(casegen)


def test_build_prompts_contains_ratio_and_source():
    # prompt 必须包含六策略配比说明与来源文档
    system, user = casegen.build_prompts("登录模块需求", 45)
    assert "正向" in system and "反向" in system and "边界" in system
    assert "等价类" in system and "状态迁移" in system and "场景" in system
    assert "只输出一个 JSON 数组" in system
    assert "45" in user and "登录模块需求" in user
    for key, weight in casegen.STRATEGY_WEIGHTS.items():
        assert f"{casegen.STRATEGY_NAMES[key]} {weight}%" in user


def test_build_prompts_guides_risk_traceability_and_observable_cases():
    """两条生成路径共用风险驱动原则，参考 designing-functional-tests（MIT）。"""
    # https://github.com/jaktestowac/awesome-copilot-for-testers/blob/main/skills/designing-functional-tests/SKILL.md
    system, _ = casegen.build_prompts("支付需求", 10)
    assert "高风险流程覆盖正向、反向、边界、权限及中断恢复" in system
    assert "每条用例只验证一个明确行为" in system
    assert "feature_point 要能追溯到需求" in system
    assert "steps 至少写成两行" in system
    assert "steps（可执行操作步骤）" in system
    assert "expected 至少 6 个字" in system
    assert "需求未给出确定预期时不要编造" in system


def test_parse_cases_tolerates_fences_and_prose():
    # 允许代码围栏与首尾解释文字
    raw = '好的，以下是用例：\n```json\n[{"name": "登录成功", "strategy": "正向"}]\n```\n以上共 1 条。'
    cases = casegen.parse_cases(raw)
    assert len(cases) == 1 and cases[0]["name"] == "登录成功"


def test_parse_cases_rejects_invalid_payload():
    import pytest

    with pytest.raises(ValueError):
        casegen.parse_cases("完全不是 JSON 的输出")
    with pytest.raises(ValueError):
        casegen.parse_cases('{"name": "对象而非数组"}')
    with pytest.raises(ValueError):
        casegen.parse_cases("[{\"strategy\": \"正向\"}]")  # 无 name 的条目被过滤后为空


def test_rebalance_trims_overweight_strategy():
    # 正向超配比被截断；总条数不超上限
    cases = [{"name": f"用例{i}", "strategy": "正向"} for i in range(40)]
    cases += [{"name": f"反用例{i}", "strategy": "反向"} for i in range(5)]
    result = casegen.rebalance_by_strategy(cases, 45)
    positives = [c for c in result if c["strategy"] == "正向"]
    negatives = [c for c in result if c["strategy"] == "反向"]
    # 45 条配额：正向 18（40%）、反向 11（25%）；不足的 5 条反向全保留
    assert len(positives) == 18
    assert len(negatives) == 5
    assert len(result) <= 45


def test_rebalance_uses_requested_weights_and_excludes_zero_weight():
    """全正向请求不能再被默认正向四成配额截断，零配额策略不得混入。"""
    cases = [{"name": f"正向{i}", "strategy": "正向"} for i in range(20)]
    cases += [{"name": "反向", "strategy": "反向"}]
    result = casegen.rebalance_by_strategy(cases, 20, {"positive": 100})
    assert len(result) == 20
    assert all(case["strategy"] == "正向" for case in result)


def test_rebalance_excludes_unknown_strategy():
    """模型给出未定义策略时不能绕过用户选择进入候选。"""
    cases = [
        {"name": "未知策略", "strategy": "任意新策略"},
        {"name": "未选策略", "strategy": "反向"},
        {"name": "已选策略", "strategy": "正向"},
    ]
    assert casegen.rebalance_by_strategy(cases, 3, {"positive": 100}) == [cases[2]]


def test_parse_cases_removes_model_controlled_metadata():
    """供应商输出不能伪造持久身份和映射状态，正常业务扩展列仍保留。"""
    import json

    result = casegen.parse_cases(json.dumps([{
        "name": "正常登录", "strategy": "正向", "owner": "测试组",
        "id": "victim", "case_set_id": "foreign", "mapped": True,
        "pending_complete": False, "sort_order": 999, "extras": {"id": "nested"},
    }]))
    assert result == [{"name": "正常登录", "strategy": "正向", "owner": "测试组"}]


def test_selfcheck_flags_missing_core_positive_and_negative():
    # 无正向用例 + 无反向用例：两条红字
    cases = [{"name": "边界值", "strategy": "边界"}]
    checks = casegen.selfcheck(cases)
    codes = {check["code"] for check in checks}
    assert codes == {"no_core_positive", "missing_constraint_negative"}
    assert all(check["level"] == "error" for check in checks)


def test_selfcheck_flags_positive_without_core():
    # 有正向但无 P0/核心：仍红字 no_core_positive
    cases = [
        {"name": "普通正向", "strategy": "正向", "priority": "P2"},
        {"name": "反向用例", "strategy": "反向"},
    ]
    codes = {check["code"] for check in casegen.selfcheck(cases)}
    assert codes == {"no_core_positive"}


def test_selfcheck_passes_with_core_positive_and_negative():
    # HX 正向 + 反向齐全：无红字
    cases = [
        {"name": "核心登录", "strategy": "正向", "priority": "HX"},
        {"name": "密码错误", "strategy": "反向"},
    ]
    assert casegen.selfcheck(cases) == []


def test_scale_contract_constants():
    # 规模口径：中等目标 45、硬上限 80（PRD 5.4.1）
    assert casegen.TARGET_COUNT == 45
    assert casegen.MAX_COUNT == 80


def test_clip_source_reports_truncation():
    """来源截断必须可被上层感知，否则长 PRD 后半段会静默不参与生成。"""
    short, short_truncated = casegen.clip_source("需求")
    assert short == "需求" and short_truncated is False

    long_text = "需" * (casegen.SOURCE_MAX_CHARS + 500)
    clipped, truncated = casegen.clip_source(long_text)
    assert truncated is True
    assert len(clipped) == casegen.SOURCE_MAX_CHARS


def test_parse_cases_normalizes_strategy_and_priority_aliases():
    """模型常写英文键或 P0/P1 档位；不归一会被配比裁剪当成未知策略丢弃。"""
    items = casegen.parse_cases(
        '[{"name":"登录成功","strategy":"positive","priority":"P0"},'
        '{"name":"密码错误","strategy":"negative","priority":"p2"}]'
    )
    assert [item["strategy"] for item in items] == ["正向", "反向"]
    assert [item["priority"] for item in items] == ["HX", "BJ"]


def test_selfcheck_only_checks_strategies_with_positive_weight():
    """用户显式只生成正向时，不能再按默认配比要求反向用例。"""
    cases = [{"name": "登录成功", "strategy": "正向", "priority": "HX"}]
    assert casegen.selfcheck(cases, weights={"positive": 100}) == []
    # 默认配比下仍然要求反向用例，保持既有红字语义。
    codes = {check["code"] for check in casegen.selfcheck(cases)}
    assert codes == {"missing_constraint_negative"}


def test_rebalance_reports_dropped_unknown_and_over_quota():
    """裁剪统计用于向用户解释「模型给了 N 条、实际保留 M 条」。"""
    items = [
        {"name": "正向1", "strategy": "正向"},
        {"name": "正向2", "strategy": "正向"},
        {"name": "正向3", "strategy": "正向"},
        {"name": "反向1", "strategy": "反向"},
    ]
    kept, dropped = casegen.rebalance_with_stats(items, 2, weights={"positive": 100})
    assert [item["name"] for item in kept] == ["正向1", "正向2"]
    assert dropped == {"dropped_unknown_strategy": 1, "dropped_over_quota": 1}


def test_dedupe_cases_keeps_first_and_counts_duplicates():
    """同名同策略只保留首条；名称空白差异不算不同用例。"""
    items = [
        {"name": "登录 成功", "strategy": "正向"},
        {"name": "登录成功", "strategy": "正向"},
        {"name": "登录成功", "strategy": "反向"},
        {"name": "密码错误", "strategy": "反向"},
    ]
    kept, dropped = casegen.dedupe_cases(items)
    assert [item["name"] for item in kept] == ["登录 成功", "登录成功", "密码错误"]
    assert dropped == 1


def test_extract_json_array_is_shared_tolerance_point():
    """用例生成与数据集补全共用容错解析，围栏与前后解释文字都要能处理。"""
    raw = '说明文字\n```json\n[{"name":"a"}]\n```\n结尾'
    assert casegen.extract_json_array(raw) == [{"name": "a"}]
    for broken in ("", "没有数组", '{"a":1}'):
        try:
            casegen.extract_json_array(broken)
        except ValueError:
            continue
        raise AssertionError("非法输出必须抛 ValueError")


def test_build_coverage_prompt_lists_case_summary():
    """覆盖复审只需要清单与需求，不在提示词里放全量用例正文。"""
    system, user = casegen.build_coverage_prompt(
        "需求：退款需在 3 个工作日内到账",
        [{"name": "退款到账", "module": "退款", "feature_point": "3 个工作日", "steps": "很长的步骤"}],
    )
    assert "uncovered" in system and "不要臆造" in system
    assert "退款需在 3 个工作日内到账" in user
    assert "1. [退款] 退款到账（功能点：3 个工作日）" in user
    assert "很长的步骤" not in user


def test_parse_coverage_caps_items_and_tolerates_strings():
    """覆盖结果允许纯字符串条目，字段长度与条数都要截断。"""
    import json

    raw = "```json\n" + json.dumps({
        "uncovered": ["退款超时处理"] + [
            {"requirement": f"点{index}", "reason": "x" * 400} for index in range(30)
        ],
        "notes": "n" * 400,
    }, ensure_ascii=False) + "\n```"
    result = casegen.parse_coverage(raw)
    assert result["uncovered"][0] == {"requirement": "退款超时处理", "reason": ""}
    assert len(result["uncovered"]) == casegen.COVERAGE_MAX_ITEMS
    assert all(len(item["reason"]) <= casegen.COVERAGE_MAX_FIELD_CHARS for item in result["uncovered"])
    assert len(result["notes"]) == casegen.COVERAGE_MAX_FIELD_CHARS


def test_generation_budget_scales_with_case_count():
    """输出预算随条数线性增长并封顶：40 条给 8192 会截断正文（实测 100% 失败）。"""
    assert casegen.generation_token_budget(10) == 8192
    assert casegen.generation_token_budget(20) > 8192
    assert casegen.generation_token_budget(40) == 16384
    assert casegen.generation_token_budget(80) == 16384
    assert casegen.generation_token_budget(80) <= casegen.OUTPUT_TOKEN_CEILING


def test_parse_cases_reports_entries_dropped_for_missing_name():
    """缺名称的条目必须计数：旧实现静默丢弃，用户看到条数变少却无任何提示。"""
    raw = (
        '[{"name":"有效","strategy":"正向"},'
        '{"strategy":"正向","steps":"1. 步骤","expected":"结果"},'
        '"不是对象"]'
    )
    items, stats = casegen.parse_cases_with_stats(raw)
    assert [item["name"] for item in items] == ["有效"]
    assert stats == {"dropped_missing_name": 1, "dropped_non_object": 1}
    assert casegen.parse_cases(raw) == items


def test_dedupe_cases_merges_same_steps_and_expected():
    """换名字但步骤与预期一字不差的近似重复必须合并。"""
    base = {"strategy": "正向", "module": "登录", "feature_point": "验证码有效期",
            "steps": "1. 输入手机号\n2. 输入验证码\n3. 点击登录", "expected": "登录成功并跳转首页"}
    items = [
        {**base, "name": "验证码有效期校验"},
        {**base, "name": "验证码有效期校验 第2种写法"},
        {**base, "name": "验证码过期提示", "expected": "提示验证码已过期"},
    ]
    kept, dropped = casegen.dedupe_cases(items)
    assert dropped == 1
    assert [item["name"] for item in kept] == ["验证码有效期校验", "验证码过期提示"]


def test_requirement_rules_extracts_numbered_and_constraint_lines():
    """编号列表与硬约束要进规则块；普通说明行不进，避免提示词被噪声撑满。"""
    source = "需求：上传附件。\n1. 字段 file 必填。\n2. 已退款订单不可再次申请。\n补充说明不单列。"
    rules = casegen.requirement_rules(source)
    joined = " | ".join(rules)
    assert "字段 file 必填" in joined
    assert "已退款订单不可再次申请" in joined
    assert "补充说明不单列" not in joined


def test_requirement_rules_keeps_numbered_requirement_rows():
    """PRD 表格里的 FR 编号条目要保留编号与优先级，这是功能域完整的抓手。"""
    source = (
        "| 编号 | 需求 | 优先级 |\n"
        "| --- | --- | --- |\n"
        "| FR-601 | 生成面试报告 | P0 |\n"
        "| FR-801 | 账号与权限管理 | P0 |\n"
    )
    rules = casegen.requirement_rules(source)
    joined = " | ".join(rules)
    assert "FR-601" in joined and "生成面试报告" in joined
    assert "FR-801" in joined


def test_build_prompts_requires_numbered_coverage():
    """提示词要明确 P0 一条对一条、六类策略齐备、边界与反向合计下限。"""
    source = "| FR-101 | 创建岗位 | P0 |\n| FR-601 | 生成报告 | P0 |"
    system, user = casegen.build_prompts(source, 12)
    assert "P0" in system and "一条用例对应一条" in system
    assert "边界与反向合计不低于 40%" in system
    assert "FR-101" in user and "FR-601" in user


def test_format_steps_numbers_semicolon_actions():
    """一行里用分号拼的两个操作要拆成编号步骤，已编号的多行保持原样。"""
    assert casegen.format_steps("打开上传页；选择超过 20MB 的文件") == (
        "1. 打开上传页\n2. 选择超过 20MB 的文件"
    )
    numbered = "1. 输入手机号\n2. 点击获取验证码"
    assert casegen.format_steps(numbered) == numbered
    assert casegen.format_steps("只点一次登录") == "只点一次登录"


def test_dedupe_cases_drops_near_duplicate_feature_points():
    """名称和功能点高度重合的改写只留第一条，不同规则都保留。"""
    items = [
        {"name": "重复退款申请被拦截", "strategy": "反向", "feature_point": "重复退款拦截"},
        {"name": "重复退款再次申请被拦截", "strategy": "反向", "feature_point": "重复退款拦截"},
        {"name": "缺少 file 字段时拒绝上传", "strategy": "反向", "feature_point": "必填字段校验"},
    ]
    kept, dropped = casegen.dedupe_cases(items)
    assert dropped == 1
    assert [item["feature_point"] for item in kept] == ["重复退款拦截", "必填字段校验"]


def test_dedupe_cases_keeps_pending_cases_without_content_signature():
    """预期结果留空的待澄清用例不能被内容指纹误合并。"""
    items = [
        {"strategy": "正向", "name": "待澄清A", "steps": "1. 点击搜索", "expected": ""},
        {"strategy": "正向", "name": "待澄清B", "steps": "1. 点击搜索", "expected": ""},
    ]
    assert casegen.dedupe_cases(items)[1] == 0


def test_mark_pending_complete_flags_missing_expected_or_steps():
    assert casegen.mark_pending_complete({"name": "a", "steps": "1. x", "expected": "ok"})["pending_complete"] is False
    assert casegen.mark_pending_complete({"name": "a", "steps": "1. x", "expected": "  "})["pending_complete"] is True
    assert casegen.mark_pending_complete({"name": "a", "expected": "ok"})["pending_complete"] is True

def test_split_sections_uses_markdown_headings():
    """按需求小节切分，供分批生成使用；每节要能独立成 prompt。"""
    source = (
        "## 4.1 岗位与能力模型\nFR-101 支持创建岗位\n"
        "## 4.2 材料解析\nFR-201 支持上传 PDF\n"
        "## 4.3 智能出题\nFR-301 生成蓝图\n"
    )
    sections = casegen.split_sections(source)
    assert len(sections) == 3
    assert "4.1" in sections[0]["title"]
    assert "FR-101" in sections[0]["text"]
    assert "FR-301" in sections[2]["text"]


def test_split_sections_falls_back_to_length_blocks():
    """没有标题结构时按长度切块，每块不超过上限，避免单批 prompt 失控。"""
    source = "这是一段没有标题的需求描述。" * 800
    sections = casegen.split_sections(source, max_chars=2000)
    assert len(sections) >= 3
    assert all(len(section["text"]) <= 2200 for section in sections)


def test_split_sections_returns_empty_for_blank_source():
    assert casegen.split_sections("   ") == []

def test_split_sections_stops_at_higher_level_heading():
    """功能小节不能被后续更高级章节吞掉（否则技术方案会被当成需求生成用例）。"""
    source = (
        "### 4.1 岗位与能力模型\nFR-101 创建岗位\n"
        "### 4.2 材料解析\nFR-201 上传 PDF\n"
        "## 5. LangGraph 技术方案\nload_context 节点实现细节\n"
    )
    sections = casegen.split_sections(source)
    titles = [s["title"] for s in sections]
    assert len(sections) == 2
    assert all("技术方案" not in s["text"] for s in sections)
    assert "FR-201" in sections[1]["text"]
    assert titles[1].startswith("4.2")

def test_module_label_strips_numbering_and_tags():
    """小节标题要收敛成可直接当 module 的名称。"""
    assert casegen.module_label("### 4.1 岗位与能力模型（FR-100）") == "岗位与能力模型"
    assert casegen.module_label("### 4.3 智能出题（FR-300）— 核心模块") == "智能出题"
    assert casegen.module_label("## 4.8 运营与系统管理") == "运营与系统管理"


def test_build_prompts_pins_module_when_given():
    """分批生成时把本批小节名写进提示词，禁止模型自创模块名。"""
    system, _ = casegen.build_prompts("### 4.1 岗位\nFR-101 创建岗位", 6, module_name="岗位与能力模型")
    assert "module 字段必须原样填" in system
    assert "岗位与能力模型" in system
    # 不传时不追加约束，保持 api 侧单批次行为不变
    plain, _ = casegen.build_prompts("### 4.1 岗位\nFR-101 创建岗位", 6)
    assert "module 字段必须原样填" not in plain

def test_build_review_prompt_includes_cases_and_dimensions():
    """评审提示词要包含四维定义与实际用例内容。"""
    system, user = casegen.build_review_prompt(
        "需求：登录成功后跳转首页",
        [{"module": "登录", "name": "登录成功跳转", "strategy": "正向",
          "steps": "1. 输入账号\n2. 点击登录", "expected": "跳转首页"}],
    )
    assert "覆盖度" in system and "executability" in system and "distribution" in system
    assert "登录成功跳转" in user and "跳转首页" in user


def test_parse_review_normalizes_and_clamps():
    """非法 verdict 按分数推断；缺维度补零；问题条数与分数都收敛到上限。"""
    issues = [
        {"case": f"c{i}", "type": "coverage", "detail": "d", "fix": "f"} for i in range(30)
    ]
    review = casegen.parse_review(
        json.dumps({"verdict": "weird", "score": 999, "issues": issues})
    )
    assert review["verdict"] == "pass"
    assert review["score"] == 100
    assert len(review["issues"]) == casegen.REVIEW_MAX_ISSUES
    assert review["dimensions"]["executability"] == {"score": 0, "note": ""}


def test_parse_review_rejects_non_object():
    with pytest.raises(ValueError):
        casegen.parse_review("[1, 2, 3]")
