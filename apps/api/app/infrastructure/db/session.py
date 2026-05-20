"""Async SQLAlchemy engine and session factory.

Single engine per process. The session factory returns a context-managed
`AsyncSession`; consumers use the `get_db` FastAPI dependency.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine: AsyncEngine = create_async_engine(
    str(settings.database_url),
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

_SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=_engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


def session_factory() -> AsyncSession:
    """Return a new AsyncSession. Caller is responsible for `async with`."""
    return _SessionLocal()


async def session_iter() -> AsyncGenerator[AsyncSession, None]:
    async with _SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    await _engine.dispose()


def get_engine() -> AsyncEngine:
    return _engine
