"""契约模型：能力中心资源域。

四类资源（Agent / Skill / Script / Rule）共用一套出入参；``content`` 由前端
按 kind 渲染不同字段，服务端只做体积与结构的最小校验，不对业务字段做语义约束。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .accounts import ApiModel

ResourceKind = Literal["agent", "skill", "script", "rule", "rag"]
ResourceVisibility = Literal["private", "team"]


class ResourceCreateIn(ApiModel):
    """新建资源输入。"""

    kind: ResourceKind
    name: str = Field(min_length=1, max_length=80)
    summary: str = Field(default="", max_length=400)
    content: dict[str, Any] = Field(default_factory=dict)
    visibility: ResourceVisibility = "team"


class ResourceUpdateIn(ApiModel):
    """更新资源输入；字段缺省表示不修改。"""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=400)
    content: dict[str, Any] | None = None
    visibility: ResourceVisibility | None = None


class ResourceOut(ApiModel):
    """资源列表与详情共用的出参。"""

    id: str
    kind: str
    name: str
    summary: str
    content: dict[str, Any]
    owner_id: str | None
    owner_name: str
    visibility: str
    usage_count: int
    source_id: str | None
    editable: bool
    created_at: str
    updated_at: str


class ResourceListOut(ApiModel):
    """分页列表。"""

    items: list[ResourceOut]
    total: int


class ResourceCloneIn(ApiModel):
    """基于此创建：可覆盖名称，未提供时沿用原名加「副本」。"""

    name: str | None = Field(default=None, min_length=1, max_length=80)


class ResourceUseOut(ApiModel):
    """使用回执：返回最新计数与内容，前端直接复制到剪贴板。"""

    id: str
    usage_count: int
    content: dict[str, Any]


class PlazaRankItem(ApiModel):
    """榜单条目。"""

    id: str
    kind: str
    name: str
    summary: str
    owner_name: str
    usage_count: int
    weekly_uses: int
    created_at: str


class PlazaOut(ApiModel):
    """资源广场：精选 + 三榜。"""

    total: int
    featured: list[PlazaRankItem]
    popular: list[PlazaRankItem]
    rising: list[PlazaRankItem]
    newest: list[PlazaRankItem]
