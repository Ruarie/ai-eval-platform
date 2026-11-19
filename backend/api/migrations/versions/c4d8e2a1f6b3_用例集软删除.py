"""用例集软删除列。

只用 `deleted_at` 标记：列表与详情过滤掉，版本快照、评审记录、报告仍然可追溯。
对照工作区注销的口径，不做物理删除，避免级联清掉历史。

Revision ID: c4d8e2a1f6b3
Revises: b9e2f4a7c318
Create Date: 2026-11-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Alembic 迁移标识。
revision: str = "c4d8e2a1f6b3"
down_revision: Union[str, None] = "b9e2f4a7c318"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为用例集补软删除标记与查询索引。"""
    op.add_column("case_sets", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_case_sets_deleted_at", "case_sets", ["deleted_at"])


def downgrade() -> None:
    """回滚：移除索引与列。"""
    op.drop_index("ix_case_sets_deleted_at", table_name="case_sets")
    op.drop_column("case_sets", "deleted_at")
