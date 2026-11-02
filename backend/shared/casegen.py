"""用例生成纯函数集（PRD 5.4.1 / 后端计划 M2 W8）。

prompt 组装、模型输出解析、策略配比校正与自检红字全部为纯函数零依赖：
api 侧测试按文件路径直接加载（见 ``backend/api/tests/test_casegen.py``），
worker 执行器运行时同源引用，保证两端生成口径一致。修改时必须保持零
import 约束，prompt 文案与 ``api/app/routers/cases.py`` 的 ai-generate 对齐。
"""

from __future__ import annotations

import json

# ─── 规模与配比口径（PRD 5.4.1） ───
TARGET_COUNT = 45  # 目标条数：中等复杂度
MAX_COUNT = 80  # 硬上限：复杂 PRD；超出即 failed 提示拆分，禁止灌水
SOURCE_MAX_CHARS = 20_000  # 来源文档注入 prompt 的最大字符数（与 api 侧一致）


def generation_token_budget(target_count: int) -> int:
    """用例条数超过中等规模时增加输出预算，供 API 与 Worker 共用。"""
    return 8192 if target_count <= TARGET_COUNT else 16384

# 六大策略默认配比（正向40/反向25/边界15/等价类10/状态迁移5/场景5，与 api 侧一致）
STRATEGY_WEIGHTS = {
    "positive": 40,
    "negative": 25,
    "boundary": 15,
    "equivalence": 10,
    "state": 5,
    "scenario": 5,
}
STRATEGY_NAMES = {
    "positive": "正向",
    "negative": "反向",
    "boundary": "边界",
    "equivalence": "等价类",
    "state": "状态迁移",
    "scenario": "场景",
}

# 优先级六档（PRD 用例模板）：核心/非核心/边界问题/异常/中断/遍历
PRIORITY_VALUES = ("HX", "FHX", "BJ", "YC", "ZD", "BL")
PRIORITY_LABELS = {
    "HX": "核心",
    "FHX": "非核心",
    "BJ": "边界问题",
    "YC": "异常",
    "ZD": "中断",
    "BL": "遍历",
}

# 模型只能生成用例正文，身份、归属和工作流状态一律由服务端生成。
MODEL_RESERVED_KEYS = frozenset({
    "id", "case_set_id", "mapped", "pending_complete", "extras",
    "sort_order", "created_at", "updated_at",
})

# 策略别名：模型常写英文键或简称，若不归一会被配额裁剪当成未知策略整条丢弃。
STRATEGY_ALIASES = {
    "positive": "正向", "normal": "正向", "正向用例": "正向", "正常": "正向",
    "negative": "反向", "反向用例": "反向", "异常": "反向", "约束": "反向",
    "boundary": "边界", "边界值": "边界", "边界条件": "边界",
    "equivalence": "等价类", "equivalence class": "等价类", "等价": "等价类",
    "state": "状态迁移", "state transition": "状态迁移", "状态": "状态迁移",
    "scenario": "场景", "end-to-end": "场景", "端到端": "场景",
}

# 优先级别名：文档早期示例使用 P0/P1，模型可能照抄；统一收敛到六档。
PRIORITY_ALIASES = {
    "p0": "HX", "p1": "FHX", "p2": "BJ", "p3": "YC", "p4": "ZD",
    "critical": "HX", "high": "HX", "medium": "FHX", "low": "BJ",
    "核心": "HX", "非核心": "FHX", "边界问题": "BJ",
    "异常": "YC", "中断": "ZD", "遍历": "BL",
}


def clip_source(source_text: str) -> tuple[str, bool]:
    """按 SOURCE_MAX_CHARS 截断来源，返回 ``(文本, 是否截断)``。

    截断必须让调用方可见：一份完整 PRD 常超过 2 万字，静默截断会让后半段
    需求完全不参与生成，而用户以为覆盖了全文。
    """
    if len(source_text) <= SOURCE_MAX_CHARS:
        return source_text, False
    return source_text[:SOURCE_MAX_CHARS], True


