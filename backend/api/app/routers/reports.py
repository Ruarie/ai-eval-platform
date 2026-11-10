"""报告中心接口（API.md §3.11）：列表 / 详情 / 样本明细 / Markdown 导出 / 免登分享 / 基线冻结。

报告行由 Worker 在评测任务成功后写入；详情支持登录 Cookie 或未过期 ?share= 免登访问。
benchmark 样本明细来自 Worker 落库的 ``eval_items``；RAG/stress 段暂未开放，
前端在无数据时必须展示空态/错误态，禁止用静态报告顶替（API.md §12.3）。
"""

import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, get_current_user_optional
from ..errors import AppError, ErrorCode
from ..models import Dataset, EvalItem, ProtocolProfile, Report, Task, User

router = APIRouter(prefix="/api/reports", tags=["reports"])

_KIND_LABELS = {
    "benchmark": "Benchmark 报告",
    "rag": "RAG 评测报告",
    "stress": "共享压测报告",
    "testcase": "用例生成报告",
}


def _child_stress_report_id(db: Session, task: Task | None) -> str | None:
    """先评后压：质量任务派生的压测子任务所对应的报告 ID。"""
    if not task:
        return None
    child = (
        db.query(Task)
        .filter(Task.parent_task_id == task.id, Task.kind == "stress")
        .order_by(Task.created_at.asc())
        .first()
    )
    if not child:
        return None
    child_report = db.query(Report).filter(Report.task_id == child.id).first()
    return child_report.id if child_report else None


def _parent_report_id(db: Session, task: Task | None) -> str | None:
    """压测任务回溯父质量任务的报告 ID。"""
    if not task or not task.parent_task_id:
        return None
    parent_report = db.query(Report).filter(Report.task_id == task.parent_task_id).first()
    return parent_report.id if parent_report else None


def _title_with_datasets(report: Report, task: Task | None, datasets: dict[str, Dataset]) -> str:
    """按契约示例风格生成报告标题；数据集由调用方批量载入，避免列表逐行查库。"""
    label = _KIND_LABELS.get(report.kind, f"{report.kind} 报告")
    config = (task.config or {}) if task else {}
    dataset_id = config.get("dataset_id")
    ds = datasets.get(dataset_id) if dataset_id else None
    if ds:
        return f"{label} · {ds.name} v{ds.version}"
    return f"{label} · 任务 {report.task_id[:8]}"


def _title(db: Session, report: Report, task: Task | None) -> str:
    """单条报告标题（详情/导出路径复用），内部按需查一次数据集。"""
    config = (task.config or {}) if task else {}
    dataset_id = config.get("dataset_id")
    datasets: dict[str, Dataset] = {}
    if dataset_id:
        ds = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if ds:
            datasets[ds.id] = ds
    return _title_with_datasets(report, task, datasets)


def _child_stress_report_ids(db: Session, task_ids: list[str]) -> dict[str, str]:
    """批量解析「先评后压」子报告：返回父任务 ID → 压测报告 ID。

    列表页原先每行查两次（子任务 + 子报告），100 条上限会产生数百条 SQL。
    这里一次取出所有子任务，再一次取出对应报告，语义与 `_child_stress_report_id` 一致
    （同父任务取最早创建的子任务）。
    """
    if not task_ids:
        return {}
    children = (
        db.query(Task.id, Task.parent_task_id)
        .filter(Task.parent_task_id.in_(task_ids), Task.kind == "stress")
        .order_by(Task.created_at.asc())
        .all()
    )
    first_child: dict[str, str] = {}
    for child_id, parent_id in children:
        if parent_id:
            first_child.setdefault(parent_id, child_id)
    if not first_child:
        return {}
    reports = (
        db.query(Report.task_id, Report.id)
        .filter(Report.task_id.in_(list(first_child.values())))
        .all()
    )
    report_by_task = {task_id: report_id for task_id, report_id in reports}
    return {
        parent_id: report_by_task[child_id]
        for parent_id, child_id in first_child.items()
        if child_id in report_by_task
    }


def _baseline_matches(current: dict, candidate: dict) -> bool:
    """基线可比对口径（F-BM-07）：同 dataset 版本 + 主指标才允许对比。"""
    return (
        current.get("dataset_id") is not None
        and current.get("dataset_id") == candidate.get("dataset_id")
        and current.get("dataset_version") == candidate.get("dataset_version")
        and current.get("metric") == candidate.get("metric")
    )


def _find_baseline(db: Session, report: Report) -> Report | None:
    """在已冻结的 benchmark 基线中找同数据集版本 + 主指标的最新一条（排除自身）。"""
    if report.kind != "benchmark":
        return None
    metrics = report.metrics if isinstance(report.metrics, dict) else {}
    if not metrics.get("dataset_id"):
        return None
    candidates = (
        db.query(Report)
        .filter(Report.kind == "benchmark", Report.is_baseline.is_(True), Report.id != report.id)
        .order_by(Report.created_at.desc())
        .all()
    )
    for candidate in candidates:
        cand_metrics = candidate.metrics if isinstance(candidate.metrics, dict) else {}
        if _baseline_matches(metrics, cand_metrics):
            return candidate
    return None


