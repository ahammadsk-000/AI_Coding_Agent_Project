"""Multi-agent pipeline endpoint (planner → researchers → synthesizer)."""
from __future__ import annotations

from fastapi import APIRouter

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
