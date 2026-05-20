"""FastAPI dependencies: DB session, current user, RBAC guards.

Routers depend on these. Services do not import FastAPI.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, InvalidTokenError, UnauthorizedError
from app.core.security import decode_access_token
from app.domain.users.models import User
from app.domain.users.repository import UserRepository
from app.infrastructure.db.session import session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as e:
        raise InvalidTokenError("Token missing valid subject") from e

    user = await UserRepository(db).get(user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: str) -> Callable[[User], User]:
    """Return a dependency that asserts the current user has at least one of `roles`."""
    required = set(roles)

    async def _guard(user: CurrentUser) -> User:
        user_roles = {r.name for r in user.roles}
        if user.is_superuser or user_roles & required:
            return user
        raise ForbiddenError(
            "Insufficient role",
            details={"required_any_of": sorted(required), "have": sorted(user_roles)},
        )

    return _guard
