"""Automated repo audit endpoint — streams a per-file review over SSE."""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.dependencies import CurrentUser
from app.domain.audit.service import AuditService

router = APIRouter()


@router.get("/run/stream")
async def audit_stream(
    user: CurrentUser,
    repository_id: str,
    depth: int = 6,
    model: str | None = None,
) -> EventSourceResponse:
    """Stream the audit: one `file` event per reviewed file, then a `summary`.

    Opens its own DB session inside the generator (the request-scoped one can be
    torn down before the streaming body runs).
    """

    async def gen():
        from app.infrastructure.db.session import session_factory

        try:
            rid = UUID(repository_id)
            d = max(1, min(int(depth), 15))
            async with session_factory() as session:
                async for event, data in AuditService(session).run_stream(
                    user, rid, d, model
                ):
                    yield {"event": event, "data": json.dumps(data, default=str)}
        except Exception as e:  # noqa: BLE001
            yield {
                "event": "error",
                "data": json.dumps({"message": f"{type(e).__name__}: {e}"}),
            }

    return EventSourceResponse(gen())
