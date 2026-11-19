from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings
from .models import Base  # noqa: F401  re-export：migrations/env.py 依赖此入口

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # 显式连接池边界：默认 pool_size=5 且无回收，长连接会被 PG / 中间件
    # 单方面断开，池耗尽时请求会无限等待。
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """请求级会话：异常时显式回滚，避免脏事务随连接归还池中。"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
