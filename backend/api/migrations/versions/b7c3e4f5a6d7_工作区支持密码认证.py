"""工作区支持密码认证（密码不落库）

Revision ID: b7c3e4f5a6d7
Revises: 9c1f4b7d2e30
Create Date: 2026-11-05

远程工作区除"服务端预置私钥"外，支持"连接时临时提供密码"：
``auth_type='password'`` 时不需要 ``ssh_key_name``，密码由前端在页面上输入、
经请求头随本次调用传入，服务端不落库、不缓存。
"""

from alembic import op
import sqlalchemy as sa

revision = "b7c3e4f5a6d7"
down_revision = "9c1f4b7d2e30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column(
            "auth_type", sa.String(length=16), nullable=False, server_default="key_file"
        ),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "auth_type")
