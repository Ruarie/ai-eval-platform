"""用例评审工作流与版本历史（N-02）。

Revision ID: c1e7f3a9d2b4
Revises: a9d4e6f2b8c1
Create Date: 2026-11-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c1e7f3a9d2b4"
down_revision = "a9d4e6f2b8c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """增加评审状态、评审请求/评论/AI 历史与不可变版本快照。"""
    op.add_column(
        "case_sets",
        sa.Column("review_state", sa.String(), nullable=False, server_default=sa.text("'draft'")),
    )
    op.add_column("case_sets", sa.Column("review_assignee_id", sa.String(), nullable=True))
    op.create_index("ix_case_sets_review_assignee_id", "case_sets", ["review_assignee_id"])
    op.create_foreign_key(
        "fk_case_sets_review_assignee",
        "case_sets",
        "users",
        ["review_assignee_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "case_review_requests",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_set_id", sa.String(), nullable=False),
        sa.Column("assignee_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("decision_note", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_set_id"], ["case_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'changes_requested', 'cancelled')",
            name="ck_case_review_requests_status",
        ),
    )
    op.create_index("ix_case_review_requests_case_set_id", "case_review_requests", ["case_set_id"])
    op.create_index("ix_case_review_requests_assignee_id", "case_review_requests", ["assignee_id"])
    op.create_index("ix_case_review_requests_status", "case_review_requests", ["status"])

    op.create_table(
        "case_review_comments",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_set_id", sa.String(), nullable=False),
        sa.Column("case_item_id", sa.String(), nullable=True),
        sa.Column("author_id", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_set_id"], ["case_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["case_item_id"], ["case_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_case_review_comments_case_set_id", "case_review_comments", ["case_set_id"])
    op.create_index("ix_case_review_comments_case_item_id", "case_review_comments", ["case_item_id"])
    op.create_index("ix_case_review_comments_author_id", "case_review_comments", ["author_id"])

    op.create_table(
        "case_review_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_set_id", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verdict", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("profile_id", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_set_id"], ["case_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_case_review_runs_case_set_id", "case_review_runs", ["case_set_id"])

    op.create_table(
        "case_set_versions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_set_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["case_set_id"], ["case_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("case_set_id", "version", name="uq_case_set_versions_set_version"),
    )
    op.create_index("ix_case_set_versions_case_set_id", "case_set_versions", ["case_set_id"])


def downgrade() -> None:
    """回退评审与版本表；已有快照会随表删除。"""
    op.drop_index("ix_case_set_versions_case_set_id", table_name="case_set_versions")
    op.drop_table("case_set_versions")
    op.drop_index("ix_case_review_runs_case_set_id", table_name="case_review_runs")
    op.drop_table("case_review_runs")
    op.drop_index("ix_case_review_comments_author_id", table_name="case_review_comments")
    op.drop_index("ix_case_review_comments_case_item_id", table_name="case_review_comments")
    op.drop_index("ix_case_review_comments_case_set_id", table_name="case_review_comments")
    op.drop_table("case_review_comments")
    op.drop_index("ix_case_review_requests_status", table_name="case_review_requests")
    op.drop_index("ix_case_review_requests_assignee_id", table_name="case_review_requests")
    op.drop_index("ix_case_review_requests_case_set_id", table_name="case_review_requests")
    op.drop_table("case_review_requests")
    op.drop_constraint("fk_case_sets_review_assignee", "case_sets", type_="foreignkey")
    op.drop_index("ix_case_sets_review_assignee_id", table_name="case_sets")
    op.drop_column("case_sets", "review_assignee_id")
    op.drop_column("case_sets", "review_state")
