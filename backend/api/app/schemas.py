"""REST 和 WebSocket 共用的 Pydantic 契约模型。"""

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class ApiModel(BaseModel):
    """所有输入模型默认拒绝契约外字段，避免浏览器临时字段落库。"""

    model_config = ConfigDict(extra="forbid")


class OrmOut(ApiModel):
    """支持由 SQLAlchemy 模型安全构造的只读响应基类。"""

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(ApiModel):
    """登录请求的用户名和密码。"""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class ChangePasswordRequest(ApiModel):
    """当前成员的密码变更请求。"""

    old_password: str | None = Field(default=None, max_length=512)
    new_password: str = Field(min_length=8, max_length=512)


class UserCreate(ApiModel):
    """创建成员账号的输入字段，所有成员自动使用 member 角色。"""

    username: str = Field(min_length=1, max_length=128)
    display_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=8, max_length=512)
    # V1.83 起机制废除：字段仅保留请求兼容，服务端恒写 False（不再强制首次改密）。
    must_change_password: bool = False


class UserUpdate(ApiModel):
    """可修改的成员资料，不暴露角色变更能力。"""

    display_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=320)


class UserStatusUpdate(ApiModel):
    """成员启用或停用请求。"""

    disabled: bool


class ResetPasswordRequest(ApiModel):
    """成员重置密码请求。

    ``current_password`` 在「重置他人密码」时必填：本项目为全员同权模型，
    没有角色可作授权依据，改以「重新验证请求者本人密码」作为接管他人账号前
    的二次确认，避免仅凭一个未过期会话即可改密并把对方踢下线。
    """

    password: str = Field(min_length=8, max_length=512)
    current_password: str | None = Field(default=None, max_length=512)


class UserOut(OrmOut):
    """不包含密码哈希和认证版本的成员响应。"""

    id: str
    username: str
    display_name: str | None = None
    email: str | None = None
    role: Literal["member"] = "member"
    disabled: bool
    must_change_password: bool
    last_login_at: Any | None = None
    last_login_ip: str | None = None
    created_at: Any


class ProfileCreate(ApiModel):
    """创建协议档时的可写字段；两类模型的 API Key 仅在本模型出现。"""

    name: str = Field(min_length=1, max_length=128)
    protocol: Literal["openai_chat", "openai_responses", "anthropic_messages"]
    base_url: str = Field(min_length=1, max_length=1024)
    full_url: bool = False  # 原样使用完整请求地址。
    model: str = Field(min_length=1, max_length=256)
    api_key: str | None = Field(default=None, max_length=4096)
    embedding_base_url: str | None = Field(default=None, max_length=1024)
    embedding_model: str | None = Field(default=None, max_length=256)
    embedding_api_key: str | None = Field(default=None, max_length=4096)
    reranker_base_url: str | None = Field(default=None, max_length=1024)
    reranker_model: str | None = Field(default=None, max_length=256)
    reranker_api_key: str | None = Field(default=None, max_length=4096)
    anthropic_version: str | None = Field(default=None, max_length=64)
    usages: list[Literal["target", "agent", "judge"]] = Field(default_factory=list)
    context_window: int = Field(default=200000, ge=1000, le=10000000, description="上下文窗口大小 (Tokens)")
    max_output_tokens: int = Field(
        default=8192, ge=256, le=131072, description="Agent 单回合模型输出上限 (max_tokens)"
    )
    tool_call_mode: Literal["native", "legacy"] = Field(
        default="native", description="Agent 工具调用模式：原生 ToolCall（默认）或受控 JSON 回退"
    )
    reasoning_template_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def clean_empty_strings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for k in (
                "embedding_base_url",
                "embedding_model",
                "embedding_api_key",
                "reranker_base_url",
                "reranker_model",
                "reranker_api_key",
                "api_key",
                "anthropic_version",
            ):
                if k in data and isinstance(data[k], str) and not data[k].strip():
                    data[k] = None
        return data


