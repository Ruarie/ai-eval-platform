"""合并能力中心资源表与协议档归属两条迁移链。

Revision ID: c9f1d2e3a4b5
Revises: b9e2f4a7c318, b3d8e1f6a2c4
Create Date: 2026-11-19

`b9e2f4a7c318`（能力中心 resources）与 `b3d8e1f6a2c4`（协议档归属）都基于
`d8a3c6e1f047`，并行合并后必须显式收口为一个 head，否则 alembic 会报多 head。
本迁移不产生 DDL，只声明两条分支已汇合。
"""

from __future__ import annotations

revision = "c9f1d2e3a4b5"
down_revision = ("b9e2f4a7c318", "b3d8e1f6a2c4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """两条分支各自完成建表/加列，合并点无额外变更。"""


def downgrade() -> None:
    """回退时仍由两条分支各自处理，合并点无额外变更。"""
