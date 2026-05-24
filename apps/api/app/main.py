"""FastAPI application factory + ASGI entrypoint.

Composes middleware, routers, exception handlers, lifespan, and observability.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.middleware.metrics import MetricsMiddleware
from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.middleware.request_id import RequestIdMiddleware
from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.infrastructure.db.session import dispose_engine
from app.infrastructure.redis.client import close_redis

log = get_logger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    log.info("startup", env=settings.app_env, version="0.1.0")
    if settings.seed_admin:
        await _seed_admin()
    try:
        yield
    finally:
        log.info("shutdown")
        await close_redis()
        await dispose_engine()


async def _seed_admin() -> None:
    """Idempotently create the dev admin user from env settings."""
    from app.domain.users.schemas import UserCreate
    from app.domain.users.service import UserService
    from app.infrastructure.db.session import session_factory

    async with session_factory() as session:
        try:
            existing = await UserService(session).users.get_by_email(settings.seed_admin_email)
            if existing:
                return
            await UserService(session).register(
                UserCreate(
                    email=settings.seed_admin_email,  # type: ignore[arg-type]
                    password=settings.seed_admin_password,
                    full_name="Local Admin",
                ),
                is_superuser=True,
            )
            await session.commit()
            log.info("seed_admin_created", email=settings.seed_admin_email)
        except Exception as e:
            await session.rollback()
            log.warning("seed_admin_failed", error=str(e))


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI Coding Agent Platform — API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ---- middleware (order matters; outermost added last) ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # ---- exception handlers ----
    register_exception_handlers(app)

    # ---- routes ----
    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    if settings.prometheus_enabled:
        @app.get("/metrics", tags=["observability"])
        async def metrics() -> PlainTextResponse:
            return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
