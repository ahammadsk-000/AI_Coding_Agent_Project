"""Sliding-window rate limiter backed by Redis.

Counts requests per (subject, route_group) over a 60s window. `subject` is the user
id if authenticated, otherwise the client IP. Limits come from settings.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.exceptions import RateLimitedError
from app.infrastructure.redis.client import get_redis

_WINDOW_S = 60


def _route_group(path: str) -> str:
    if path.startswith("/api/v1/auth"):
        return "auth"
    if path.startswith("/api/"):
        return "api"
    return "other"


def _limit_for(group: str, authed: bool) -> int:
    if group == "auth":
        return settings.rate_limit_auth_endpoints_per_min
    return settings.rate_limit_authed_per_min if authed else settings.rate_limit_anon_per_min


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip health/metrics + non-API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        subject = (request.client.host if request.client else "unknown") + ":anon"
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            # cheap subject key — actual user check happens later
            subject = "tok:" + auth.split(" ", 1)[1][:16]

        group = _route_group(request.url.path)
        limit = _limit_for(group, authed=auth is not None)
        key = f"rl:{group}:{subject}:{int(time.time()) // _WINDOW_S}"

        redis = get_redis()
        try:
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, _WINDOW_S + 1)
        except Exception:
            # fail-open: do not block traffic if Redis is down
            return await call_next(request)

        if count > limit:
            err = RateLimitedError(
                "Rate limit exceeded",
                details={"limit": limit, "window_seconds": _WINDOW_S, "group": group},
            )
            return JSONResponse(
                status_code=err.status_code,
                content={
                    "error": {"code": err.error_code, "message": err.message, "details": err.details},
                    "request_id": getattr(request.state, "request_id", None),
                },
                headers={"Retry-After": str(_WINDOW_S)},
            )

        return await call_next(request)
