"""契约模型：cases 域。

由 ``app.schemas`` 统一重导出，调用方导入路径不变。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from .accounts import (
    ApiModel,
    OrmOut,
)


class McpToolOut(ApiModel):
    """MCP 工具注册清单项，区分已挂载内置工具与独立注册项。"""

    name: str
    desc: str
    permission: Literal["read", "write"]
    enabled: bool
    source: Literal["builtin", "standalone"] = "builtin"

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
    def validate_unique_column_keys(self) -> DatasetUpdate:
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
    def validate_unique_row_no(self) -> RowsPayload:
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
    def validate_by_mode(self) -> AiGenerateIn:
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

class CaseSetCreate(ApiModel):
    """创建空用例集输入；column_schema 规则同数据集自定义列。"""

    name: str = Field(min_length=1, max_length=100)
    folder_id: str | None = None
    column_schema: list[ColumnSchemaItem] | None = None

    @model_validator(mode="after")
    def validate_unique_column_keys(self) -> CaseSetCreate:
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
    def validate_unique_column_keys(self) -> CaseSetUpdate:
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
    def validate_source(self) -> CaseCoverageIn:
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
    def validate_unique_case_id(self) -> CasesPayload:
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
    def validate_source(self) -> CaseAiGenerateIn:
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