class ProfileUpdate(ApiModel):
    """更新协议档；空的两类 API Key 均表示不修改既有密文。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    protocol: Literal["openai_chat", "openai_responses", "anthropic_messages"] | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=1024)
    full_url: bool | None = None  # 原样使用完整请求地址。
    model: str | None = Field(default=None, min_length=1, max_length=256)
    api_key: str | None = Field(default=None, max_length=4096)
    embedding_base_url: str | None = Field(default=None, max_length=1024)
    embedding_model: str | None = Field(default=None, max_length=256)
    embedding_api_key: str | None = Field(default=None, max_length=4096)
    reranker_base_url: str | None = Field(default=None, max_length=1024)
    reranker_model: str | None = Field(default=None, max_length=256)
    reranker_api_key: str | None = Field(default=None, max_length=4096)
    anthropic_version: str | None = Field(default=None, max_length=64)
    usages: list[Literal["target", "agent", "judge"]] | None = None
    context_window: int | None = Field(default=None, ge=1000, le=10000000, description="上下文窗口大小 (Tokens)")
    max_output_tokens: int | None = Field(
        default=None, ge=256, le=131072, description="Agent 单回合模型输出上限 (max_tokens)"
    )
    tool_call_mode: Literal["native", "legacy"] | None = None
    reasoning_template_id: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="before")
    @classmethod
    def clean_empty_strings(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for k in (
                "embedding_base_url",
                "embedding_model",
                "embedding_api_key",
                "reranker_base_url",
                "reranker_model",
                "reranker_api_key",
                "api_key",
                "anthropic_version",
            ):
                if k in data and isinstance(data[k], str) and not data[k].strip():
                    data[k] = None
        return data


class ProfileOut(OrmOut):
    """协议档公开字段，任何响应均不含 API Key。"""

    id: str
    name: str
    protocol: str
    base_url: str
    full_url: bool = False  # 原样使用完整请求地址。
    model: str
    usages: list[str]
    anthropic_version: str | None = None
    has_api_key: bool = False
    embedding_base_url: str | None = None
    embedding_model: str | None = None
    has_embedding_api_key: bool = False
    reranker_base_url: str | None = None
    reranker_model: str | None = None
    has_reranker_api_key: bool = False
    context_window: int = 200000
    max_output_tokens: int = 8192
    provider: str = "openai"
    reasoning_effort: str = "off"
    allowed_efforts: list[str] = Field(default_factory=list)
    reasoning_note: str = ""
    # 控件语义由模板声明；legacy 为 null，避免把开关展示成多档强度。
    reasoning_mode: Literal["none", "switch", "effort", "budget", "fixed"] | None = None
    reasoning_template_id: str | None = None
    reasoning_template_name: str | None = None
    reasoning_probe_status: Literal["legacy", "unverified", "passed", "partial", "failed"] = "legacy"
    # 工具往返结果与思考档位独立；历史配置不默认宣称工具可用。
    tool_probe_status: Literal["unverified", "passed", "failed", "skipped"] = "unverified"
    tool_call_mode: Literal["native", "legacy"] = "native"
    created_at: Any
    updated_at: Any


class ProfileProbeCreate(ProfileCreate):
    """使用受控模板真实验证并创建协议档的完整请求。"""

    reasoning_template_id: str = Field(min_length=1, max_length=128)


class ProfileProbeUpdate(ProfileProbeCreate):
    """使用拟更新的完整连接配置验证后原子更新协议档。"""


class ProfileProbeOut(ApiModel):
    """模型模板探测结果；任何字段都不得含上游响应正文或凭据。"""

    ok: bool
    profile: ProfileOut | None = None
    probe: dict[str, Any]
    message: str


class FetchModelsIn(ApiModel):
    """远程获取模型列表请求入参。"""

    protocol: Literal["openai_chat", "openai_responses", "anthropic_messages"] = "openai_chat"
    base_url: str | None = Field(default=None, max_length=1024)
    full_url: bool | None = None  # 原样使用完整请求地址。
    api_key: str | None = Field(default=None, max_length=4096)
    profile_id: str | None = None
    anthropic_version: str | None = None



class MediaMcpConfigUpdate(ApiModel):
    """协议档页面写入的媒体 MCP 配置；Key 只接收不回显。"""

    enabled: bool | None = None
    compatible_base_url: str | None = Field(default=None, min_length=1, max_length=1024)
    api_key: str | None = Field(default=None, max_length=4096)
    image_model: str | None = Field(default=None, min_length=1, max_length=256)
    video_model: str | None = Field(default=None, min_length=1, max_length=256)
    request_timeout_s: float | None = Field(default=None, ge=10, le=600)

    @model_validator(mode="before")
    @classmethod
    def clean_empty_api_key(cls, data: Any) -> Any:
        """空密钥是保留现状，避免编辑模型时误删已保存的凭据。"""
        if isinstance(data, dict) and isinstance(data.get("api_key"), str) and not data["api_key"].strip():
            data["api_key"] = None
        return data


class MediaMcpConfigOut(ApiModel):
    """媒体 MCP 的脱敏配置响应。"""

    enabled: bool
    compatible_base_url: str
    image_model: str
    video_model: str
    request_timeout_s: float
    has_api_key: bool


class SessionCreate(ApiModel):
    """创建空 Agent 会话的输入。

    F3/G5：``workspace_id``/``scope_path`` 可选——绑定用户工作区（创建时
    固化、运行期不可变，设计《工作区与沙箱设计方案》§5）；绑定仅限 private
    会话（BLK-4）。未绑定时使用平台临时工作区。
    """

    title: str = Field(default="新会话", min_length=1, max_length=200)
    # 新建会话统一走 AgentLoop；历史 legacy 行只通过 SessionOut 保持可回放。
    engine_version: Literal["agent_loop_v2"] = "agent_loop_v2"
    visibility: Literal["private", "team"] = "private"
    workspace_id: str | None = Field(default=None, max_length=64)
    scope_path: str | None = Field(default=None, max_length=1024)
    # 三档权限等级；None = 继承全局 settings.permission_tier_default。
    permission_tier: str | None = Field(default=None, max_length=16)


class SessionSharingUpdate(ApiModel):
    """会话创建者设置团队共享范围的输入。"""

    visibility: Literal["private", "team"]


class SessionPermissionTierUpdate(ApiModel):
    """会话级权限档位覆盖输入；None = 继承全局默认。"""

    permission_tier: Literal["tier1", "tier2", "tier3"] | None = None


class SessionTitleUpdate(ApiModel):
    """修改会话标题的输入。"""

    title: str = Field(..., min_length=1, max_length=200)


class SessionOut(OrmOut):
    """会话列表项及当前成员的共享管理权限。

    F3/G5：``workspace_id``/``scope_path``/``workspace_name`` 为绑定工作区
    信息（未绑定为 None）；``workspace_name`` 由路由侧补充（行内无此列）。
    """

    id: str
    engine_version: Literal["legacy", "agent_loop_v2"] = "legacy"
    title: str
    owner_id: str = Field(validation_alias=AliasChoices("user_id", "owner_id"))
    visibility: Literal["private", "team"] = "private"
    workspace_id: str | None = None
    scope_path: str | None = None
    workspace_name: str | None = None
    permission_tier: str | None = None
    created_at: Any
    updated_at: Any
    can_manage: bool = False
    can_delete: bool = False
    active_task: dict[str, Any] | None = None


class MessageOut(OrmOut):
    """REST 回放使用的消息字段。"""

    id: str
    role: str
    content: str
    attachments: list[str | dict[str, Any]]
    author_id: str | None = None
    client_message_id: str | None = None
    latency_ms: int | None = None
    model_name: str | None = None
    profile_id: str | None = None
    profile_name: str | None = None
    provider: str | None = None
    created_at: Any


class FileOut(OrmOut):
    """文件元数据响应，不包含内部存储路径。"""

    id: str
    filename: str
    content_type: str | None = None
    size: int = Field(validation_alias=AliasChoices("size_bytes", "size"))
    sha256: str
    created_at: Any


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
    def validate_target(self) -> "DatasetImportCreate":
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
    def validate_single_source(self) -> "CaseSource":
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
    def validate_by_kind(self) -> "TaskCreate":
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
    # 顶层引用字段：Task ORM 无同名列，由路由层 _task_out 从 config 快照提升填充
    dataset_id: str | None = None
    kb_id: str | None = None
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


# ─── 调度内核与 Worker 节点管理（API V1.3 §3.13） ───


class DispatchWorkerCreate(ApiModel):
    """注册新 Worker 执行节点的输入。"""

    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    caps: list[str] = Field(default_factory=list)
    weight: int = Field(default=100, ge=1, le=1000)


class DispatchWorkerUpdate(ApiModel):
    """修改节点状态、权重或能力标签；状态取值对齐调度契约。"""

    state: Literal["idle", "busy", "offline", "draining"] | None = None
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
    """更新分发策略与全局并发容量。"""

    strategy: Literal["负载均衡", "优先级抢占", "亲和性"] | None = None
    max_running_tasks: int | None = Field(default=None, ge=1, le=64)


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


# ─── MCP 工具中心（API V1.3 §3.6.1，V1.0 只读） ───


class McpToolOut(ApiModel):
    """MCP 工具注册清单项，区分已挂载内置工具与独立注册项。"""

    name: str
    desc: str
    permission: Literal["read", "write"]
    enabled: bool
    source: Literal["builtin", "standalone"] = "builtin"


# ─── 数据集工作台扩展（API V1.3 §3.7） ───


class ColumnSchemaItem(ApiModel):
    """数据集自定义扩展列定义，行内扩展值按 key 落入 DatasetRow.extras。"""

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=32)
    required: bool = False
    sort_order: int = 0


class DatasetUpdate(ApiModel):
    """数据集可修改字段；column_schema 为整体替换而非合并。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    metric: str | None = Field(default=None, min_length=1, max_length=32)
    folder_id: str | None = None
    column_schema: list[ColumnSchemaItem] | None = None

    @model_validator(mode="after")
    def validate_unique_column_keys(self) -> "DatasetUpdate":
        """扩展列 key 必须全局唯一，否则行内扩展值无法对应列定义。"""
        if self.column_schema is not None:
            keys = [col.key for col in self.column_schema]
            if len(keys) != len(set(keys)):
                raise ValueError("column_schema 中存在重复 key")
        return self


