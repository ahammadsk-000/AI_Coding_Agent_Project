"""Multi-agent pipeline endpoints (planner → researchers → synthesizer → critic).

`POST /run`        — run the whole pipeline, return the full result.
`GET  /run/stream` — run it and stream each stage live over SSE.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import ConflictError
from app.domain.agents.schemas import AgentRunRequest, AgentRunResponse
from app.domain.agents.service import AgentOrchestrator

router = APIRouter()


@router.post("/run", response_model=AgentRunResponse)
async def run_agents(
    payload: AgentRunRequest, db: DbSession, user: CurrentUser
) -> AgentRunResponse:
    try:
        return await AgentOrchestrator(db).run(user, payload)
    except Exception as e:  # noqa: BLE001 — surface the real reason, not a 500
        raise ConflictError(f"Agent run failed: {type(e).__name__}: {e}") from e


@router.get("/run/stream")
async def run_agents_stream(
    user: CurrentUser,
    task: str,
    repository_ids: str = "",
    max_steps: int = 3,
    model: str | None = None,
    review: bool = True,
) -> EventSourceResponse:
    """Stream the multi-agent pipeline; each stage is an SSE event.

    Opens its OWN DB session inside the generator — the request-scoped session
    can be torn down before the streaming body runs, which would break the
    pipeline's queries mid-stream.
    """

    async def gen():
        from app.infrastructure.db.session import session_factory

        try:
            repo_ids = [UUID(r) for r in repository_ids.split(",") if r.strip()]
            req = AgentRunRequest(
                task=task,
                repository_ids=repo_ids,
                max_steps=max_steps,
                model=model,
                review=review,
            )
            async with session_factory() as session:
                async for event, data in AgentOrchestrator(session).run_stream(user, req):
                    yield {"event": event, "data": json.dumps(data, default=str)}
        except Exception as e:  # noqa: BLE001
            yield {
                "event": "error",
                "data": json.dumps({"message": f"{type(e).__name__}: {e}"}),
            }

    return EventSourceResponse(gen())
