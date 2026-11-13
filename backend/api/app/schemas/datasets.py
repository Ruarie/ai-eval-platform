"""契约模型：datasets 域。

由 ``app.schemas`` 统一重导出，调用方导入路径不变。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator

from .accounts import (
    ApiModel,
    OrmOut,
)


class DatasetCreate(ApiModel):
    """创建数据集输入；metric 缺省为 contain。"""

    name: str = Field(min_length=1, max_length=100)
    metric: str = Field(default="contain", min_length=1, max_length=32)

class DatasetOut(OrmOut):
    """数据集响应模型（API §3.7；契约 owner_id 即本模型的 created_by）。"""

    id: str
    name: str
    version: int = 1
    folder_id: str | None = None
    row_count: int = 0
    pending_complete_count: int = 0
    metric: str = "contain"
    # 目录导入发布后的容器状态；手工维护的历史数据集仍保持 draft。
    status: str = "draft"
    # 评测创建时必须冻结该不可变版本，而不是直接读取可编辑行。
    active_version_id: str | None = None
    column_schema: list[dict[str, Any]] = Field(default_factory=list)
    created_by: str | None = None
    created_at: Any

class CatalogEntryIn(ApiModel):
    """目录来源草稿：仅记录经审计的官方身份与允许分发域名。"""

    name: str = Field(min_length=1, max_length=160)
    upstream_owner: str = Field(min_length=1, max_length=160)
    official_project_url: str = Field(min_length=8, max_length=2_000)
    allowed_domains: list[str] = Field(min_length=1, max_length=20)
    purpose: str = Field(default="internal_evaluation_only", max_length=128)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)

class CatalogReleaseIn(ApiModel):
    """固定 release manifest；提交审核后只允许通过新 release 修订。"""

    display_version: str = Field(min_length=1, max_length=128)
    source_revision: str = Field(min_length=1, max_length=256)
    manifest: dict[str, Any]
    license: dict[str, Any]
    allowed_splits: list[str] = Field(min_length=1, max_length=8)
    filter_schema: dict[str, Any]
    parser_id: str = Field(min_length=1, max_length=128)
    parser_version: str = Field(min_length=1, max_length=64)
    task_family: Literal["multiple_choice", "generation", "instruction_following"]
    support_status: Literal["supported", "review_required", "planned"] = "review_required"
    risk_labels: list[str] = Field(default_factory=list, max_length=20)

class ReviewNoteIn(ApiModel):
    """来源、release 或导入审核操作的最小审计意见。"""

    note: str | None = Field(default=None, max_length=2_000)

class ResolveBlockIn(ReviewNoteIn):
    """封禁复核只能恢复批准状态或确认持续封禁。"""

    decision: Literal["approved", "blocked"]

class DatasetImportCreate(ApiModel):
    """创建独立导入作业；外部地址与解析规则只来自已批准 release。"""

    catalog_entry_id: str = Field(min_length=1, max_length=64)
    release_id: str = Field(min_length=1, max_length=64)
    splits: list[str] = Field(min_length=1, max_length=8)
    filter_schema_version: int = Field(ge=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    target_name: str | None = Field(default=None, min_length=1, max_length=160)
    target_dataset_id: str | None = Field(default=None, min_length=1, max_length=64)
    folder_id: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_target(self) -> DatasetImportCreate:
        """目标容器必须是已有数据集或一个待创建名称。"""
        if not self.target_name and not self.target_dataset_id:
            raise ValueError("target_name 与 target_dataset_id 至少填写一项")
        return self

class StagingRowsSave(ApiModel):
    """staging 编辑使用读取时的 revision，避免多人按行号误发布。"""

    expected_staging_revision: int = Field(ge=0)
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=20_000)

class PublishImportIn(ReviewNoteIn):
    """发布时必须同时锁定导入批次、revision 与稳定 staging 行 ID。"""

    import_id: str = Field(min_length=1, max_length=64)
    expected_staging_revision: int = Field(ge=0)
    accepted_row_ids: list[str] = Field(min_length=1, max_length=20_000)

class RunConfig(ApiModel):
    """Benchmark 与 RAG 的可复现实行配置。

    字段缺省 ``None`` 表示 REST 请求可省略该键。确认卡预填默认值不在本模型，
    单一事实源见 ``app.agent.defaults.DEFAULT_RUN``（PRD §5.2.2）。
    """

    sample_size: int | None = Field(default=None, ge=1, le=1000)
    concurrency: int | None = Field(default=None, ge=1, le=100)
    timeout_s: int | None = Field(default=None, ge=1, le=600)
    retry: int | None = Field(default=None, ge=0, le=5)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32_768)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    k: int | None = Field(default=None, ge=1, le=20)
    use_judge: bool = False
    # LLM 裁判协议档（usages 需含 "judge"）：use_judge=True 时必填
    judge_profile_id: str | None = Field(default=None, max_length=64)

class StressConfig(ApiModel):
    """仅质量任务派生压测时可用的参数段。"""

    env: Literal["dev", "test", "staging", "prod"]
    qps: int = Field(ge=1, le=500)
    duration_s: int = Field(ge=1, le=1800)
    sla_p99_ms: int | None = Field(default=None, ge=1)

class CaseSource(ApiModel):
    """用例生成的文件或文本二选一输入。"""

    file_id: str | None = None
    text: str | None = Field(default=None, max_length=1_000_000)

    @model_validator(mode="after")
    def validate_single_source(self) -> CaseSource:
        """确保用例生成输入在文件和文本之间二选一。"""
        has_file = bool(self.file_id)
        has_text = bool(self.text and self.text.strip())
        if has_file == has_text:
            raise ValueError("case_source 必须且只能提供 file_id 或 text")
        return self

class TaskCreate(ApiModel):
    """确认卡与 REST 共用的 TaskSpec，兼容前端暂存的 config 包装。"""

    kind: Literal["benchmark", "rag", "testcase", "stress"]
    session_id: str | None = None
    parent_task_id: str | None = None
    profile_ids: list[str] = Field(default_factory=list)
    dataset_id: str | None = None
    kb_id: str | None = None
    gold_qa_id: str | None = None
    rag_mode: list[Literal["naive", "local", "global", "hybrid"]] = Field(default_factory=list)
    run: RunConfig | None = None
    with_stress: bool = False
    stress: StressConfig | None = None
    case_source: CaseSource | None = None
    max_count: int | None = Field(default=None, strict=True, ge=1, le=80)
    strategy_weights: dict[str, int] | None = None

    @field_validator("strategy_weights", mode="before")
    @classmethod
    def validate_case_strategy_weights(cls, value: Any) -> Any:
        """用例任务与页面候选生成共用六策略整数百分比校验。"""
        from shared.casegen import validate_strategy_weights

        validate_strategy_weights(value)
        return value

    @model_validator(mode="before")
    @classmethod
    def unpack_frontend_config(cls, value: Any) -> Any:
        """兼容已完成前端发送的 {kind, config, session_id} 包装结构。"""
        if not isinstance(value, dict):
            return value
        nested = value.get("config")
        if not isinstance(nested, dict):
            return value
        merged = dict(nested)
        for key, item in value.items():
            if key != "config" and item is not None:
                merged[key] = item
        return merged

    @model_validator(mode="after")
    def validate_by_kind(self) -> TaskCreate:
        """按 PRD 确认卡规则校验不同 kind 的必填段。"""
        if self.kind == "benchmark":
            if not 1 <= len(self.profile_ids) <= 5:
                raise ValueError("benchmark 需要 1–5 个 profile_ids")
            if not self.dataset_id:
                raise ValueError("benchmark 需要 dataset_id")
            if not self.run:
                raise ValueError("benchmark 需要 run")
            if self.run.use_judge and not self.run.judge_profile_id:
                raise ValueError("启用 LLM 裁判时需要 judge_profile_id")
        elif self.kind == "rag":
            if not self.kb_id or not self.gold_qa_id:
                raise ValueError("rag 需要 kb_id 和 gold_qa_id")
            if not self.run:
                raise ValueError("rag 需要 run")
        elif self.kind == "testcase":
            if not self.case_source:
                raise ValueError("testcase 需要 case_source")
        elif not self.parent_task_id:
            raise ValueError("手动创建 stress 任务需要 parent_task_id")

        if self.kind != "testcase" and (self.max_count is not None or self.strategy_weights is not None):
            raise ValueError("用例生成参数仅支持 testcase 任务")

        if self.with_stress:
            if self.kind not in {"benchmark", "rag"}:
                raise ValueError("with_stress 仅支持 benchmark 或 rag")
            if not self.stress:
                raise ValueError("with_stress=true 时需要 stress")
        return self

    def snapshot(self) -> dict[str, Any]:
        """生成可复现的任务配置快照，不重复保存会话关联字段。"""
        return self.model_dump(exclude={"session_id"}, exclude_none=True, mode="json")

class TaskEventOut(OrmOut):
    """任务详情时间线中的单条事件。"""

    id: int
    task_id: str
    event: str
    level: str
    message: str | None = None
    payload: dict[str, Any]
    ts: Any

class TaskOut(OrmOut):
    """任务列表与创建接口的统一响应（API §3.10：item 含 dataset_id/kb_id/creator_id 顶层引用）。"""

    id: str
    session_id: str | None
    parent_task_id: str | None
    kind: str
    status: str
    config: dict[str, Any]
    progress: dict[str, Any]
    result: dict[str, Any]
    report_id: str | None
    # 顶层引用字段：Task ORM 无同名列，由路由层 _task_out 从 config/result 提升填充
    dataset_id: str | None = None
    kb_id: str | None = None
    case_set_id: str | None = None
    # 契约字段名 creator_id 与既有前端字段 creator 并存输出，保证新旧消费端兼容
    creator: str = Field(validation_alias=AliasChoices("created_by", "creator"))
    creator_id: str | None = Field(default=None, validation_alias=AliasChoices("created_by", "creator_id"))
    created_at: Any
    updated_at: Any

class TaskDetailOut(TaskOut):
    """任务详情额外返回的追加式事件时间线。"""

    events: list[TaskEventOut] = Field(default_factory=list)

class PageOut(OrmOut):
    """统一分页外层，具体路由传入 items 内容。"""

    items: list[Any]
    total: int

class DispatchWorkerCreate(ApiModel):
    """注册新 Worker 执行节点的输入。"""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    caps: list[str] = Field(default_factory=list)
    weight: int = Field(default=100, ge=1, le=1000)

class DispatchWorkerUpdate(ApiModel):
    """修改节点状态、权重或能力标签；状态取值对齐调度契约。"""

    state: Literal["idle", "busy", "offline", "draining", "restarting"] | None = None
    weight: int | None = Field(default=None, ge=1, le=1000)
    caps: list[str] | None = None

class DispatchWorkerOut(OrmOut):
    """调度面可读的 Worker 心跳与能力快照。"""

    id: str
    name: str
    caps: list[str]
    state: str
    weight: int
    load_percent: float | None = None
    current_task: str | None = None
    last_heartbeat_at: Any | None = None

class DispatchConfigUpdate(ApiModel):
    """更新分发策略、全局并发容量或是否暂停领取新任务。"""

    strategy: Literal["负载均衡", "优先级抢占", "亲和性"] | None = None
    max_running_tasks: int | None = Field(default=None, ge=1, le=64)
    # True 时 Worker 不再领取排队任务和数据集导入；已经在执行的任务继续跑完。
    paused: bool | None = None

class DispatchOverviewOut(ApiModel):
    """调度中心大盘指标与内核雷达状态。"""

    online_workers: int
    total_workers: int
    queue_depth: int
    avg_dispatch_cost_ms: float
    assigned_today: int
    strategy: str
    max_running_tasks: int
    heartbeat_interval_ms: int
    paused: bool = False

class DispatchEventOut(OrmOut):
    """调度分配日志流中的单条事件。"""

    id: int
    task_id: str | None = None
    worker_id: str | None = None
    event: str
    message: str
    ts: Any

class DispatchEventPage(ApiModel):
    """增量事件流响应，next_after_id 供下一轮轮询携带。"""

    items: list[DispatchEventOut]
    next_after_id: int
