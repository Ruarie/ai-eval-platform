"""需求基线版本链（N-04）。

Revision ID: e2a6b9c4d7f1
Revises: c1e7f3a9d2b4
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e2a6b9c4d7f1"
down_revision = "c1e7f3a9d2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 parent_id，用于把需求改版串成不可变版本链。"""
    op.add_column("requirement_baselines", sa.Column("parent_id", sa.String(), nullable=True))
    op.create_index(
        "ix_requirement_baselines_parent_id", "requirement_baselines", ["parent_id"]
    )
    op.create_foreign_key(
        "fk_requirement_baselines_parent",
        "requirement_baselines",
        "requirement_baselines",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """回退版本链字段。"""
    op.drop_constraint(
        "fk_requirement_baselines_parent", "requirement_baselines", type_="foreignkey"
    )
    op.drop_index("ix_requirement_baselines_parent_id", table_name="requirement_baselines")
    op.drop_column("requirement_baselines", "parent_id")
