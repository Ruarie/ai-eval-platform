"""契约模型：kb 域。

由 ``app.schemas`` 统一重导出，调用方导入路径不变。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .accounts import (
    ApiModel,
)


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
