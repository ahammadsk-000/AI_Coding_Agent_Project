"""Repo insights endpoints: architecture diagram, onboarding docs, code map."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import ConflictError
from app.domain.insights.service import InsightsService
from app.domain.repositories.service import RepositoryService

router = APIRouter()


@router.post("/{repo_id}/diagram")
async def repo_diagram(repo_id: UUID, user: CurrentUser, db: DbSession) -> dict[str, str]:
    repo = await RepositoryService(db).get_mine(user, repo_id)  # authz / 404
    try:
        return {"mermaid": await InsightsService(db).diagram(repo)}
    except Exception as e:  # noqa: BLE001
        raise ConflictError(f"Diagram failed: {type(e).__name__}: {e}") from e


@router.post("/{repo_id}/docs")
async def repo_docs(repo_id: UUID, user: CurrentUser, db: DbSession) -> dict[str, str]:
    repo = await RepositoryService(db).get_mine(user, repo_id)
    try:
        return {"markdown": await InsightsService(db).docs(repo)}
    except Exception as e:  # noqa: BLE001
        raise ConflictError(f"Docs failed: {type(e).__name__}: {e}") from e


@router.get("/{repo_id}/codemap")
async def repo_codemap(repo_id: UUID, user: CurrentUser, db: DbSession) -> dict[str, str]:
    repo = await RepositoryService(db).get_mine(user, repo_id)
    try:
        return {"mermaid": await InsightsService(db).codemap(repo)}
    except Exception as e:  # noqa: BLE001
        raise ConflictError(f"Code map failed: {type(e).__name__}: {e}") from e
