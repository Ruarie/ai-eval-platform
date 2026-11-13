"""契约模型：agent 域。

由 ``app.schemas`` 统一重导出，调用方导入路径不变。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .accounts import (
    ApiModel,
)


class GoldQaGenerateIn(ApiModel):
    """按知识库文档生成黄金 QA 候选，不直接入库。"""

    max_count: int = Field(default=8, ge=1, le=20)

class GoldQaDraftOut(ApiModel):
    """一条尚未入库的黄金 QA 候选。"""

    question: str
    reference: str
    expected_doc_ids: list[str] = Field(default_factory=list)

class GoldQaGenerateOut(ApiModel):
    """黄金 QA 候选。确认后仍走原有上传接口入库。"""

    items: list[GoldQaDraftOut]
    source_truncated: bool = False

class RequirementBaselineCreate(ApiModel):
    """创建需求基线：只接收原文，解析由服务端完成。"""

    name: str = Field(min_length=1, max_length=120)
    source_text: str = Field(min_length=1, max_length=500_000)
    source_kind: Literal["text", "file"] = "text"
    source_name: str = Field(default="", max_length=255)

class RequirementItemOut(ApiModel):
    """需求条目响应。"""

    id: str
    req_no: str
    title: str
    description: str = ""
    priority: str = ""
    module: str = ""
    source_ref: str = ""
    sort_order: int = 0

class RequirementBaselineOut(ApiModel):
    """需求基线列表项。"""

    id: str
    parent_id: str | None = None
    name: str
    source_kind: str
    source_name: str
    status: str
    revision: int = 1
    requirement_count: int
    created_by: str | None = None
    created_at: Any | None = None
    updated_at: Any | None = None

class RequirementBaselineDetailOut(RequirementBaselineOut):
    """需求基线详情：含全部条目。"""

    requirements: list[RequirementItemOut] = Field(default_factory=list)

class RequirementItemUpdate(ApiModel):
    """人工校对单条需求；只允许改文本字段，不允许改编号与基线。"""

    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    priority: str | None = Field(default=None, max_length=8)
    module: str | None = Field(default=None, max_length=40)

class RequirementChangeFieldOut(ApiModel):
    """单个需求字段的变化。"""

    field: str
    label: str
    before: str = ""
    after: str = ""

class RequirementChangeItemOut(ApiModel):
    """一条新增/删除/修改的需求。"""

    id: str
    req_no: str
    title: str
    priority: str = ""
    module: str = ""
    fields: list[RequirementChangeFieldOut] = Field(default_factory=list)

class RequirementDiffOut(ApiModel):
    """两个需求基线版本之间的差异。"""

    base_id: str
    target_id: str
    base_name: str = ""
    target_name: str = ""
    added_count: int = 0
    removed_count: int = 0
    changed_count: int = 0
    added: list[RequirementChangeItemOut] = Field(default_factory=list)
    removed: list[RequirementChangeItemOut] = Field(default_factory=list)
    changed: list[RequirementChangeItemOut] = Field(default_factory=list)
    truncated: bool = False

class RequirementImpactCaseOut(ApiModel):
    """受需求变更影响的用例。"""

    case_set_id: str
    set_name: str = ""
    set_status: str = ""
    case_item_id: str
    case_name: str = ""
    req_no: str = ""
    req_title: str = ""
    change_type: str = "changed"

class RequirementImpactSetOut(ApiModel):
    """受影响的用例集摘要。"""

    case_set_id: str
    name: str = ""
    status: str = ""
    affected_cases: int = 0

class RequirementImpactOut(ApiModel):
    """需求变更影响分析响应。"""

    base_id: str
    target_id: str
    diff: RequirementDiffOut
    affected_set_count: int = 0
    affected_case_count: int = 0
    sets: list[RequirementImpactSetOut] = Field(default_factory=list)
    cases: list[RequirementImpactCaseOut] = Field(default_factory=list)
    truncated: bool = False

class CaseRequirementBindIn(ApiModel):
    """把用例集绑定到一份已确认的需求基线。"""

    baseline_id: str = Field(min_length=1, max_length=64)

class CaseRequirementLinkItem(ApiModel):
    """一条用例到需求的关联输入。"""

    case_item_id: str = Field(min_length=1, max_length=64)
    requirement_ids: list[str] = Field(default_factory=list)

class CaseRequirementLinkIn(ApiModel):
    """人工确认的批量关联；空数组表示解除该用例关联。"""

    baseline_id: str = Field(min_length=1, max_length=64)
    links: list[CaseRequirementLinkItem] = Field(default_factory=list)

class CaseAutoLinkIn(ApiModel):
    """自动关联候选请求；阈值只影响候选，不直接落库。"""

    baseline_id: str = Field(min_length=1, max_length=64)
    threshold: float = Field(default=0.34, ge=0.0, le=1.0)

class CaseAutoLinkOut(ApiModel):
    """自动关联结果：返回候选数量与明细，供前端人工确认。"""

    links: list[dict[str, Any]] = Field(default_factory=list)
    matched_case_count: int = 0

class CoverageRequirementOut(ApiModel):
    """覆盖率明细行。"""

    id: str
    req_no: str
    title: str
    priority: str = ""
    module: str = ""
    covered: bool
    case_count: int = 0
    case_ids: list[str] = Field(default_factory=list)
    case_names: list[str] = Field(default_factory=list)

class CoverageModuleOut(ApiModel):
    """按模块聚合的覆盖率。"""

    module: str
    total: int
    covered: int
    coverage_percent: float

class UsageSeriesOut(ApiModel):
    """按天用量。"""

    day: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class UsageModelOut(ApiModel):
    """按模型/协议档用量。"""

    profile_id: str = ""
    model_name: str = "未记录"
    calls: int = 0
    sessions: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class UsageUserOut(ApiModel):
    """按会话属主用量。"""

    user_id: str = ""
    username: str = "未记录"
    calls: int = 0
    total_tokens: int = 0

class UsageRecentOut(ApiModel):
    """最近一次模型调用用量。"""

    created_at: Any | None = None
    session_id: str = ""
    session_title: str = ""
    model_name: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class UsageSummaryOut(ApiModel):
    """Token 用量中心响应；未配置单价时不做费用估算。

    ``truncated=True`` 表示时间窗内匹配消息超过聚合上限，当前数字只覆盖最近
    ``scanned_messages`` 条；页面必须显式提示，不能把样本当全量。
    """

    days: int
    generated_at: Any | None = None
    calls: int = 0
    sessions: int = 0
    users: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    truncated: bool = False
    scanned_messages: int = 0
    sample_limit: int = 0
    series: list[UsageSeriesOut] = Field(default_factory=list)
    by_model: list[UsageModelOut] = Field(default_factory=list)
    by_user: list[UsageUserOut] = Field(default_factory=list)
    recent: list[UsageRecentOut] = Field(default_factory=list)

class TraceTurnOut(ApiModel):
    """一个用户回合的轨迹摘要。"""

    turn: int
    started_at: float | None = None
    finished_at: float | None = None
    status: str = ""
    event_count: int = 0
    tool_calls: int = 0
    model_attempts: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class TraceEventOut(ApiModel):
    """脱敏后的轨迹事件；不返回正文、工具结果或提示词。"""

    seq: int
    type: str
    ts: float | None = None
    turn: int | None = None
    name: str = ""
    status: str = ""
    duration_ms: int | None = None
    error_code: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

class TraceTurnDetailOut(ApiModel):
    """单个回合的事件列表。"""

    turn: int
    summary: TraceTurnOut
    events: list[TraceEventOut] = Field(default_factory=list)

class NotificationOut(ApiModel):
    """站内通知响应。"""

    id: str
    type: str
    title: str
    body: str = ""
    link: str = ""
    read_at: Any | None = None
    created_at: Any | None = None

class NotificationListOut(ApiModel):
    """通知分页响应。"""

    items: list[NotificationOut] = Field(default_factory=list)
    total: int = 0
    unread: int = 0
    offset: int = 0
    limit: int = 20

class NotificationUnreadOut(ApiModel):
    """未读计数。"""

    unread: int = 0

class CaseAssetOut(ApiModel):
    """跨用例集复用的用例资产。"""

    id: str
    source_case_set_id: str | None = None
    source_set_name: str = ""
    source_case_item_id: str | None = None
    name: str = ""
    module: str = ""
    submodule: str = ""
    feature_point: str = ""
    strategy: str = ""
    priority: str = ""
    precondition: str = ""
    steps: str = ""
    expected: str = ""
    tags: list[str] = Field(default_factory=list)
    source_version: int = 1
    created_at: Any | None = None
    updated_at: Any | None = None

class CaseAssetListOut(ApiModel):
    """资产检索分页响应。"""

    items: list[CaseAssetOut] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 20

class CaseAssetTagsIn(ApiModel):
    """人工标签；最多 10 个，单标签最多 20 字。"""

    tags: list[str] = Field(default_factory=list, max_length=10)

class CaseAssetSimilarIn(ApiModel):
    """文本查重输入；不落库。"""

    name: str = Field(min_length=1, max_length=300)
    expected: str = Field(default="", max_length=2000)
    steps: str = Field(default="", max_length=4000)
    limit: int = Field(default=5, ge=1, le=20)

class CaseAssetSimilarItemOut(ApiModel):
    """相似资产候选。"""

    id: str
    name: str = ""
    score: float = 0.0
    module: str = ""
    priority: str = ""
    source_case_set_id: str | None = None
    source_set_name: str = ""

class CaseAssetSimilarOut(ApiModel):
    """查重结果。"""

    items: list[CaseAssetSimilarItemOut] = Field(default_factory=list)

class CaseAssetStatsOut(ApiModel):
    """资产库概览。"""

    total: int = 0
    source_sets: int = 0
    modules: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[dict[str, Any]] = Field(default_factory=list)

class CaseAssetBackfillOut(ApiModel):
    """历史确认用例集回填结果。"""

    scanned_sets: int = 0
    created_assets: int = 0

class CasegenRunOut(ApiModel):
    """一次用例生成运行的质量摘要。"""

    task_id: str
    case_set_id: str | None = None
    name: str = ""
    status: str = ""
    model_name: str = ""
    profile_id: str = ""
    profile_name: str = ""
    target_count: int = 0
    generated_count: int = 0
    confirmed_count: int = 0
    adoption_rate: float = 0.0
    ai_score: int | None = None
    ai_verdict: str = ""
    review_state: str = ""
    error_code: str = ""
    created_at: Any | None = None
    started_at: Any | None = None
    finished_at: Any | None = None
    duration_ms: int | None = None

class CasegenSeriesOut(ApiModel):
    """按天聚合的生成/确认趋势。"""

    day: str
    runs: int = 0
    generated: int = 0
    confirmed: int = 0
    adoption_rate: float = 0.0

class CasegenModelOut(ApiModel):
    """按模型/协议档聚合的质量。"""

    profile_id: str = ""
    model_name: str = "未记录"
    runs: int = 0
    generated: int = 0
    confirmed: int = 0
    adoption_rate: float = 0.0
    avg_ai_score: float | None = None

class CasegenStatusOut(ApiModel):
    """任务状态分布。"""

    status: str
    count: int = 0

class CasegenModuleOut(ApiModel):
    """模块用例分布。"""

    module: str
    case_count: int = 0

class CasegenMetricsOut(ApiModel):
    """用例生成质量看板响应。

    ``truncated=True`` 表示时间窗内运行数超过聚合上限，指标只覆盖最近
    ``sample_limit`` 次运行；分母不是全量，页面必须显式提示。
    """

    days: int
    generated_at: Any | None = None
    truncated: bool = False
    matched_runs: int = 0
    sample_limit: int = 0
    total_runs: int = 0
    succeeded_runs: int = 0
    failed_runs: int = 0
    cancelled_runs: int = 0
    awaiting_runs: int = 0
    success_rate: float = 0.0
    total_generated: int = 0
    total_confirmed: int = 0
    adoption_rate: float = 0.0
    ai_scored_runs: int = 0
    avg_ai_score: float | None = None
    review_approved: int = 0
    series: list[CasegenSeriesOut] = Field(default_factory=list)
    by_model: list[CasegenModelOut] = Field(default_factory=list)
    by_status: list[CasegenStatusOut] = Field(default_factory=list)
    modules: list[CasegenModuleOut] = Field(default_factory=list)
    recent: list[CasegenRunOut] = Field(default_factory=list)

class CaseCoverageOut(ApiModel):
    """用例集需求覆盖率响应。"""

    baseline_id: str
    baseline_name: str = ""
    baseline_version: int = 1
    total: int
    covered: int
    coverage_percent: float
    p0_total: int
    p0_covered: int
    p0_percent: float
    requirements: list[CoverageRequirementOut] = Field(default_factory=list)
    uncovered: list[CoverageRequirementOut] = Field(default_factory=list)
    modules: list[CoverageModuleOut] = Field(default_factory=list)
    linked_case_count: int = 0
    unlinked_case_count: int = 0

class SearchItemOut(ApiModel):
    """全局搜索单条结果；url 必须是前端可直接跳转的相对地址。"""

    id: str
    type: str
    title: str
    subtitle: str = ""
    status: str = ""
    url: str
    updated_at: str | None = None

class SearchGroupOut(ApiModel):
    """按实体类型分组的结果。"""

    type: str
    label: str
    items: list[SearchItemOut] = Field(default_factory=list)

class SearchResultOut(ApiModel):
    """全局搜索响应；只返回有命中的分组。"""

    query: str
    groups: list[SearchGroupOut] = Field(default_factory=list)