class FolderIn(ApiModel):
    """目录创建/更新共用输入；POST 时 name 由路由校验必填，PUT 仅修改提供的字段。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: str | None = None
    sort_order: int | None = None


class FolderOut(OrmOut):
    """数据集目录树节点响应。"""

    id: str
    name: str
    parent_id: str | None = None
    sort_order: int = 0
    created_at: Any


class DatasetRowIn(ApiModel):
    """单行保存输入：q/r/c 短名映射 question/reference/context，其余键进入 extras。"""

    # 扩展列 key 由 Dataset.column_schema 动态定义，此处必须放行契约外字段
    model_config = ConfigDict(extra="allow")

    row_no: int = Field(ge=1)
    q: str | None = Field(default=None, max_length=100_000)
    r: str | None = Field(default=None, max_length=100_000)
    c: str | None = Field(default=None, max_length=100_000)
    source_case_id: str | None = Field(default=None, max_length=64)


class RowsPayload(ApiModel):
    """批量保存请求；row_no 缺失由字段校验拦截为 VALIDATION，此处拦截重复。"""

    rows: list[DatasetRowIn] = Field(min_length=1, max_length=20_000)

    @model_validator(mode="after")
    def validate_unique_row_no(self) -> "RowsPayload":
        """单次批量保存内 row_no 不允许重复，避免 upsert 目标行歧义。"""
        row_nos = [row.row_no for row in self.rows]
        if len(row_nos) != len(set(row_nos)):
            raise ValueError("rows 中存在重复 row_no")
        return self


class AiGenerateIn(ApiModel):
    """AI 候选生成请求；模型调用层重建设计期间仅保留接口契约。"""

    dataset_id: str = Field(min_length=1, max_length=64)
    mode: Literal["scene", "seed", "doc", "fill_missing"]
    instruction: str | None = Field(default=None, max_length=20_000)
    source_text: str | None = Field(default=None, max_length=1_000_000)
    seed: str | None = Field(default=None, max_length=100_000)
    rows: list[dict[str, Any]] | None = None
    max_count: int = Field(default=10, ge=1, le=50)
    model: str | None = Field(default=None, max_length=256)
    temperature: float | None = Field(default=None, ge=0, le=2)

    @model_validator(mode="after")
    def validate_by_mode(self) -> "AiGenerateIn":
        """fill_missing 必须携带待补全行；其余模式至少要有一段生成依据。"""
        if self.mode == "fill_missing":
            if not self.rows:
                raise ValueError("fill_missing 模式必须提供待补全 rows")
        elif not any(
            [
                self.instruction and self.instruction.strip(),
                self.source_text and self.source_text.strip(),
                self.seed and self.seed.strip(),
            ]
        ):
            raise ValueError("请至少提供 instruction、source_text 或 seed 之一")
        return self


# ─── 用例工作台（API V1.3 §3.8） ───


class CaseSetCreate(ApiModel):
    """创建空用例集输入；column_schema 规则同数据集自定义列。"""

    name: str = Field(min_length=1, max_length=100)
    folder_id: str | None = None
    column_schema: list[ColumnSchemaItem] | None = None

    @model_validator(mode="after")
    def validate_unique_column_keys(self) -> "CaseSetCreate":
        """扩展列 key 必须全局唯一，否则用例行内扩展值无法对应列定义。"""
        if self.column_schema is not None:
            keys = [col.key for col in self.column_schema]
            if len(keys) != len(set(keys)):
                raise ValueError("column_schema 中存在重复 key")
        return self


class CaseSetUpdate(ApiModel):
    """用例集可修改字段；column_schema 为整体替换，confirmed 集由路由层拒绝。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    folder_id: str | None = None
    column_schema: list[ColumnSchemaItem] | None = None
    expected_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_unique_column_keys(self) -> "CaseSetUpdate":
        """扩展列 key 必须全局唯一，否则用例行内扩展值无法对应列定义。"""
        if self.column_schema is not None:
            keys = [col.key for col in self.column_schema]
            if len(keys) != len(set(keys)):
                raise ValueError("column_schema 中存在重复 key")
        return self