def _alias(value: str, aliases: dict[str, str]) -> str:
    """按原值、小写、去空白依次匹配别名；未命中保持原值。"""
    key = value.strip()
    return aliases.get(key) or aliases.get(key.lower()) or key


def normalize_case(item: dict) -> dict:
    """把模型输出的策略/优先级别名收敛到平台枚举（其余字段原样保留）。"""
    normalized = dict(item)
    strategy = _alias(str(item.get("strategy") or ""), STRATEGY_ALIASES)
    normalized["strategy"] = strategy
    if item.get("priority") is not None:
        normalized["priority"] = _alias(str(item.get("priority") or ""), PRIORITY_ALIASES)
    return normalized


def validate_strategy_weights(weights: dict[str, int] | None) -> dict[str, int]:
    """校验百分比；省略的策略取零，未提供配置才使用默认配比。"""
    if weights is None:
        return dict(STRATEGY_WEIGHTS)
    if (
        not isinstance(weights, dict)
        or any(key not in STRATEGY_NAMES for key in weights)
        or any(type(value) is not int or not 0 <= value <= 100 for value in weights.values())
        or sum(weights.values()) != 100
    ):
        raise ValueError("策略配比须为六类已知策略的 0–100 整数百分比，合计 100")
    return {key: weights.get(key, 0) for key in STRATEGY_NAMES}


def build_prompts(
    source_text: str, target_count: int, weights: dict[str, int] | None = None
) -> tuple[str, str]:
    """组装六策略用例生成的中文 system / user prompt（口径对齐 api ai-generate）。"""
    weights = validate_strategy_weights(weights)
    ratio_desc = "、".join(f"{STRATEGY_NAMES[key]} {value}%" for key, value in weights.items())
    priority_desc = "、".join(f"{value}（{PRIORITY_LABELS[value]}）" for value in PRIORITY_VALUES)
    # 风险驱动、需求追溯与可观察断言参考 designing-functional-tests（MIT）：
    # https://github.com/jaktestowac/awesome-copilot-for-testers/blob/main/skills/designing-functional-tests/SKILL.md
    # 仅适配其方法原则，不复制技能正文或模板。
    system = (
        "你是资深测试设计专家，负责根据需求文档设计软件测试用例。"
        "先识别需求中的功能点、业务约束和高风险流程；高风险流程覆盖正向、反向、边界、权限及中断恢复，"
        "低风险流程按价值精简，避免为凑数量重复生成。"
        "每条用例只验证一个明确行为，feature_point 要能追溯到需求中的具体功能或规则。"
        "steps 写出可执行的具体操作，expected 写出与操作对应、可观察的结果，避免仅写“正常”或“成功”。"
        "需求未给出确定预期时不要编造；expected 留空，并在 test_type 标记“待澄清”。"
        "每条用例必须包含 strategy（策略，取值限于 正向/反向/边界/等价类/状态迁移/场景）、"
        f"priority（优先级，取值限于 {priority_desc}）、"
        "module（模块）、submodule（子模块）、feature_point（功能点）、"
        "name（测试点/用例名称）、expected（预期结果）、precondition（前置条件）、"
        "steps（可执行操作步骤）、test_type（测试类型，如 核心业务/异常处理/兼容性）。"
        "输出格式示例（仅示意结构与字段名，取值必须按当前需求重写，禁止照抄）："
        '[{"strategy":"正向","priority":"HX","module":"登录","submodule":"短信验证码",'
        '"feature_point":"验证码 5 分钟内有效","name":"有效期内输入验证码可登录",'
        '"precondition":"已获取未过期的验证码","steps":"1. 输入手机号与验证码\\n2. 点击登录",'
        '"expected":"登录成功并跳转首页","test_type":"核心业务"}]'
        "只输出一个 JSON 数组，不要输出任何解释文字或 markdown 代码围栏。"
    )
    user = (
        f"请按以下策略配比生成不超过 {target_count} 条测试用例：{ratio_desc}。\n\n"
        f"需求文档：\n{source_text}"
    )
    return system, user


