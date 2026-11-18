"""能力中心：资源实体与使用事件。

Revision ID: b9e2f4a7c318
Revises: d8a3c6e1f047
Create Date: 2026-11-18

新增两张表：
1. ``resources``：Agent / Skill / Script / Rule 四类资源的统一实体（kind + JSONB content），
   支持个人私有 / 团队共享、使用计数与「基于此创建」的血缘（source_id 自引用）。
2. ``resource_usage_events``：按次记录使用，供资源广场「飙升榜」按近 7 日增量排序。

两表均只存用户提交的定义文本，不含密钥：Agent 只引用协议档 ID，不落模型凭据。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b9e2f4a7c318"
down_revision = "d8a3c6e1f047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建资源表与使用事件表。"""
    op.create_table(
        "resources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column(
            "visibility", sa.String(), nullable=False, server_default=sa.text("'team'")
        ),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], name="fk_resources_owner"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["resources.id"], name="fk_resources_source"
        ),
    )
    op.create_index("ix_resources_kind", "resources", ["kind"])
    op.create_index(
        "ix_resources_kind_visibility", "resources", ["kind", "visibility"]
    )
    op.create_index("ix_resources_owner", "resources", ["owner_id"])
    op.create_index("ix_resources_usage", "resources", ["usage_count"])

    op.create_table(
        "resource_usage_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["resource_id"], ["resources.id"], name="fk_resource_usage_resource"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_resource_usage_user"
        ),
    )
    op.create_index(
        "ix_resource_usage_events_resource_time",
        "resource_usage_events",
        ["resource_id", "created_at"],
    )
    op.create_index(
        "ix_resource_usage_events_time", "resource_usage_events", ["created_at"]
    )


def downgrade() -> None:
    """回滚：先删事件表，再删资源表。"""
    op.drop_index("ix_resource_usage_events_time", table_name="resource_usage_events")
    op.drop_index(
        "ix_resource_usage_events_resource_time", table_name="resource_usage_events"
    )
    op.drop_table("resource_usage_events")
    op.drop_index("ix_resources_usage", table_name="resources")
    op.drop_index("ix_resources_owner", table_name="resources")
    op.drop_index("ix_resources_kind_visibility", table_name="resources")
    op.drop_index("ix_resources_kind", table_name="resources")
    op.drop_table("resources")
