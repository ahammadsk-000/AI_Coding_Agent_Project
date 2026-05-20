"""User-self endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.domain.users.schemas import UserRead, UserUpdate
from app.domain.users.service import UserService

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch("/me", response_model=UserRead)
async def update_me(payload: UserUpdate, user: CurrentUser, db: DbSession) -> UserRead:
    updated = await UserService(db).update_profile(user.id, payload)
    return UserRead.model_validate(updated)
