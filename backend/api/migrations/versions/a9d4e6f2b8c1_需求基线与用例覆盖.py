"""需求基线、需求条目与用例关联。

Revision ID: a9d4e6f2b8c1
Revises: b7c3e4f5a6d7
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic 迁移标识。
revision: str = "a9d4e6f2b8c1"
down_revision: str | None = "b7c3e4f5a6d7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """新增需求基线、需求条目与用例关联三张表，并给用例集补绑定列。"""
    # 需求基线：确认后只读，revision 随人工校对/确认递增。
    op.create_table(
        "requirement_baselines",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default="未命名需求基线"),
        sa.Column("source_kind", sa.String(), nullable=False, server_default="text"),
        sa.Column("source_name", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requirement_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_requirement_baselines_created_by"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed')", name="ck_requirement_baselines_status"
        ),
    )
    op.create_index(
        "ix_requirement_baselines_status",
        "requirement_baselines",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_requirement_baselines_created_by",
        "requirement_baselines",
        ["created_by"],
        unique=False,
    )
    op.alter_column("requirement_baselines", "name", server_default=None)
    op.alter_column("requirement_baselines", "source_kind", server_default=None)
    op.alter_column("requirement_baselines", "source_name", server_default=None)
    op.alter_column("requirement_baselines", "status", server_default=None)
    op.alter_column("requirement_baselines", "revision", server_default=None)
    op.alter_column("requirement_baselines", "requirement_count", server_default=None)
    op.alter_column("requirement_baselines", "created_at", server_default=None)
    op.alter_column("requirement_baselines", "updated_at", server_default=None)

    # 需求条目：同一基线内编号唯一；只保存原文条目与回查位置。
    op.create_table(
        "requirement_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("baseline_id", sa.String(), nullable=False),
        sa.Column("req_no", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("priority", sa.String(), nullable=False, server_default=""),
        sa.Column("module", sa.String(), nullable=False, server_default=""),
        sa.Column("source_ref", sa.String(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["baseline_id"],
            ["requirement_baselines.id"],
            name="fk_requirement_items_baseline",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "baseline_id", "req_no", name="uq_requirement_items_baseline_req_no"
        ),
    )
    op.create_index(
        "ix_requirement_items_baseline_id",
        "requirement_items",
        ["baseline_id"],
        unique=False,
    )
    op.alter_column("requirement_items", "title", server_default=None)
    op.alter_column("requirement_items", "description", server_default=None)
    op.alter_column("requirement_items", "priority", server_default=None)
    op.alter_column("requirement_items", "module", server_default=None)
    op.alter_column("requirement_items", "source_ref", server_default=None)
    op.alter_column("requirement_items", "sort_order", server_default=None)
    op.alter_column("requirement_items", "created_at", server_default=None)

    # 用例集绑定列：基线删除时置空，不级联删用例集。
    op.add_column("case_sets", sa.Column("requirement_baseline_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_case_sets_requirement_baseline",
        "case_sets",
        "requirement_baselines",
        ["requirement_baseline_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_case_sets_requirement_baseline_id",
        "case_sets",
        ["requirement_baseline_id"],
        unique=False,
    )

    # 用例关联：同一用例与同一需求只保留一条；删除用例或需求时级联清理。
    op.create_table(
        "case_requirement_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("case_set_id", sa.String(), nullable=False),
        sa.Column("case_item_id", sa.String(), nullable=False),
        sa.Column("requirement_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["case_set_id"],
            ["case_sets.id"],
            name="fk_case_requirement_links_case_set",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_item_id"],
            ["case_items.id"],
            name="fk_case_requirement_links_case_item",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"],
            ["requirement_items.id"],
            name="fk_case_requirement_links_requirement",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_item_id", "requirement_id", name="uq_case_requirement_links_pair"
        ),
    )
    op.create_index(
        "ix_case_requirement_links_case_set_id",
        "case_requirement_links",
        ["case_set_id"],
        unique=False,
    )
    op.create_index(
        "ix_case_requirement_links_case_item_id",
        "case_requirement_links",
        ["case_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_case_requirement_links_requirement_id",
        "case_requirement_links",
        ["requirement_id"],
        unique=False,
    )
    op.alter_column("case_requirement_links", "source", server_default=None)
    op.alter_column("case_requirement_links", "confidence", server_default=None)
    op.alter_column("case_requirement_links", "created_at", server_default=None)


def downgrade() -> None:
    """按反向依赖删除关联表、绑定列与需求表。"""
    op.drop_index(
        "ix_case_requirement_links_requirement_id",
        table_name="case_requirement_links",
    )
    op.drop_index(
        "ix_case_requirement_links_case_item_id",
        table_name="case_requirement_links",
    )
    op.drop_index(
        "ix_case_requirement_links_case_set_id",
        table_name="case_requirement_links",
    )
    op.drop_table("case_requirement_links")

    op.drop_index("ix_case_sets_requirement_baseline_id", table_name="case_sets")
    op.drop_constraint("fk_case_sets_requirement_baseline", "case_sets", type_="foreignkey")
    op.drop_column("case_sets", "requirement_baseline_id")

    op.drop_index("ix_requirement_items_baseline_id", table_name="requirement_items")
    op.drop_table("requirement_items")

    op.drop_index("ix_requirement_baselines_created_by", table_name="requirement_baselines")
    op.drop_index("ix_requirement_baselines_status", table_name="requirement_baselines")
    op.drop_table("requirement_baselines")
