"""协议档归属与个人模型隔离。

Revision ID: b3d8e1f6a2c4
Revises: d8a3c6e1f047
Create Date: 2026-11-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3d8e1f6a2c4"
down_revision = "d8a3c6e1f047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为协议档增加平台/个人归属，存量协议档一律回填为平台模型。"""
    op.add_column(
        "protocol_profiles",
        sa.Column("visibility", sa.String(), nullable=False, server_default="platform"),
    )
    op.add_column("protocol_profiles", sa.Column("owner_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_protocol_profiles_owner_id",
        "protocol_profiles",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_protocol_profiles_owner_id", "protocol_profiles", ["owner_id"]
    )
    op.create_index(
        "ix_protocol_profiles_visibility", "protocol_profiles", ["visibility"]
    )
    # 存量数据都是管理端/种子创建的公共模型；不回填 owner_id，避免把历史协议档
    # 误判成某个成员的私有资产。
    op.execute("UPDATE protocol_profiles SET visibility = 'platform', owner_id = NULL")


def downgrade() -> None:
    op.drop_index("ix_protocol_profiles_visibility", table_name="protocol_profiles")
    op.drop_index("ix_protocol_profiles_owner_id", table_name="protocol_profiles")
    op.drop_constraint(
        "fk_protocol_profiles_owner_id", "protocol_profiles", type_="foreignkey"
    )
    op.drop_column("protocol_profiles", "owner_id")
    op.drop_column("protocol_profiles", "visibility")