class CaseSetOut(OrmOut):
    """用例集列表项响应（API §3.8）；expires_at 由任务域写入，此处原样返回。"""

    id: str
    task_id: str | None = None
    name: str
    status: str = "generated"
    generated_count: int = 0
    confirmed_count: int = 0
    revision: int = 0
    folder_id: str | None = None
    requirement_baseline_id: str | None = None
    review_state: str = "draft"
    review_assignee_id: str | None = None
    column_schema: list[dict[str, Any]] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    expires_at: Any | None = None
    created_at: Any
    updated_at: Any | None = None


class CaseSetDetailOut(CaseSetOut):
    """用例集详情额外返回的用例行数组（固定字段 + 扩展列平铺）。"""

    cases: list[dict[str, Any]] = Field(default_factory=list)


class CaseIn(ApiModel):
    """单条用例保存输入：固定字段之外的扩展列 key 进入 CaseItem.extras。"""

    # 扩展列 key 由 CaseSet.column_schema 动态定义，此处必须放行契约外字段
    model_config = ConfigDict(extra="allow")

    id: str | None = Field(default=None, max_length=64)
    strategy: str = Field(min_length=1, max_length=32)
    priority: str = Field(min_length=1, max_length=16)
    module: str = Field(default="", max_length=100)
    submodule: str | None = Field(default=None, max_length=100)
    feature_point: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    precondition: str | None = Field(default=None, max_length=100_000)
    steps: str | None = Field(default=None, max_length=100_000)
    expected: str | None = Field(default=None, max_length=100_000)
    test_type: str | None = Field(default=None, max_length=64)