def _strip_code_fence(text: str) -> str:
    """去掉模型习惯性包裹的 ```json 围栏。"""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(
            line for line in cleaned.splitlines() if not line.strip().startswith("```")
        ).strip()
    return cleaned


def extract_json_array(text: str) -> list:
    """从模型输出提取 JSON 数组（容忍代码围栏与首尾解释文字）。

    用例生成、用例补全与数据集合成共用同一段容错逻辑：任何一侧放宽或收紧
    解析规则都必须在这里改，避免两份实现长期漂移。
    """
    cleaned = _strip_code_fence(text)
    if not cleaned:
        raise ValueError("模型返回空内容")
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("模型输出无法解析为 JSON 数组")
    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, list):
        raise ValueError("模型返回的不是 JSON 数组")
    return data


def parse_cases(text: str) -> list[dict]:
    """从容错模型输出提取用例 JSON 数组（允许代码围栏与首尾解释文字）。"""
    data = extract_json_array(text)
    items = [
        normalize_case({key: value for key, value in item.items() if key not in MODEL_RESERVED_KEYS})
        for item in data if isinstance(item, dict) and item.get("name")
    ]
    if not items:
        raise ValueError("模型输出中没有含用例名称的有效条目")
    return items


def dedupe_cases(items: list[dict]) -> tuple[list[dict], int]:
    """按「策略 + 去空白小写名称」去重，返回 ``(保留项, 丢弃条数)``。

    模型容易为凑数量重复输出同名用例；配额裁剪按条数算，重复项会挤掉真正
    不同的用例，所以先去重再裁剪。缺名称的条目不参与去重（由上层判缺项）。
    """
    seen: set[tuple[str, str]] = set()
    result: list[dict] = []
    for item in items:
        name = "".join(str(item.get("name") or "").split()).lower()
        key = (str(item.get("strategy") or ""), name)
        if name and key in seen:
            continue
        if name:
            seen.add(key)
        result.append(item)
    return result, len(items) - len(result)


# ─── 需求覆盖自检（可选，独立请求，不与生成争同一条超时预算） ───
COVERAGE_MAX_ITEMS = 20
COVERAGE_MAX_FIELD_CHARS = 300


def build_coverage_prompt(
    source_text: str, cases: list[dict]
) -> tuple[str, str]:
    """组装「需求覆盖」复审提示词：找出需求中有、用例里没有的功能点。"""
    lines = []
    for index, case in enumerate(cases, start=1):
        module = str(case.get("module") or "通用").strip()
        name = str(case.get("name") or "").strip()
        feature = str(case.get("feature_point") or "未标注").strip()
        lines.append(f"{index}. [{module}] {name}（功能点：{feature}）")
    system = (
        "你是测试评审专家。给定需求文档与已生成的测试用例清单，"
        "找出需求中**明确描述**、但清单里没有任何用例覆盖的功能点或业务规则。"
        "只报告确实缺失的项：不要臆造需求中不存在的内容，不要因为措辞不同就判定缺失，"
        "不要把「已覆盖但没写全」当成缺失。"
        "每条缺失项给出 requirement（需求中的功能点摘要，≤80 字）与 reason（为什么判定未被覆盖，≤120 字）。"
        "若没有明显缺失，返回空数组并在 notes 说明覆盖情况。"
        '只输出 JSON 对象：{"uncovered":[{"requirement":"...","reason":"..."}],"notes":"..."}，'
        "不要输出解释文字或代码围栏。"
    )
    user = (
        f"需求文档：\n{source_text}\n\n"
        f"已生成用例清单（共 {len(cases)} 条）：\n" + "\n".join(lines)
    )
    return system, user


