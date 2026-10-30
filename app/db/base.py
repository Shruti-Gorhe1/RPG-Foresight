"""SQLAlchemy async engine + session factory (PostgreSQL / asyncpg)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from shared.config import get_settings


def _make_engine():
    s = get_settings()
    return create_async_engine(s.database_url, echo=False, pool_pre_ping=True)


engine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def create_all_tables() -> None:
    """Create all ORM tables if they don't exist. Prefer Alembic in production —
    run `alembic upgrade head` as a pre-deploy step. Kept for local dev only."""
    import db.models  # noqa: F401  (register metadata on Base)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a DB session with auto commit/rollback."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
