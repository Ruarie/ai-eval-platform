"""工作区支持远程 SSH

Revision ID: 9c1f4b7d2e30
Revises: b5e2d7c94a10
Create Date: 2026-11-05

工作区从"本地目录"扩展为"本地目录 / 远程 SSH 目录"：

- ``kind``：``local``（默认，沿用 ``data/workspaces/<id>``）或 ``ssh``；
- ``ssh_host`` / ``ssh_port`` / ``ssh_user``：连接目标；
- ``ssh_key_name``：私钥**文件名**，私钥内容放在宿主机 ``WORKSPACE_SSH_KEY_DIR``，
  平台不落库、不回显；
- ``remote_root``：远程根目录，允许绝对路径。
"""

from alembic import op
import sqlalchemy as sa

revision = "9c1f4b7d2e30"
down_revision = "b5e2d7c94a10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="local"),
    )
    op.add_column("workspaces", sa.Column("ssh_host", sa.String(length=200), nullable=True))
    op.add_column("workspaces", sa.Column("ssh_port", sa.Integer(), nullable=True))
    op.add_column("workspaces", sa.Column("ssh_user", sa.String(length=100), nullable=True))
    op.add_column("workspaces", sa.Column("ssh_key_name", sa.String(length=200), nullable=True))
    op.add_column("workspaces", sa.Column("remote_root", sa.String(length=500), nullable=True))
    op.create_check_constraint(
        "ck_workspaces_kind", "workspaces", "kind IN ('local', 'ssh')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_workspaces_kind", "workspaces", type_="check")
    for column in (
        "remote_root",
        "ssh_key_name",
        "ssh_user",
        "ssh_port",
        "ssh_host",
        "kind",
    ):
        op.drop_column("workspaces", column)
