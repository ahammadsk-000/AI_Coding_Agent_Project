"""GitHub endpoints (Phase 6) — PAT-based PR generation + AI review."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser
from app.core.exceptions import ConflictError
from app.domain.github.schemas import (
    CreatePRRequest,
    CreatePRResponse,
    GitHubStatus,
    ReviewPRRequest,
    ReviewPRResponse,
)
from app.domain.github.service import GitHubService
from app.infrastructure.github.client import GitHubError

router = APIRouter()


@router.get("/status", response_model=GitHubStatus)
async def github_status(_user: CurrentUser) -> GitHubStatus:
    configured, login, name = await GitHubService().status()
    return GitHubStatus(configured=configured, login=login, name=name)


@router.post("/pulls", response_model=CreatePRResponse)
async def create_pull_request(
    payload: CreatePRRequest, _user: CurrentUser
) -> CreatePRResponse:
    try:
        return await GitHubService().create_pr(payload)
    except GitHubError as e:
        raise ConflictError(f"GitHub: {e.message}") from e


@router.post("/review", response_model=ReviewPRResponse)
async def review_pull_request(
    payload: ReviewPRRequest, _user: CurrentUser
) -> ReviewPRResponse:
    try:
        return await GitHubService().review_pr(payload)
    except GitHubError as e:
        raise ConflictError(f"GitHub: {e.message}") from e
