"""HTTP request metrics middleware (Phase 8).

Records request count + latency per (method, route-template, status). We use the
matched route template (e.g. `/api/v1/conversations/{conv_id}`) rather than the
raw path so high-cardinality IDs don't explode the metric label space.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core import metrics as M


def _route_template(request: Request) -> str:
    """Best-effort matched route template; falls back to the raw path."""
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - started
            path = _route_template(request)
            # Skip the metrics endpoint itself to avoid self-referential noise.
            if path != "/metrics":
                M.http_requests_total.labels(
                    request.method, path, str(status_code)
                ).inc()
                M.http_request_duration_seconds.labels(
                    request.method, path
                ).observe(elapsed)
