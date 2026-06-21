"""Async SQLAlchemy engine and session factory.

Single engine per process. The session factory returns a context-managed
`AsyncSession`; consumers use the `get_db` FastAPI dependency.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _build_async_engine() -> AsyncEngine:
    """Create the async engine, normalizing libpq-style SSL params for asyncpg.

    Managed Postgres providers (e.g. Neon) hand out URLs with `?sslmode=require`
    (and sometimes `channel_binding`). psycopg (Alembic) accepts those, but
    asyncpg's connect() rejects them with `unexpected keyword argument 'sslmode'`.
    Pull them out of the URL and translate sslmode into asyncpg's own `ssl` arg.
    """
    url = make_url(str(settings.database_url))
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if isinstance(sslmode, (list, tuple)):
        sslmode = sslmode[0] if sslmode else None
    query.pop("channel_binding", None)
    url = url.set(query=query)

    connect_args: dict[str, object] = {}
    if isinstance(sslmode, str) and sslmode.lower() not in ("", "disable"):
        connect_args["ssl"] = "require"

    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        future=True,
        connect_args=connect_args,
    )


_engine: AsyncEngine = _build_async_engine()

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
