"""会话事件号计数器（WS 事件号取号不再扫 MAX）。

Revision ID: c4d8f1a7b203
Revises: b8e4d2f7c1a3
Create Date: 2026-11-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d8f1a7b203"
down_revision = "b8e4d2f7c1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增会话级事件号计数器，并按历史最大 event_id 回填。"""
    op.add_column(
        "sessions",
        sa.Column("last_event_id", sa.BigInteger(), nullable=False, server_default="0"),
    )
    # 已有会话必须从历史最大值继续发号，否则重新从 1 开始会与历史事件撞唯一键。
    op.execute(
        "UPDATE sessions s SET last_event_id = COALESCE(("
        "  SELECT MAX(e.event_id) FROM ws_events e WHERE e.session_id = s.id), 0)"
    )


def downgrade() -> None:
    op.drop_column("sessions", "last_event_id")
