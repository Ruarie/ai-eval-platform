"""用例评审快照 diff 纯函数回归（N-02）。"""

from types import SimpleNamespace

from shared.case_review import diff_snapshots, serialize_case


def _case(case_id: str, name: str, **overrides):
    """构造最小用例对象，模拟 ORM 行。"""
    values = {
        "id": case_id,
        "strategy": "正向",
        "priority": "HX",
        "module": "登录",
        "submodule": "",
        "feature_point": "FR-101",
        "name": name,
        "precondition": "",
        "steps": "1. 打开页面",
        "expected": "进入首页",
        "test_type": "",
        "extras": {},
        "sort_order": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_serialize_case_keeps_business_fields():
    """空值归一为空字符串，扩展字段原样保留。"""
    item = serialize_case(_case("c1", "登录成功", extras={"负责人": "qa"}))
    assert item["id"] == "c1"
    assert item["name"] == "登录成功"
    assert item["extras"] == {"负责人": "qa"}
    assert item["sort_order"] == 0


def test_diff_detects_added_removed_and_changed():
    """按 ID 匹配，输出新增/删除/字段变更。"""
    base = [serialize_case(_case("c1", "登录成功")), serialize_case(_case("c2", "登录失败"))]
    target = [
        serialize_case(_case("c1", "登录成功", priority="FHX")),
        serialize_case(_case("c3", "验证码错误")),
    ]
    result = diff_snapshots(base, target)
    assert result["base_count"] == 2
    assert result["target_count"] == 2
    assert result["added_count"] == 1
    assert result["removed_count"] == 1
    assert result["changed_count"] == 1
    assert result["added"][0]["name"] == "验证码错误"
    assert result["removed"][0]["name"] == "登录失败"
    assert result["changed"][0]["fields"][0]["field"] == "priority"
    assert result["changed"][0]["fields"][0]["before"] == "HX"
    assert result["changed"][0]["fields"][0]["after"] == "FHX"


def test_diff_ignores_sort_order_and_empty_extras():
    """排序调整与空对象不应被当成业务变更。"""
    base = [serialize_case(_case("c1", "登录成功", sort_order=0, extras={}))]
    target = [serialize_case(_case("c1", "登录成功", sort_order=9, extras={}))]
    result = diff_snapshots(base, target)
    assert result["changed_count"] == 0


def test_diff_truncates_detail_but_keeps_counts():
    """超过上限只截断明细，计数仍为全量。"""
    base = []
    target = [serialize_case(_case(f"c{i}", f"用例{i}")) for i in range(5)]
    result = diff_snapshots(base, target, limit=2)
    assert result["added_count"] == 5
    assert len(result["added"]) == 2
    assert result["truncated"] is True
