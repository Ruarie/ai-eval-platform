"""模型单价与费用估算（N-10b）。

Revision ID: d3f7a1c9e6b2
Revises: b8e4d2f7c1a3
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3f7a1c9e6b2"
down_revision = "b8e4d2f7c1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """按模型名保存每百万 token 输入/输出单价。"""
    op.create_table(
        "model_prices",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("model_name", sa.String(), nullable=False),
        sa.Column("input_per_1m", sa.Float(), nullable=False, server_default="0"),
        sa.Column("output_per_1m", sa.Float(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), nullable=False, server_default="USD"),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("model_name", name="uq_model_prices_model_name"),
    )
    op.create_index("ix_model_prices_model_name", "model_prices", ["model_name"], unique=True)


def downgrade() -> None:
    """回退单价表；历史费用不再可重算。"""
    op.drop_index("ix_model_prices_model_name", table_name="model_prices")
    op.drop_table("model_prices")
