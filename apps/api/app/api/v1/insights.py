"""Repo insights endpoints: architecture diagram, onboarding docs, code map."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from typing import Any

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import ConflictError, NotFoundError
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


@router.get("/{repo_id}/metrics")
async def repo_metrics(repo_id: UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    repo = await RepositoryService(db).get_mine(user, repo_id)
    return await InsightsService(db).metrics(repo)


@router.get("/{repo_id}/files/{file_id}/similar")
async def repo_similar(
    repo_id: UUID, file_id: UUID, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    repo = await RepositoryService(db).get_mine(user, repo_id)
    try:
        return {"matches": await InsightsService(db).similar(user, repo, file_id)}
    except NotFoundError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ConflictError(f"Similar search failed: {type(e).__name__}: {e}") from e


@router.post("/{repo_id}/files/{file_id}/tests")
async def repo_gen_tests(
    repo_id: UUID, file_id: UUID, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    repo = await RepositoryService(db).get_mine(user, repo_id)
    try:
        return await InsightsService(db).gen_tests(repo, file_id)
    except NotFoundError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ConflictError(f"Test generation failed: {type(e).__name__}: {e}") from e
