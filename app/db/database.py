"""
Database engine & session factory.

本番: asyncpg (PostgreSQL)
テスト: aiosqlite (SQLite in-memory)
DATABASE_URL の dialect で自動判別する。
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _build_engine():
    url = settings.DATABASE_URL
    is_sqlite = url.startswith("sqlite")
    kwargs: dict = dict(echo=False)
    if is_sqlite:
        # SQLite はコネクションプール設定を受け付けない
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
    return create_async_engine(url, **kwargs)


engine = _build_engine()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():  # type: ignore[return]
    """
    FastAPI dependency — yields a DB session per request.

    重要: commit はコールバック前に明示的に行う必要があるため、
    ここでは commit せず session を渡すだけにする。
    各エンドポイントで必要なタイミングで await session.commit() を呼ぶ。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """アプリ起動時にテーブルを自動作成する（alembicと共存可）。"""
    async with engine.begin() as conn:
        from app.db import models  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