class CoverageCaseIn(ApiModel):
    """覆盖自检的用例摘要：只取评审需要的四个字段，避免被无关必填项拒绝。"""

    name: str = Field(min_length=1, max_length=200)
    strategy: str | None = Field(default=None, max_length=32)
    module: str | None = Field(default=None, max_length=100)
    feature_point: str | None = Field(default=None, max_length=100)


class CaseAiReviewIn(ApiModel):
    """用例评审请求：来源文档可选。

    不传时用用例集关联任务快照里的 case_source；都没有则退化为
    "只看用例自身质量"（可执行性/重复/分布），覆盖度维度会标注无需求可对照。
    """

    source_doc_id: str | None = Field(default=None, max_length=64)
    source_text: str | None = Field(default=None, max_length=1_000_000)


class CaseCoverageIn(ApiModel):
    """需求覆盖自检请求：来源文档 + 已生成用例摘要，返回未被覆盖的需求点。"""

    source_doc_id: str | None = Field(default=None, max_length=64)
    source_text: str | None = Field(default=None, max_length=1_000_000)
    cases: list[CoverageCaseIn] = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_source(self) -> "CaseCoverageIn":
        """与 ai-generate 一致：来源二选一必填。"""
        has_doc = bool(self.source_doc_id)
        has_text = bool(self.source_text and self.source_text.strip())
        if not (has_doc or has_text):
            raise ValueError("source_text 与 source_doc_id 至少填一项")
        return self


