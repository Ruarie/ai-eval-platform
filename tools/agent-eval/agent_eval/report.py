"""报告渲染：Markdown 摘要 + 明细，便于贴到 issue 或群里。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .core import Check

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
STATUS_ICON = {"pass": "✅", "fail": "❌", "skip": "⚪", "error": "⚠️"}
SEVERITY_LABEL = {"P0": "P0 阻断", "P1": "P1 严重", "P2": "P2 一般"}


def _evidence(evidence: Any, limit: int = 900) -> str:
    if not evidence:
        return ""
    if isinstance(evidence, str):
        text = evidence
    else:
        try:
            text = json.dumps(evidence, ensure_ascii=False, indent=None)
        except (TypeError, ValueError):
            text = str(evidence)
    text = text.replace("\n", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


def render_markdown(
    checks: list[Check],
    *,
    meta: dict[str, Any],
    quality: list[dict[str, Any]] | None = None,
) -> str:
    counts: dict[str, int] = {"pass": 0, "fail": 0, "skip": 0, "error": 0}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    failures = [c for c in checks if c.status in {"fail", "error"}]
    failures.sort(key=lambda c: (SEVERITY_ORDER.get(c.severity, 9), c.suite, c.name))

    lines = [
        "# Agent 自动化全量测试报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 目标服务：{meta.get('base')}（commit {meta.get('commit')}，version {meta.get('version')}）",
        f"- 登录账号：{meta.get('user')}",
        f"- 模型模式：{meta.get('model_mode')}",
        f"- 结果：{counts['pass']} 通过 / {counts['fail']} 失败 / {counts['error']} 异常 / {counts['skip']} 跳过",
        "",
    ]

    if meta.get("notes"):
        lines += ["> " + note for note in meta["notes"]]
        lines.append("")

    lines += ["## 1. 缺陷清单", ""]
    if not failures:
        lines.append("本轮未发现失败项。")
    else:
        by_severity: dict[str, int] = {}
        for item in failures:
            by_severity[item.severity] = by_severity.get(item.severity, 0) + 1
        lines.append(
            "分布：" + "，".join(f"{SEVERITY_LABEL.get(k, k)} {v} 个" for k, v in sorted(by_severity.items()))
        )
        lines.append("")
        for index, item in enumerate(failures, start=1):
            lines.append(f"### {index}. [{item.severity}] {item.name}")
            lines.append("")
            lines.append(f"- 套件：`{item.suite}`　状态：{STATUS_ICON.get(item.status, '')} {item.status}")
            lines.append(f"- 现象：{item.detail}")
            evidence = _evidence(item.evidence)
            if evidence:
                lines.append(f"- 证据：`{evidence}`")
            lines.append("")

    lines += ["## 2. 用例明细", "", "| 套件 | 检查项 | 结果 | 等级 | 耗时 |", "| --- | --- | --- | --- | --- |"]
    for check in checks:
        lines.append(
            f"| {check.suite} | {check.name} | {STATUS_ICON.get(check.status, '')}{check.status} "
            f"| {check.severity} | {check.ms:.0f}ms |"
        )
    lines.append("")

    if quality:
        lines += [
            "## 3. 生成质量评分",
            "",
            "| 需求 | 分数 | 等级 | 条数 | 字段 | 覆盖 | 追溯 | 可执行 | 策略 | 去重 | 主要问题 |",
            "| --- | ---: | :--: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
        for item in quality:
            dims = item.get("dimensions", {})
            issues = "；".join(item.get("issues") or [])[:160]
            lines.append(
                f"| {item.get('fixture_id')} | {item.get('score')} | {item.get('grade')} | {item.get('total')} "
                f"| {dims.get('schema', 0):.0%} | {dims.get('coverage', 0):.0%} | {dims.get('trace', 0):.0%} "
                f"| {dims.get('action', 0):.0%} | {dims.get('strategy', 0):.0%} | {dims.get('dedupe', 0):.0%} "
                f"| {issues} |"
            )
        lines.append("")

    return "\n".join(lines)
