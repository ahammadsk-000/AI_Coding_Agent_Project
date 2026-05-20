"""Test fixtures.

- A session-scoped Postgres container provides an isolated database per test run.
- A function-scoped transactional session lets each test see a clean slate.
- The ASGI app is wired through `httpx.AsyncClient` with ASGI transport — no real
  network sockets opened.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set required env BEFORE importing app modules
os.environ.setdefault("JWT_SECRET", "test-secret-min-16-characters-long-xx")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SEED_ADMIN", "false")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------- containers ----------
@pytest.fixture(scope="session")
def postgres_url() -> Generator[str, None, None]:
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        # Convert sync URL → async asyncpg URL
        sync_url = pg.get_connection_url()  # postgresql+psycopg2://...
        async_url = sync_url.replace("postgresql+psycopg2", "postgresql+asyncpg")
        os.environ["DATABASE_URL"] = async_url
        yield async_url


@pytest.fixture(scope="session")
def redis_url() -> Generator[str, None, None]:
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as r:
        url = f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"
        os.environ["REDIS_URL"] = url
        yield url


# ---------- schema + app ----------
@pytest_asyncio.fixture(scope="session")
async def _migrated(postgres_url: str, redis_url: str) -> AsyncGenerator[None, None]:
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.infrastructure.db.base import Base
    from app.domain.users import models as _models  # noqa: F401 — registers metadata

    engine = create_async_engine(postgres_url, future=True)
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text('CREATE EXTENSION IF NOT EXISTS "citext"'))
        await conn.execute(__import__("sqlalchemy").text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def client(_migrated: None) -> AsyncGenerator[AsyncClient, None]:
    # Late import so env vars are picked up by config
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session(_migrated: None) -> AsyncGenerator:
    from app.infrastructure.db.session import session_factory

    async with session_factory() as session:
        yield session
        await session.rollback()
