"""Liveness, readiness, and ping endpoints."""
from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel
from sqlalchemy import text

from app.core.dependencies import DbSession
from app.infrastructure.redis.client import get_redis

router = APIRouter()


class PingResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/ping", response_model=PingResponse, status_code=status.HTTP_200_OK)
async def ping() -> PingResponse:
    return PingResponse(status="ok", service="api")


@router.get("/ready", response_model=ReadyResponse)
async def ready(db: DbSession) -> ReadyResponse:
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e.__class__.__name__}"

    try:
        pong = await get_redis().ping()
        checks["redis"] = "ok" if pong else "error: no pong"
    except Exception as e:
        checks["redis"] = f"error: {e.__class__.__name__}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return ReadyResponse(status=overall, checks=checks)