def _degraded_vs_baseline(metrics: dict, baseline_scores: list) -> bool:
    """任一同 profile 主指标较基准下降 ≥5pp 即判定退化（与 RAG 5pp 口径一致）。"""
    if not baseline_scores:
        return False
    base = {
        item.get("profile_id"): item.get("score")
        for item in baseline_scores
        if isinstance(item, dict)
    }
    for item in (metrics or {}).get("scores") or []:
        if not isinstance(item, dict):
            continue
        base_score = base.get(item.get("profile_id"))
        current = item.get("score")
        if (
            isinstance(base_score, int | float)
            and isinstance(current, int | float)
            # round 消除浮点表示误差(0.65-0.70 实为 -0.04999...),保证 5pp 阈值判定稳定
            and round(current - base_score, 6) <= -0.05
        ):
            return True
    return False


def _report_json(db: Session, report: Report) -> dict:
    """装配契约公共头；metrics JSONB 原样展开，富字段（scores/sample_items 等）随执行器落地自动透出。"""
    task = db.query(Task).filter(Task.id == report.task_id).first()
    metrics = report.metrics if isinstance(report.metrics, dict) else {}
    # 基线对比（F-BM-07）：baseline_id 指向同数据集版本 + 主指标的可比基准；
    # baseline_scores 原样透出供前端并排计算 Δ；degraded 为契约公共头布尔
    baseline = _find_baseline(db, report)
    baseline_scores = (
        baseline.metrics.get("scores") or []
        if baseline and isinstance(baseline.metrics, dict)
        else []
    )
    body = {
        "id": report.id,
        "task_id": report.task_id,
        "child_stress_report_id": _child_stress_report_id(db, task),
        "parent_report_id": _parent_report_id(db, task),
        "kind": report.kind,
        "title": _title(db, report, task),
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "snapshot": (task.config or {}) if task else {},
        # 对比基准报告 ID：无可比基线（含版本/指标不一致）时为 null
        "baseline_id": baseline.id if baseline else None,
        "degraded": _degraded_vs_baseline(metrics, baseline_scores),
    }
    if baseline:
        body["baseline_scores"] = baseline_scores
    # metrics 内的富字段（scores / rag_scores / qps_peak ...）平铺到顶层，与契约详情结构对齐
    if isinstance(report.metrics, dict):
        body.update(report.metrics)
    return body


def _report_markdown(db: Session, report: Report) -> str:
    """最小 Markdown 导出：标题 + 公共头 + metrics 键值表。"""
    data = _report_json(db, report)
    lines = [
        f"# {data['title']}",
        "",
        f"- 报告 ID：`{report.id}`",
        f"- 关联任务：`{report.task_id}`",
        f"- 类型：{report.kind}",
        f"- 生成时间：{data['created_at'] or '—'}",
        "",
        "## 指标",
        "",
        "| 键 | 值 |",
        "| --- | --- |",
    ]
    metrics = report.metrics if isinstance(report.metrics, dict) else {}
    if metrics:
        for key, value in metrics.items():
            lines.append(f"| {key} | {value} |")
    else:
        lines.append("| — | 暂无指标数据 |")
    return "\n".join(lines) + "\n"


