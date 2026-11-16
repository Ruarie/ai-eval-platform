"""页面用例生成、对比、评审改由 Worker 领取。

Revision ID: d8a3c6e1f047
Revises: c4d8f1a7b203
Create Date: 2026-11-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d8a3c6e1f047"
down_revision = "c4d8f1a7b203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """新增 case_ai_jobs。候选与评审结果放在 result，不进入 tasks 状态机。"""
    op.create_table(
        "case_ai_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('generate', 'compare', 'review')",
            name="ck_case_ai_jobs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_case_ai_jobs_status",
        ),
    )
    op.create_index("ix_case_ai_jobs_user_id", "case_ai_jobs", ["user_id"])
    op.create_index("ix_case_ai_jobs_queue", "case_ai_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_case_ai_jobs_queue", table_name="case_ai_jobs")
    op.drop_index("ix_case_ai_jobs_user_id", table_name="case_ai_jobs")
    op.drop_table("case_ai_jobs")
