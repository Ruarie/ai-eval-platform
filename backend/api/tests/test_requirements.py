"""需求基线与覆盖率纯函数单测（N-01 MVP）。

shared/requirements.py 不依赖 FastAPI / SQLAlchemy，这里按文件路径直接加载，
确保 API 与 Worker 共用同一套抽取、相似度与覆盖率口径。
"""

import importlib.util
import sys
from pathlib import Path

# 共享需求解析模块路径：backend/shared/requirements.py
_REQUIREMENTS_PATH = Path(__file__).resolve().parents[2] / "shared" / "requirements.py"
_spec = importlib.util.spec_from_file_location("shared_requirements", _REQUIREMENTS_PATH)
requirements = importlib.util.module_from_spec(_spec)
# dataclass(slots=True) 在 exec 期间需要能按模块名回查；先注册再执行。
sys.modules[_spec.name] = requirements
_spec.loader.exec_module(requirements)


def test_extract_table_requirements_with_module_and_priority():
    """表格行：编号、标题、优先级与模块必须稳定抽取。"""
    text = """
## 4. 功能需求

### 4.1 登录与注册

| 编号 | 需求 | 优先级 | 模块 |
| --- | --- | --- | --- |
| FR-101 | 支持手机号加密码登录 | P0 | 登录 |
| FR-102 | 连续输错 5 次锁定 15 分钟 | P1 | 登录 |
| NFR-12 | 登录接口 P95 小于 300ms | P2 | 性能 |
"""
    items = requirements.extract_requirements(text)
    assert [item.req_no for item in items] == ["FR-101", "FR-102", "NFR-12"]
    assert items[0].title == "支持手机号加密码登录"
    assert items[0].priority == "P0"
    assert items[0].module == "登录"
    assert items[0].source_ref.startswith("第 ")
    assert items[2].priority == "P2"


def test_extract_dedupes_repeated_numbers_and_keeps_first():
    """同一编号在正文与汇总表重复出现时只保留第一次，避免覆盖率分母翻倍。"""
    text = """
FR-201 支持导出 Excel
FR-201 支持导出 Excel（重复描述）
"""
    items = requirements.extract_requirements(text)
    assert len(items) == 1
    assert items[0].req_no == "FR-201"


def test_extract_ignores_plain_text_without_numbered_requirements():
    """没有编号的普通段落不进入分母，提示用户先补编号。"""
    assert requirements.extract_requirements("用户应该可以顺利登录，页面要好看。") == []


def test_extract_supports_numbered_headings_and_generic_section_reset():
    """通用标题不继承上文模块；具体小节标题作为模块。"""
    text = """
### 4.1 订单

FR-301 下单成功后生成订单号

## 5. 非功能需求

FR-302 订单列表分页大小可配置
"""
    items = requirements.extract_requirements(text)
    assert items[0].module == "订单"
    # 进入「非功能需求」通用标题后，不应继续沿用「订单」。
    assert items[1].module == ""


def test_similarity_and_tokenize_handle_chinese_and_ascii():
    """中文双字与英文词都能参与确定性相似度。"""
    assert requirements.similarity("支持手机号登录", "手机号登录失败提示") > 0
    assert requirements.similarity("export excel", "export csv") > 0
    assert requirements.similarity("", "任意文本") == 0.0


def test_auto_link_prefers_explicit_requirement_number():
    """用例文本出现编号时，直接以 1.0 置信度命中。"""
    reqs = [{"id": "r1", "req_no": "FR-101", "title": "手机号登录", "module": "登录"}]
    cases = [
        {
            "id": "c1",
            "name": "FR-101 手机号登录成功",
            "feature_point": "FR-101",
            "module": "登录",
            "expected": "进入首页",
        }
    ]
    links = requirements.auto_link_requirements(reqs, cases)
    assert len(links) == 1
    assert links[0]["requirement_id"] == "r1"
    assert links[0]["confidence"] == 1.0
    assert links[0]["reason"] == "编号命中"


def test_auto_link_returns_title_match_candidate():
    """标题被完整包含时返回 0.8 候选，供人工确认。"""
    reqs = [{"id": "r1", "req_no": "FR-102", "title": "连续输错锁定", "module": "登录"}]
    cases = [
        {
            "id": "c1",
            "name": "连续输错锁定后提示剩余时间",
            "feature_point": "连续输错锁定",
            "module": "登录",
        }
    ]
    links = requirements.auto_link_requirements(reqs, cases)
    assert links and links[0]["confidence"] == 0.8
    assert links[0]["reason"] == "标题命中"


def test_build_coverage_counts_p0_and_uncovered_modules():
    """覆盖率分母只包含传入需求，未关联需求进入 uncovered。"""
    reqs = [
        {"id": "r1", "req_no": "FR-101", "title": "登录", "priority": "P0", "module": "登录"},
        {"id": "r2", "req_no": "FR-102", "title": "锁定", "priority": "P1", "module": "登录"},
        {"id": "r3", "req_no": "NFR-1", "title": "性能", "priority": "P0", "module": "性能"},
    ]
    cases = [
        {"id": "c1", "name": "登录成功"},
        {"id": "c2", "name": "未关联用例"},
    ]
    links = [{"requirement_id": "r1", "case_item_id": "c1"}]
    coverage = requirements.build_coverage(reqs, cases, links)
    assert coverage["total"] == 3
    assert coverage["covered"] == 1
    assert coverage["coverage_percent"] == 33.3
    assert coverage["p0_total"] == 2
    assert coverage["p0_covered"] == 1
    assert coverage["p0_percent"] == 50.0
    assert [row["req_no"] for row in coverage["uncovered"]] == ["FR-102", "NFR-1"]
    assert coverage["linked_case_count"] == 1
    assert coverage["unlinked_case_count"] == 1
    login_module = next(row for row in coverage["modules"] if row["module"] == "登录")
    assert login_module == {
        "module": "登录",
        "total": 2,
        "covered": 1,
        "coverage_percent": 50.0,
    }
