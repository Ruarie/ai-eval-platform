"""记忆向量列解除固定维度。

个人记忆的向量由当前 Embedding 模型决定（如 bge-m3 为 1024 维），固定
``vector(1536)`` 会让非 OpenAI 维度写入直接失败。此迁移把列改为无维度
``vector``，检索侧逐行比较余弦相似度；无 pgvector 扩展的库保持 Text 回退不动。

Revision ID: c7a1e93d2f60
Revises: d8a3c6e1f047
Create Date: 2026-11-18 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7a1e93d2f60"
down_revision: str | None = "d8a3c6e1f047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _vector_ready(bind) -> bool:
    """扩展真实安装且 embedding 列已是 pgvector 类型时才迁移。"""
    try:
        if not bind.execute(
            sa.text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
        ).scalar():
            return False
        current = bind.execute(
            sa.text(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = 'memory_knowledge'::regclass AND attname = 'embedding'"
            )
        ).scalar()
    except Exception:  # 表或扩展缺失（隔离测试库）时保持原状
        return False
    return bool(current)


def upgrade() -> None:
    """把 embedding 列改为无维度 vector；无扩展环境为 Text 回退，不做变更。"""
    bind = op.get_bind()
    if not _vector_ready(bind):
        return
    current = bind.execute(
        sa.text(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'memory_knowledge'::regclass AND attname = 'embedding'"
        )
    ).scalar()
    if current == "vector":
        return
    op.execute(
        "ALTER TABLE memory_knowledge ALTER COLUMN embedding TYPE vector USING embedding::vector"
    )


def downgrade() -> None:
    """恢复固定 1536 维；已有非 1536 维向量时拒绝降级，避免静默截断数据。"""
    bind = op.get_bind()
    if not _vector_ready(bind):
        return
    has_rows = bind.execute(
        sa.text("SELECT 1 FROM memory_knowledge WHERE embedding IS NOT NULL LIMIT 1")
    ).scalar()
    if has_rows:
        raise RuntimeError("记忆已写入非固定维度向量，降级前需先清空 embedding 列")
    op.execute(
        "ALTER TABLE memory_knowledge ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