def parse_coverage(text: str) -> dict:
    """解析覆盖检查输出；严格拒绝非对象/非数组，字段长度截断到上限。"""
    cleaned = _strip_code_fence(text)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("覆盖检查输出无法解析为 JSON 对象")
    data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("覆盖检查输出必须是 JSON 对象")
    raw = data.get("uncovered") or []
    if not isinstance(raw, list):
        raise ValueError("uncovered 必须是数组")
    uncovered: list[dict[str, str]] = []
    for entry in raw[:COVERAGE_MAX_ITEMS]:
        if isinstance(entry, str):
            requirement, reason = entry.strip(), ""
        elif isinstance(entry, dict):
            requirement = str(entry.get("requirement") or entry.get("feature_point") or "").strip()
            reason = str(entry.get("reason") or "").strip()
        else:
            continue
        if not requirement:
            continue
        uncovered.append({
            "requirement": requirement[:80],
            "reason": reason[:COVERAGE_MAX_FIELD_CHARS],
        })
    notes = str(data.get("notes") or "").strip()[:COVERAGE_MAX_FIELD_CHARS]
    return {"uncovered": uncovered, "notes": notes}


def rebalance_with_stats(
    items: list[dict], max_count: int, weights: dict[str, int] | None = None,
) -> tuple[list[dict], dict[str, int]]:
    """按策略配比裁剪并返回丢弃统计：超出配比的截断，不足的保留。

    统计用于向用户解释「模型给了 N 条、实际保留 M 条」：
    ``dropped_unknown_strategy`` = 策略不在本次所选配比内的条目（含模型自创策略），
    ``dropped_over_quota`` = 同一策略超过配额或总数超过 max_count 的条目。
    """
    weights = validate_strategy_weights(weights)
    total_weight = sum(weights.values())
    quotas = {
        STRATEGY_NAMES[key]: (max(1, round(max_count * w / total_weight)) if w > 0 else 0)
        for key, w in weights.items()
    }
    dropped_unknown = 0
    dropped_over_quota = 0
    grouped: dict[str, list[dict]] = {}
    for item in items:
        strategy = str(item.get("strategy") or "")
        if quotas.get(strategy, 0) <= 0:
            dropped_unknown += 1
            continue
        grouped.setdefault(strategy, []).append(item)
    result: list[dict] = []
    for strategy, group in grouped.items():
        quota = quotas[strategy]
        result.extend(group[:quota])
        dropped_over_quota += max(0, len(group) - quota)
    if len(result) > max_count:
        dropped_over_quota += len(result) - max_count
        result = result[:max_count]
    return result, {
        "dropped_unknown_strategy": dropped_unknown,
        "dropped_over_quota": dropped_over_quota,
    }


def rebalance_by_strategy(
    items: list[dict], max_count: int, weights: dict[str, int] | None = None,
) -> list[dict]:
    """按策略配比裁剪（只取结果，丢弃统计见 ``rebalance_with_stats``）。"""
    return rebalance_with_stats(items, max_count, weights=weights)[0]


def selfcheck(cases: list[dict], weights: dict[str, int] | None = None) -> list[dict]:
    """自检红字（PRD 5.4.1 P0）：无核心正向、缺约束反向 → 确认页红字检查项。

    ``weights`` 给定时只检查权重 > 0 的策略：用户主动选择「只生成正向」时，
    再要求反向用例属于拿默认配比否定用户的显式配置。
    """
    weights = validate_strategy_weights(weights)
    checks: list[dict] = []
    if weights.get("positive", 0) > 0:
        positives = [case for case in cases if case.get("strategy") == "正向"]
        core_positives = [
            case
            for case in positives
            if case.get("priority") == "HX" or "核心" in str(case.get("test_type") or "")
        ]
        if not positives:
            checks.append({"level": "error", "code": "no_core_positive", "message": "自检未通过：未生成任何正向策略用例"})
        elif not core_positives:
            checks.append({"level": "error", "code": "no_core_positive", "message": "自检未通过：正向用例中没有 HX 核心用例"})
    if weights.get("negative", 0) > 0:
        negatives = [case for case in cases if case.get("strategy") == "反向"]
        if not negatives:
            checks.append({"level": "error", "code": "missing_constraint_negative", "message": "自检未通过：缺少反向（约束/异常）策略用例"})
    return checks
