"""契约模型：accounts 域。

由 ``app.schemas`` 统一重导出，调用方导入路径不变。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


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
