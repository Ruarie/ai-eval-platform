"""需求基线与用例覆盖的共享解析能力。

设计边界：

- 只从需求原文抽取**已存在**的编号条目（FR-/NFR-/BR-/SR-），不扩写、不臆造；
- 解析结果必须允许人工校对，覆盖率只统计已确认的需求条目；
- 覆盖率是“有用例关联”的事实统计，不代表功能正确或已验证；
- 自动关联只做候选提示，落库前仍需经过接口的显式调用，不静默改写用例。

本模块被 API 与 Worker 共用，不依赖 FastAPI / SQLAlchemy，便于单测。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# 需求编号：兼容 FR-101 / FR_101 / FR 101 / NFR-12 / BR-3 / SR-01。
_REQUIREMENT_NO = re.compile(r"\b(FR|NFR|BR|SR)[-_ ]?(\d{2,4})\b", re.IGNORECASE)
# 优先级：只认 P0–P3，避免把普通数字误判为优先级。
_PRIORITY = re.compile(r"\bP([0-3])\b", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
_LIST_PREFIX = re.compile(r"^\s*(?:[-*+•]|\d+[.、．)])\s*")
_GENERIC_MODULES = {
    "功能需求",
    "需求",
    "需求清单",
    "需求说明",
    "背景",
    "目标",
    "概述",
    "非功能需求",
    "验收标准",
    "范围",
}


@dataclass(frozen=True, slots=True)
class ParsedRequirement:
    """一条从原文抽取的需求条目；``source_ref`` 保留可回查的位置。"""

    req_no: str
    title: str
    priority: str
    module: str
    source_ref: str


def _clean_text(value: str) -> str:
    """压缩空白并去掉表格竖线与常见 Markdown 装饰。"""
    text = str(value or "").replace("|", " ")
    text = re.sub(r"[`*_~]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" :：-—")


def _module_from_heading(title: str) -> str:
    """把「4.1 登录与注册（FR-100）」收敛成「登录与注册」。"""
    text = _clean_text(title)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^\d+(?:\.\d+)*[.、]?\s*", "", text)
    text = re.sub(r"[（(]\s*(?:FR|NFR|BR|SR)[-_ ]?\d{2,4}\s*[)）]", "", text, flags=re.IGNORECASE)
    text = re.split(r"\s*[—–]\s*|\s+-\s+", text)[0]
    text = text.strip()
    return "" if text in _GENERIC_MODULES else text[:40]


def _table_title(line: str, req_no: str) -> tuple[str, str]:
    """从表格行里挑出标题与可能的模块列。

    表格没有统一列定义，只做保守推断：优先取编号右侧第一个非优先级、
    长度足够的单元格作为标题；其余单元格若像模块名，作为模块兜底。
    """
    cells = [_clean_text(cell) for cell in line.strip().strip("|").split("|")]
    cells = [cell for cell in cells if cell]
    index = next((i for i, cell in enumerate(cells) if req_no.lower() in cell.lower()), -1)
    candidates = cells[index + 1 :] if index >= 0 else cells
    title = ""
    module = ""
    for cell in candidates:
        if _PRIORITY.fullmatch(cell):
            continue
        if not title and len(cell) >= 2:
            title = cell
            continue
        if title and not module and len(cell) <= 40 and not _PRIORITY.search(cell):
            module = cell
    return title, module


def extract_requirements(text: str, *, max_items: int = 300) -> list[ParsedRequirement]:
    """从需求原文抽取编号条目，按出现顺序去重。

    只识别带明确编号的行：这是当前用例生成提示词已经在使用的同一口径，
    避免把普通段落误判成需求，导致覆盖率分母虚高。
    """
    source = str(text or "")
    if not source.strip():
        return []

    current_module = ""
    seen: set[str] = set()
    items: list[ParsedRequirement] = []

    for line_no, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        heading = _HEADING.match(line)
        if heading:
            # 进入新的标题层级时重置模块；通用标题（功能需求/背景等）不继承上文模块。
            current_module = _module_from_heading(heading.group(2))

        match = _REQUIREMENT_NO.search(line)
        if not match:
            continue

        req_no = f"{match.group(1).upper()}-{match.group(2)}"
        if req_no in seen:
            continue
        seen.add(req_no)

        title, module_hint = ("", "")
        if "|" in line:
            title, module_hint = _table_title(line, req_no)

        # 非表格行：去掉列表符号、编号与优先级后作为标题。
        if not title:
            title = _LIST_PREFIX.sub("", line)
            title = _REQUIREMENT_NO.sub(" ", title)
            title = _PRIORITY.sub(" ", title)
            title = _clean_text(title)

        priority_match = _PRIORITY.search(line)
        priority = f"P{priority_match.group(1)}" if priority_match else ""
        module = module_hint or current_module

        if not title:
            title = f"{module} {req_no}".strip() or req_no
        items.append(
            ParsedRequirement(
                req_no=req_no,
                title=title[:160],
                priority=priority,
                module=module[:40],
                source_ref=f"第 {line_no} 行",
            )
        )
        if len(items) >= max_items:
            break

    return items


def tokenize(value: str) -> set[str]:
    """轻量中英文分词：英文按词、中文按双字，供确定性相似度使用。"""
    text = str(value or "").lower()
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    tokens: set[str] = set()
    for chunk in text.split():
        if re.fullmatch(r"[0-9a-z]+", chunk):
            if len(chunk) >= 2:
                tokens.add(chunk)
            continue
        # 中文按双字切分；单字对短标题仍有意义，额外保留。
        if len(chunk) == 1:
            tokens.add(chunk)
        else:
            tokens.update(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return tokens


def similarity(left: str, right: str) -> float:
    """Dice 相似度，返回 0–1；空文本为 0。"""
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    return 2.0 * overlap / (len(left_tokens) + len(right_tokens))


def _requirement_text(requirement: Mapping[str, Any]) -> str:
    """把需求条目拼成用于匹配的文本，标题权重最高。"""
    parts = [
        str(requirement.get("req_no") or ""),
        str(requirement.get("title") or ""),
        str(requirement.get("module") or ""),
    ]
    return " ".join(part for part in parts if part)


def auto_link_requirements(
    requirements: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    *,
    threshold: float = 0.34,
) -> list[dict[str, Any]]:
    """为每条用例挑一个最可能的需求，返回待人工确认的关联候选。

    优先级：
    1. 用例文本里直接出现需求编号 → 置信度 1.0；
    2. 文本相似度 + 模块一致加成 → 达到阈值才返回。

    只返回每条用例最多一条关联，避免把“可能相关”堆成噪音。
    """
    results: list[dict[str, Any]] = []
    if not requirements or not cases:
        return results

    for case in cases:
        case_id = str(case.get("id") or "")
        if not case_id:
            continue
        case_text = " ".join(
            str(case.get(key) or "")
            for key in ("name", "feature_point", "module", "expected")
        )
        case_module = str(case.get("module") or "")
        best: tuple[float, Mapping[str, Any], str] | None = None
        for requirement in requirements:
            req_no = str(requirement.get("req_no") or "")
            if req_no and req_no.lower() in case_text.lower():
                best = (1.0, requirement, "编号命中")
                break
            req_title = str(requirement.get("title") or "").strip()
            if len(req_title) >= 4 and req_title in case_text:
                best = (0.8, requirement, "标题命中")
                continue
            score = similarity(case_text, _requirement_text(requirement))
            if case_module and case_module == str(requirement.get("module") or ""):
                score = min(1.0, score + 0.08)
            if best is None or score > best[0]:
                best = (score, requirement, "文本相似")
        if best is None or best[0] < threshold:
            continue
        results.append(
            {
                "case_item_id": case_id,
                "requirement_id": str(best[1].get("id") or ""),
                "confidence": round(float(best[0]), 4),
                "reason": best[2],
            }
        )
    return results


def build_coverage(
    requirements: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    links: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """按“需求 → 关联用例”计算覆盖率与模块缺口。

    分母只包含传入的需求条目（调用方应只传已确认基线）；
    未关联任何用例的需求进入 ``uncovered``，供页面和导出使用。
    """
    case_by_id = {str(case.get("id")): case for case in cases if case.get("id")}
    all_case_ids = set(case_by_id)
    linked: dict[str, set[str]] = {}
    for link in links:
        req_id = str(link.get("requirement_id") or "")
        case_id = str(link.get("case_item_id") or "")
        if req_id and case_id:
            linked.setdefault(req_id, set()).add(case_id)

    requirement_rows: list[dict[str, Any]] = []
    module_stats: dict[str, dict[str, int]] = {}
    covered_count = 0
    p0_total = 0
    p0_covered = 0

    for requirement in requirements:
        req_id = str(requirement.get("id") or "")
        case_ids = sorted(linked.get(req_id, set()) & all_case_ids)
        covered = bool(case_ids)
        covered_count += 1 if covered else 0
        priority = str(requirement.get("priority") or "")
        if priority.upper() == "P0":
            p0_total += 1
            p0_covered += 1 if covered else 0
        module = str(requirement.get("module") or "未分模块")
        bucket = module_stats.setdefault(module, {"total": 0, "covered": 0})
        bucket["total"] += 1
        bucket["covered"] += 1 if covered else 0
        requirement_rows.append(
            {
                "id": req_id,
                "req_no": str(requirement.get("req_no") or ""),
                "title": str(requirement.get("title") or ""),
                "priority": priority,
                "module": str(requirement.get("module") or ""),
                "covered": covered,
                "case_count": len(case_ids),
                "case_ids": case_ids,
                "case_names": [
                    str(case_by_id[case_id].get("name") or "")
                    for case_id in case_ids[:3]
                ],
            }
        )

    total = len(requirement_rows)
    linked_case_ids = {case_id for ids in linked.values() for case_id in ids if case_id in case_by_id}
    modules = [
        {
            "module": module,
            "total": stats["total"],
            "covered": stats["covered"],
            "coverage_percent": round(stats["covered"] * 100.0 / stats["total"], 1) if stats["total"] else 0.0,
        }
        for module, stats in sorted(module_stats.items(), key=lambda item: (-item[1]["total"], item[0]))
    ]

    return {
        "total": total,
        "covered": covered_count,
        "coverage_percent": round(covered_count * 100.0 / total, 1) if total else 0.0,
        "p0_total": p0_total,
        "p0_covered": p0_covered,
        "p0_percent": round(p0_covered * 100.0 / p0_total, 1) if p0_total else 0.0,
        "requirements": requirement_rows,
        "uncovered": [row for row in requirement_rows if not row["covered"]],
        "modules": modules,
        "linked_case_count": len(linked_case_ids),
        "unlinked_case_count": max(0, len(case_by_id) - len(linked_case_ids)),
    }


_DIFF_FIELDS = (
    ("title", "标题"),
    ("priority", "优先级"),
    ("module", "模块"),
    ("description", "描述"),
)


def _requirement_key(item: Mapping[str, Any]) -> str:
    """按需求编号匹配版本；编号缺失时退回 ID，仍保持稳定。"""
    req_no = str(item.get("req_no") or "").strip().upper()
    return req_no or str(item.get("id") or "")


def _diff_item(item: Mapping[str, Any], *, fields: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """输出需求条目的稳定结构，供 API 直接序列化。"""
    return {
        "id": str(item.get("id") or ""),
        "req_no": str(item.get("req_no") or ""),
        "title": str(item.get("title") or ""),
        "priority": str(item.get("priority") or ""),
        "module": str(item.get("module") or ""),
        "fields": fields or [],
    }


def diff_requirements(
    base_items: Sequence[Mapping[str, Any]],
    target_items: Sequence[Mapping[str, Any]],
    *,
    limit: int = 500,
) -> dict[str, Any]:
    """对比两版需求条目。

    匹配以需求编号优先；输出新增、删除、字段修改三类。排序变化不算修改，
    空字符串与缺失值等价。明细最多 ``limit`` 条，但计数保持全量。
    """
    base_map: dict[str, Mapping[str, Any]] = {}
    for item in base_items:
        base_map[_requirement_key(item)] = item
    target_map: dict[str, Mapping[str, Any]] = {}
    for item in target_items:
        target_map[_requirement_key(item)] = item

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    added_count = removed_count = changed_count = 0

    for key, item in target_map.items():
        if key not in base_map:
            added_count += 1
            if len(added) < limit:
                added.append(_diff_item(item))
            continue
        base = base_map[key]
        fields: list[dict[str, str]] = []
        for field, label in _DIFF_FIELDS:
            before = str(base.get(field) or "").strip()
            after = str(item.get(field) or "").strip()
            if before != after:
                fields.append({"field": field, "label": label, "before": before, "after": after})
        if fields:
            changed_count += 1
            if len(changed) < limit:
                changed.append(_diff_item(item, fields=fields))

    for key, item in base_map.items():
        if key not in target_map:
            removed_count += 1
            if len(removed) < limit:
                removed.append(_diff_item(item))

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "added_count": added_count,
        "removed_count": removed_count,
        "changed_count": changed_count,
        "truncated": any(
            count > limit for count in (added_count, removed_count, changed_count)
        ),
    }
