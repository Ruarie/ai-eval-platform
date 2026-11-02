"""L3：真实模型下的用例质量评测。

需要可用的 Agent 协议档（真实 URL / 模型 / API Key）。每条夹具生成一次，
用规则评分器打分并输出维度明细；分数低于阈值即判失败。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .core import Api, Recorder, expect, expect_status
from .fixtures import FIXTURES
from .grader import QualityReport, grade

PASS_SCORE = 70.0


def run_quality(
    rec: Recorder,
    api: Api,
    *,
    fixtures: list[dict] | None = None,
    weights: dict[str, int] | None = None,
    on_report: Callable[[QualityReport], None] | None = None,
) -> list[QualityReport]:
    reports: list[QualityReport] = []
    for fixture in fixtures or FIXTURES:
        def one(fixture: dict = fixture) -> tuple[str, dict[str, Any]]:
            resp = api.post(
                "/api/case-sets/ai-generate",
                {
                    "source_text": fixture["text"],
                    "max_count": fixture["max_count"],
                    **({"strategy_weights": weights} if weights else {}),
                },
                timeout=300,
            )
            expect_status(resp, 200, f"{fixture['title']} 生成")
            body = resp.body if isinstance(resp.body, dict) else {}
            items = body.get("items") or []
            # pending_complete 是服务端在返回前打上的待补全标记，不是模型写出的身份字段。
            graded = [
                {key: value for key, value in item.items() if key != "pending_complete"}
                for item in items
                if isinstance(item, dict)
            ]
            report = grade(
                graded,
                source_text=fixture["text"],
                expected_points=fixture["expected_points"],
                weights=weights or {"positive": 40, "negative": 25, "boundary": 15,
                                    "equivalence": 10, "state": 5, "scenario": 5},
                max_count=fixture["max_count"],
                ambiguity=bool(fixture.get("ambiguity")),
                fixture_id=fixture["id"],
            )
            reports.append(report)
            if on_report:
                on_report(report)
            expect(
                report.score >= PASS_SCORE,
                f"质量分 {report.score:.1f}（{report.grade}）低于阈值 {PASS_SCORE}："
                + "；".join(report.issues[:4]),
                report=report.as_dict(),
                checks=body.get("checks"),
                dropped=body.get("dropped"),
            )
            return (
                f"{report.score:.1f} 分/{report.grade}，{report.total} 条，"
                f"覆盖 {report.dimensions['coverage']:.0%}",
                report.as_dict(),
            )

        rec.run("quality", f"用例质量 · {fixture['title']}", one, severity="P1")
    return reports
