"""用例评审与版本快照的纯函数（N-02）。

职责边界：
- 只做“用例行 → 可比较字典”的归一、两个快照的字段级 diff；
- 不访问数据库、不调用模型、不决定权限；
- 路由层负责落库、审计与状态流转。

快照是确认/评审通过时的只读副本，不替代 ``case_items`` 当前行。
"""

from __future__ import annotations

from typing import Any

# 参与 diff 的业务字段；sort_order 只用于回放排序，不作为“变更”提示。
CASE_DIFF_FIELDS: tuple[str, ...] = (
    "code",
    "strategy",
    "priority",
    "module",
    "submodule",
    "feature_point",
    "name",
    "precondition",
    "steps",
    "expected",
    "test_type",
    "extras",
)

FIELD_LABELS: dict[str, str] = {
    "code": "编号",
    "strategy": "策略",
    "priority": "优先级",
    "module": "模块",
    "submodule": "子模块",
    "feature_point": "功能点",
    "name": "用例名称",
    "precondition": "前置条件",
    "steps": "执行步骤",
    "expected": "预期结果",
    "test_type": "测试类型",
    "extras": "扩展字段",
}

# 单次 diff 最多返回的明细条数，避免超大用例集把响应撑爆。
MAX_DIFF_ITEMS = 500


def _text(value: Any) -> str:
    """把可能为 None 的字段归一成字符串，保证 diff 可比较。"""
    return "" if value is None else str(value)


def serialize_case(item: Any) -> dict[str, Any]:
    """把 ORM 用例行转换为稳定快照字典；只保留业务字段与排序。"""
    return {
        "id": item.id,
        "code": _text(getattr(item, "code", "")),
        "strategy": _text(getattr(item, "strategy", "")),
        "priority": _text(getattr(item, "priority", "")),
        "module": _text(getattr(item, "module", "")),
        "submodule": _text(getattr(item, "submodule", "")),
        "feature_point": _text(getattr(item, "feature_point", "")),
        "name": _text(getattr(item, "name", "")),
        "precondition": _text(getattr(item, "precondition", "")),
        "steps": _text(getattr(item, "steps", "")),
        "expected": _text(getattr(item, "expected", "")),
        "test_type": _text(getattr(item, "test_type", "")),
        "extras": getattr(item, "extras", None) or {},
        "sort_order": int(getattr(item, "sort_order", 0) or 0),
    }


def snapshot_cases(items: list[Any]) -> list[dict[str, Any]]:
    """按当前顺序生成用例快照。"""
    return [serialize_case(item) for item in items]


def _case_label(case: dict[str, Any]) -> str:
    """diff 展示名：优先用例名称，缺失时退回编号/ID。"""
    return _text(case.get("name")) or _text(case.get("code")) or _text(case.get("id"))


def _diff_fields(base: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    """逐字段比较，返回旧值/新值；空字符串与 None 视为等价。"""
    changes: list[dict[str, Any]] = []
    for field in CASE_DIFF_FIELDS:
        before = base.get(field)
        after = target.get(field)
        if isinstance(before, dict) or isinstance(after, dict):
            if (before or {}) == (after or {}):
                continue
        elif _text(before) == _text(after):
            continue
        changes.append(
            {
                "field": field,
                "label": FIELD_LABELS.get(field, field),
                "before": before,
                "after": after,
            }
        )
    return changes


def diff_snapshots(
    base_cases: list[dict[str, Any]],
    target_cases: list[dict[str, Any]],
    *,
    limit: int = MAX_DIFF_ITEMS,
) -> dict[str, Any]:
    """对比两个用例快照，输出新增/删除/字段变更。

    以用例 ID 为准匹配；同一 ID 只比较业务字段，排序变化不算修改。
    超过 ``limit`` 时截断明细并置 ``truncated=True``，计数仍为全量。
    """
    base_by_id = {str(item.get("id")): item for item in base_cases if item.get("id")}
    target_by_id = {str(item.get("id")): item for item in target_cases if item.get("id")}

    added: list[dict[str, Any]] = []
    for case_id, case in target_by_id.items():
        if case_id not in base_by_id:
            added.append({"id": case_id, "name": _case_label(case)})

    removed: list[dict[str, Any]] = []
    for case_id, case in base_by_id.items():
        if case_id not in target_by_id:
            removed.append({"id": case_id, "name": _case_label(case)})

    changed: list[dict[str, Any]] = []
    for case_id, target in target_by_id.items():
        base = base_by_id.get(case_id)
        if not base:
            continue
        fields = _diff_fields(base, target)
        if fields:
            changed.append(
                {
                    "id": case_id,
                    "name": _case_label(target),
                    "fields": fields,
                }
            )

    truncated = any(
        len(items) > limit for items in (added, removed, changed)
    )
    return {
        "base_count": len(base_cases),
        "target_count": len(target_cases),
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added": added[:limit],
        "removed": removed[:limit],
        "changed": changed[:limit],
        "truncated": truncated,
    }
