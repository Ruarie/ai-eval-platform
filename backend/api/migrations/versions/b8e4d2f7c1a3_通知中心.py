"""站内通知中心（N-08）。

Revision ID: b8e4d2f7c1a3
Revises: f5c1d8a3b6e2
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8e4d2f7c1a3"
down_revision = "f5c1d8a3b6e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建通知表与用户维度索引。"""
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False, server_default="system"),
        sa.Column("title", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("body", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("link", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("dedupe_key", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index(
        "ix_notifications_user_read_created", "notifications", ["user_id", "read_at", "created_at"]
    )


def downgrade() -> None:
    """回退通知表。"""
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
