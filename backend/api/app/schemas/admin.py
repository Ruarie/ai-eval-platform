"""契约模型：管理后台总览。

只承载聚合后的计数与最近审计，不返回正文、不返回密钥；所有字段都可由
数据库直接算出，前端不二次聚合，避免两套口径。
"""

from __future__ import annotations

from pydantic import Field

from .accounts import ApiModel


class OverviewUsers(ApiModel):
    """成员口径：active_7d 以最近登录计算，disabled 单独列出。"""

    total: int
    new_7d: int
    active_7d: int
    disabled: int


class OverviewSessions(ApiModel):
    """会话口径：total 不计软删除；shared 为团队共享会话数。"""

    total: int
    new_7d: int
    shared: int


class OverviewTasks(ApiModel):
    """任务口径：只统计近 7 天，避免历史全量拖慢首屏。"""

    total_7d: int
    by_status: dict[str, int] = Field(default_factory=dict)


class OverviewResources(ApiModel):
    """能力中心资源口径。"""

    total: int
    new_7d: int
    team: int
    private: int
    usage_total: int
    by_kind: dict[str, int] = Field(default_factory=dict)


class OverviewStorage(ApiModel):
    """存储口径：文件字节数与知识库文档数。"""

    files: int
    bytes: int
    kb_count: int
    kb_docs: int


class OverviewAuditItem(ApiModel):
    """最近审计条目：只给定位信息，不含 detail 明细。"""

    id: int
    action: str
    target_type: str | None = None
    target_id: str | None = None
    user_name: str = ""
    ip: str | None = None
    ts: str


class AdminOverviewOut(ApiModel):
    """后台首屏：一次请求给出全部大盘数字。"""

    users: OverviewUsers
    sessions: OverviewSessions
    tasks: OverviewTasks
    resources: OverviewResources
    storage: OverviewStorage
    audit_24h: int
    top_actions: dict[str, int] = Field(default_factory=dict)
    recent_audit: list[OverviewAuditItem] = Field(default_factory=list)
    generated_at: str