class CaseSetFromCandidatesIn(ApiModel):
    """把已审核的 AI 候选一次性保存为待确认草稿。"""

    name: str = Field(min_length=1, max_length=100)
    folder_id: str | None = None
    cases: list[CaseIn] = Field(min_length=1, max_length=80)


class CasesPayload(ApiModel):
    """按修订号原子保存用例行与扩展列；单次请求内用例 id 不允许重复。"""

    cases: list[CaseIn] = Field(max_length=20_000)
    expected_revision: int = Field(ge=0)
    column_schema: list[ColumnSchemaItem] | None = None

    @model_validator(mode="after")
    def validate_unique_case_id(self) -> "CasesPayload":
        """单次批量保存内显式 id 不允许重复；缺省 id 由服务端生成，不参与查重。"""
        ids = [case.id for case in self.cases if case.id]
        if len(ids) != len(set(ids)):
            raise ValueError("cases 中存在重复 id")
        if self.column_schema is not None:
            keys = [col.key for col in self.column_schema]
            if len(keys) != len(set(keys)):
                raise ValueError("column_schema 中存在重复 key")
        return self


class CaseConfirmIn(ApiModel):
    """确认/废弃用例集请求；ok=false 时置 cancelled 并联动关联任务。"""

    ok: bool
    expected_revision: int = Field(ge=0)
    # edits / mapping_target / target_id 仅为历史兼容字段，旧评测数据集映射已停用；
    # 本接口仅消费 ok 与 expected_revision，其余字段只写审计明细。
    edits: dict[str, Any] | None = None
    mapping_target: Literal["dataset", "gold_qa"] | None = None
    target_id: str | None = Field(default=None, max_length=64)


class CaseCancelIn(ApiModel):
    """废弃用例集请求，可附废弃原因。"""

    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=2000)


class CaseMapIn(ApiModel):
    """已停用映射端点的历史兼容请求契约。"""

    target: Literal["dataset", "gold_qa"]
    target_id: str = Field(min_length=1, max_length=64)
    case_ids: list[str] = Field(min_length=1, max_length=20_000)


class CaseAiGenerateIn(ApiModel):
    """AI 候选用例生成请求；仅返回未落库候选，不创建用例集。"""

    source_doc_id: str | None = Field(default=None, max_length=64)
    source_text: str | None = Field(default=None, max_length=1_000_000)
    # 6 大策略配比（百分比），键取值 positive/negative/boundary/equivalence/state/scenario
    strategy_weights: dict[str, int] | None = None
    # 规模只由 max_count 决定（简单/中等/复杂 = 20/45/80 由调用方直接传条数），
    # 不再接受不生效的 complexity 字段。
    max_count: int = Field(default=45, strict=True, ge=1, le=80)

    @field_validator("strategy_weights", mode="before")
    @classmethod
    def validate_weights(cls, value: Any) -> Any:
        """先检查原始整数百分比，避免布尔值或小数被类型转换后放行。"""
        from shared.casegen import validate_strategy_weights

        validate_strategy_weights(value)
        return value

    @model_validator(mode="after")
    def validate_source(self) -> "CaseAiGenerateIn":
        """source_doc_id 与 source_text 至少填一项，作为用例生成依据。"""
        has_doc = bool(self.source_doc_id)
        has_text = bool(self.source_text and self.source_text.strip())
        if not (has_doc or has_text):
            raise ValueError("source_doc_id 与 source_text 至少填一项")
        return self


