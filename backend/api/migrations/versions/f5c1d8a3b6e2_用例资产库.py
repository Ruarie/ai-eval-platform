"""用例资产库（N-05）。

Revision ID: f5c1d8a3b6e2
Revises: e2a6b9c4d7f1
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f5c1d8a3b6e2"
down_revision = "e2a6b9c4d7f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """确认入库时物化的跨用例集资产快照。"""
    op.create_table(
        "case_assets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_case_set_id", sa.String(), nullable=True),
        sa.Column("source_case_item_id", sa.String(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("module", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("submodule", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("feature_point", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("strategy", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("priority", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("precondition", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("steps", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("expected", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["source_case_set_id"], ["case_sets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("source_case_item_id", name="uq_case_assets_source_item"),
    )
    op.create_index("ix_case_assets_source_case_set_id", "case_assets", ["source_case_set_id"])
    op.create_index("ix_case_assets_module", "case_assets", ["module"])
    op.create_index("ix_case_assets_strategy", "case_assets", ["strategy"])
    op.create_index("ix_case_assets_priority", "case_assets", ["priority"])
    op.create_index("ix_case_assets_revoked_at", "case_assets", ["revoked_at"])
    op.create_index("ix_case_assets_module_strategy", "case_assets", ["module", "strategy"])


def downgrade() -> None:
    """回退资产库；确认快照仍保留在 case_items。"""
    op.drop_index("ix_case_assets_module_strategy", table_name="case_assets")
    op.drop_index("ix_case_assets_revoked_at", table_name="case_assets")
    op.drop_index("ix_case_assets_priority", table_name="case_assets")
    op.drop_index("ix_case_assets_strategy", table_name="case_assets")
    op.drop_index("ix_case_assets_module", table_name="case_assets")
    op.drop_index("ix_case_assets_source_case_set_id", table_name="case_assets")
    op.drop_table("case_assets")