@router.get("")
def list_reports(
    kind: str | None = None,
    task_id: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """报告列表：支持 kind / task_id 过滤与分页，按创建时间倒序。"""
    query = db.query(Report)
    if kind:
        query = query.filter(Report.kind == kind)
    if task_id:
        query = query.filter(Report.task_id == task_id)
    # count() 会把整行包进子查询，metrics / share_token 仍会被数据库读出。只数主键。
    total = query.with_entities(func.count(Report.id)).scalar() or 0
    # 列表不返回指标与分享令牌。metrics 可能很大，share_token 只允许详情通道按需读取。
    rows = (
        query.order_by(Report.created_at.desc())
        .offset(offset)
        .limit(limit)
        .with_entities(Report.id, Report.kind, Report.task_id, Report.created_at)
        .all()
    )
    # 批量载入任务、数据集与派生压测报告，避免逐行查询（原实现单页最多数百条 SQL）。
    # 标题只需要 config.dataset_id，不读 result / progress。
    task_ids = list({row.task_id for row in rows if row.task_id})
    tasks = {
        task.id: task
        for task in db.query(Task.id, Task.config).filter(Task.id.in_(task_ids)).all()
    } if task_ids else {}
    dataset_ids = {
        (task.config or {}).get("dataset_id")
        for task in tasks.values()
        if (task.config or {}).get("dataset_id")
    }
    datasets = {
        dataset.id: dataset
        for dataset in db.query(Dataset.id, Dataset.name, Dataset.version)
        .filter(Dataset.id.in_(list(dataset_ids)))
        .all()
    } if dataset_ids else {}
    child_reports = _child_stress_report_ids(db, task_ids)
    items = []
    for row in rows:
        task = tasks.get(row.task_id)
        items.append(
            {
                "id": row.id,
                "title": _title_with_datasets(row, task, datasets),
                "kind": row.kind,
                "task_id": row.task_id,
                "child_stress_report_id": child_reports.get(row.task_id),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return {"items": items, "total": total}


@router.get("/{report_id}")
def get_report(
    report_id: str,
    fmt: str | None = None,
    share: str | None = None,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """报告详情；登录 Cookie 或未过期 `?share=` 免登访问；`?fmt=md` 导出 Markdown。"""
    if user is None and not share:
        # 未登录且未携带分享令牌：查库前直接拒绝
        raise AppError(ErrorCode.UNAUTHORIZED, "没有权限做这件事", status_code=401)
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise AppError(ErrorCode.NOT_FOUND, "报告不存在或已删除")
    if user is None:
        # 免登分享通道：token 匹配且未过期才放行只读详情
        token_valid = (
            report.share_token
            and secrets.compare_digest(report.share_token.encode(), (share or "").encode())
            and report.share_expire_at
            and report.share_expire_at > datetime.now(UTC)
        )
        if not token_valid:
            raise AppError(ErrorCode.UNAUTHORIZED, "没有权限做这件事", status_code=401)
    if fmt == "md":
        return PlainTextResponse(_report_markdown(db, report), media_type="text/markdown; charset=utf-8")
    return _report_json(db, report)


@router.get("/{report_id}/samples")
def report_samples(
    report_id: str,
    filter: str = Query(default="all", pattern="^(all|diff|fail)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """样本级逐题比对（API §3.11）：按行聚合各 profile 预测，支持 all/diff/fail 过滤。

    数据全部来自 Worker 写入的 ``eval_items``（含 Raw 报文，超 32KB 已截断），
    浏览器只做只读回放；非 benchmark 报告暂未提供样本明细，返回空集与说明。
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise AppError(ErrorCode.NOT_FOUND, "报告不存在或已删除")
    if report.kind != "benchmark":
        return {"items": [], "total": 0, "note": "该类型报告暂未提供样本明细"}

    items = (
        db.query(EvalItem)
        .filter(EvalItem.task_id == report.task_id)
        .order_by(EvalItem.row_no.asc(), EvalItem.profile_id.asc())
        .all()
    )
    profile_ids = {item.profile_id for item in items}
    profiles = {
        profile.id: profile
        for profile in db.query(ProtocolProfile).filter(ProtocolProfile.id.in_(profile_ids)).all()
    }

    # 按行号聚合为逐题比对条目（行数上限 2 万，内存聚合可控）
    grouped: dict[int, list[EvalItem]] = {}
    for item in items:
        grouped.setdefault(item.row_no, []).append(item)

    rows: list[dict[str, Any]] = []
    for row_no, predictions in grouped.items():
        scores = [p.score for p in predictions if p.score is not None]
        # 差异行：各 profile 得分不全一致，或部分成功部分失败
        diff = len({round(s, 6) for s in scores}) > 1 or bool(
            any(p.error for p in predictions) and scores
        )
        has_fail = any(p.error for p in predictions) or (scores and all(s == 0 for s in scores))
        if filter == "fail" and not has_fail:
            continue
        if filter == "diff" and not diff:
            continue
        rows.append(
            {
                "row_no": row_no,
                "question": predictions[0].question,
                "reference": predictions[0].reference,
                "context": predictions[0].context,
                "diff": diff,
                "predictions": [
                    {
                        "profile_id": p.profile_id,
                        "profile_name": profiles[p.profile_id].name if p.profile_id in profiles else None,
                        "model": profiles[p.profile_id].model if p.profile_id in profiles else None,
                        "output": p.output,
                        "score": p.score,
                        "exact": p.exact,
                        "rouge_l": p.rouge_l,
                        "latency_ms": p.latency_ms,
                        "usage": p.usage,
                        "judge_score": p.judge_score,
                        "judge_reason": p.judge_reason,
                        "error": p.error,
                        "raw": p.raw,
                    }
                    for p in predictions
                ],
            }
        )

    rows.sort(key=lambda entry: entry["row_no"])
    total = len(rows)
    return {"items": rows[offset : offset + limit], "total": total}


@router.post("/{report_id}/share")
def share_report(
    report_id: str,
    body: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """旧报告只读，不再生成新的分享凭证。"""
    raise AppError(ErrorCode.VALIDATION, "历史报告仅支持只读查询")


@router.post("/{report_id}/baseline")
def freeze_baseline(
    report_id: str,
    body: dict[str, Any] | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """旧报告只读，不再修改对比基线。"""
    raise AppError(ErrorCode.VALIDATION, "历史报告仅支持只读查询")