class CaseAiCompareIn(CaseAiGenerateIn):
    """同一需求交给两个 Agent 协议档生成，只对比候选，不创建用例集。"""

    profile_ids: list[str] = Field(min_length=2, max_length=2)

    @field_validator("profile_ids")
    @classmethod
    def validate_profile_ids(cls, value: list[str]) -> list[str]:
        """必须是两个不同的协议档，避免用同一模型对比出虚假差异。"""
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 64 for item in cleaned) or len(set(cleaned)) != 2:
            raise ValueError("需要两个不同的协议档")
        return cleaned


class CaseAiFillIn(ApiModel):
    """行级 AI 补全请求；case_ids 必填且必须全部属于该用例集。"""

    case_ids: list[str] = Field(min_length=1, max_length=20_000)
    instruction: str | None = Field(default=None, max_length=20_000)
    # 缺省时补全所有缺失字段；提供时仅补全指定字段（含扩展列 key）
    fields: list[str] | None = Field(default=None, max_length=64)


class KbCreate(ApiModel):
    """知识库创建输入：kind 区分 LightRAG 原生库与外部 RAG 服务。"""

    name: str = Field(min_length=1, max_length=100)
    kind: Literal["lightrag", "external_chat"] = "lightrag"
    profile_id: str | None = Field(default=None, max_length=64)


class KbUpdate(ApiModel):
    """知识库更新输入：仅修改提供的字段，拒绝契约外字段落库。"""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    kind: Literal["lightrag", "external_chat"] | None = None
    profile_id: str | None = Field(default=None, max_length=64)
    is_core: bool | None = None


class KbOut(ApiModel):
    """知识库响应：doc_count / owner / capabilities 为派生字段，手动构造。"""

    id: str
    name: str
    kind: str
    doc_count: int | None = None
    is_core: bool = False
    owner: str = ""
    profile_id: str | None = None
    capabilities: dict = Field(default_factory=lambda: {"projection": False, "rerank_compare": False})
    created_at: Any | None = None


class KbDocOut(ApiModel):
    """知识库文档响应：size 为格式化展示串（如 "12.4 KB"）。"""

    doc_id: str
    filename: str
    status: str
    size: str = ""
    created_at: Any | None = None


class KbChunkOut(ApiModel):
    """切块预览响应。"""

    chunk_id: str
    doc_id: str
    text: str
    tokens: int


class KbQueryIn(ApiModel):
    """检索 Playground 请求。"""

    query: str = Field(min_length=1, max_length=20_000)
    mode: Literal["naive", "local", "global", "hybrid"] = "hybrid"
    k: int = Field(default=5, ge=1, le=20)


class KbQueryItemOut(ApiModel):
    """检索结果单条：hit 标记该切块文档是否命中黄金 QA 期望文档。"""

    chunk_id: str
    doc_name: str = ""
    similarity: float | None = None
    text: str = ""
    hit: bool = False


class KbQueryOut(ApiModel):
    """检索 Playground 响应：指标按「question 匹配的黄金 QA 行」计算。"""

    query: str
    mode: str
    items: list[KbQueryItemOut] = Field(default_factory=list)
    reranked_ids: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=lambda: {"hit_rate": 0.0, "mrr": 0.0, "recall": 0.0, "contain": 0.0})


class KbGraphNodeOut(ApiModel):
    """图谱节点：``degree`` 为当前知识库内的关联数，``doc_ids`` 为来源文档。"""

    id: str
    entity_type: str = ""
    description: str = ""
    degree: int = 0
    doc_ids: list[str] = Field(default_factory=list)


class KbGraphEdgeOut(ApiModel):
    """图谱关系：``weight`` 取引擎给出的强度，缺失时按 1.0。"""

    source: str
    target: str
    description: str = ""
    weight: float = 1.0


class KbGraphOut(ApiModel):
    """知识库图谱响应（只读）：truncated 表示节点数超过 limit 被截断。"""

    kb_id: str
    nodes: list[KbGraphNodeOut] = Field(default_factory=list)
    edges: list[KbGraphEdgeOut] = Field(default_factory=list)
    truncated: bool = False
    engine: str = "lightrag"


