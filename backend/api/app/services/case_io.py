"""用例集导入导出：Excel / XMind 生成与行映射（纯格式化，不涉及路由）。"""

from __future__ import annotations

import io
import time
import zipfile
from typing import Any
from xml.sax.saxutils import escape

from openpyxl import Workbook

from ..case_excel import EXPORT_FIXED_COLUMNS
from ..models import CaseItem, CaseSet, uuid_str

_RESERVED_EXTRA_KEYS = {
    "id",
    "case_set_id",
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
    "mapped",
    "pending_complete",
    "extras",
    "sort_order",
    "created_at",
    "updated_at",
}

def case_to_item(case: CaseItem) -> dict[str, Any]:
    """把用例行展开为契约用例项：固定字段 + extras 扩展键平铺。"""
    item: dict[str, Any] = {
        "id": case.id,
        "strategy": case.strategy,
        "priority": case.priority,
        "module": case.module or "",
        "submodule": case.submodule or "",
        "feature_point": case.feature_point or "",
        "name": case.name,
        "precondition": case.precondition or "",
        "steps": case.steps or "",
        "expected": case.expected or "",
        "test_type": case.test_type or "",
        "mapped": bool(case.mapped),
        "pending_complete": bool(case.pending_complete),
    }
    item.update({key: value for key, value in (case.extras or {}).items() if key not in _RESERVED_EXTRA_KEYS})
    return item


def build_xlsx(case_set: CaseSet, cases: list[CaseItem]) -> bytes:
    """生成 Excel 工作簿字节流：固定列 + column_schema 声明的扩展列。"""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "用例集"
    extra_columns = [
        (col.get("key", ""), col.get("name") or col.get("key", ""))
        for col in (case_set.column_schema or [])
    ]
    sheet.append([title for _, title in EXPORT_FIXED_COLUMNS] + [name for _, name in extra_columns])
    for case in cases:
        item = case_to_item(case)
        row: list[Any] = []
        for field, _title in EXPORT_FIXED_COLUMNS:
            value = item.get(field)
            if isinstance(value, bool):
                value = "是" if value else "否"
            row.append(value)
        row.extend((case.extras or {}).get(key) for key, _ in extra_columns)
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def xmind_topic(topic_id: str, title: str, timestamp: int, note: str = "", children: str = "") -> str:
    """拼接单个 XMind topic 节点 XML；标题与备注均做 XML 转义。"""
    parts = [f'<topic id="{topic_id}" timestamp="{timestamp}">', f"<title>{escape(title)}</title>"]
    if note:
        parts.append(f"<notes><plain>{escape(note)}</plain></notes>")
    if children:
        parts.append(f'<children><topics type="attached">{children}</topics></children>')
    parts.append("</topic>")
    return "".join(parts)


def build_xmind(case_set: CaseSet, cases: list[CaseItem]) -> bytes:
    """生成 XMind 8 文件字节流（zip：content.xml + META-INF/manifest.xml）。

    结构：根节点=用例集名，二级节点按 module 分组，叶子=用例名（expected 写入备注）。
    """
    timestamp = int(time.time() * 1000)
    modules: dict[str, list[CaseItem]] = {}
    for case in cases:
        modules.setdefault(case.module or "未分组", []).append(case)
    modules_xml = "".join(
        xmind_topic(
            uuid_str(),
            module,
            timestamp,
            children="".join(
                xmind_topic(uuid_str(), case.name, timestamp, note=case.expected or "")
                for case in group
            ),
        )
        for module, group in modules.items()
    )
    content_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" '
        'xmlns:fo="http://www.w3.org/1999/XSL/Format" '
        'xmlns:svg="http://www.w3.org/2000/svg" '
        'xmlns:xhtml="http://www.w3.org/1999/xhtml" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" version="2.0">'
        f'<sheet id="{uuid_str()}" timestamp="{timestamp}">'
        + xmind_topic(uuid_str(), case_set.name, timestamp, children=modules_xml)
        + "</sheet></xmap-content>"
    )
    manifest_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
        '<manifest xmlns="urn:xmind:xmap:xmlns:manifest:1.0">'
        '<file-entry full-path="content.xml" media-type="text/xml"/>'
        "</manifest>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.xml", content_xml)
        archive.writestr("META-INF/manifest.xml", manifest_xml)
    return buffer.getvalue()