# ─── 用例评审工作流与版本 ─────────────────────────────────────────────


class CaseReviewRequestIn(ApiModel):
    """发起评审：负责人缺省为当前成员，截止时间可选。"""

    assignee_id: str | None = Field(default=None, max_length=64)
    due_at: Any | None = None
    note: str = Field(default="", max_length=2000)


class CaseReviewDecisionIn(ApiModel):
    """评审结论；要求修改必须给出原因。"""

    decision: Literal["approved", "changes_requested"]
    note: str = Field(default="", max_length=2000)


class CaseReviewCommentIn(ApiModel):
    """新增评审评论；case_item_id 为空表示整体评论。"""

    body: str = Field(min_length=1, max_length=2000)
    case_item_id: str | None = Field(default=None, max_length=64)


class CaseReviewCommentOut(ApiModel):
    """评论响应。"""

    id: str
    case_item_id: str | None = None
    author_id: str | None = None
    author_name: str = ""
    body: str
    created_at: Any | None = None


class CaseReviewRequestOut(ApiModel):
    """评审请求响应。"""

    id: str
    status: str
    note: str = ""
    decision_note: str = ""
    assignee_id: str | None = None
    assignee_name: str = ""
    due_at: Any | None = None
    created_by: str | None = None
    created_by_name: str = ""
    created_at: Any | None = None
    decided_at: Any | None = None


class CaseReviewRunOut(ApiModel):
    """AI 评审历史行。"""

    id: str
    score: int = 0
    verdict: str = ""
    summary: str = ""
    dimensions: dict[str, Any] = Field(default_factory=dict)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    case_count: int = 0
    source_truncated: bool = False
    created_at: Any | None = None


class CaseSetVersionOut(ApiModel):
    """版本快照元信息。"""

    id: str
    version: int
    reason: str = ""
    case_count: int = 0
    created_by: str | None = None
    created_by_name: str = ""
    created_at: Any | None = None


class CaseSetVersionDetailOut(CaseSetVersionOut):
    """版本详情：含完整快照。"""

    snapshot: dict[str, Any] = Field(default_factory=dict)


class CaseVersionDiffOut(ApiModel):
    """两个版本的字段级差异。"""

    base_version: int
    target_version: int
    base_count: int
    target_count: int
    added_count: int
    removed_count: int
    changed_count: int
    added: list[dict[str, Any]] = Field(default_factory=list)
    removed: list[dict[str, Any]] = Field(default_factory=list)
    changed: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False


class CaseReviewWorkspaceOut(ApiModel):
    """评审工作台聚合响应：状态、请求、评论、AI 历史与版本列表。"""

    case_set_id: str
    review_state: str = "draft"
    review_assignee_id: str | None = None
    review_assignee_name: str = ""
    active_request: CaseReviewRequestOut | None = None
    latest_request: CaseReviewRequestOut | None = None
    comments: list[CaseReviewCommentOut] = Field(default_factory=list)
    ai_runs: list[CaseReviewRunOut] = Field(default_factory=list)
    versions: list[CaseSetVersionOut] = Field(default_factory=list)


class CaseVersionCreateIn(ApiModel):
    """手动创建版本快照。"""

    reason: str = Field(default="", max_length=200)


class CaseVersionRestoreOut(ApiModel):
    """回滚结果：返回新建草稿的 ID 与名称。"""

    case_set_id: str
    name: str
    source_version: int


class GoldQaOut(ApiModel):
    """黄金 QA 集响应。"""

    id: str
    kb_id: str
    name: str
    version: int
    row_count: int
    owner: str = ""
    created_at: Any | None = None


# ─── 需求基线与用例覆盖 ───────────────────────────────────────────────


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
    """Token 用量中心响应；未配置单价时不做费用估算。"""

    days: int
    generated_at: Any | None = None
    calls: int = 0
    sessions: int = 0
    users: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
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
    """用例生成质量看板响应。"""

    days: int
    generated_at: Any | None = None
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


# ─── 全局搜索（N-07 MVP） ────────────────────────────────────────────


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
