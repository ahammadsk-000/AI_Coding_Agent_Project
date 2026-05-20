"""Data access for User / Role / RefreshToken / AuditLog.

All queries live here. Services depend on this class — they never call
`session.execute()` directly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.users.models import AuditLog, RefreshToken, Role, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: UUID) -> User | None:
        stmt = select(User).options(selectinload(User.roles)).where(User.id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).options(selectinload(User.roles)).where(User.email == email)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user, attribute_names=["roles"])
        return user

    async def update(self, user: User) -> User:
        await self.session.flush()
        return user


class RoleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_name(self, name: str) -> Role | None:
        return (
            await self.session.execute(select(Role).where(Role.name == name))
        ).scalar_one_or_none()

    async def get_or_create(self, name: str, description: str | None = None) -> Role:
        role = await self.get_by_name(name)
        if role:
            return role
        role = Role(name=name, description=description)
        self.session.add(role)
        await self.session.flush()
        return role


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, token: RefreshToken) -> RefreshToken:
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_active_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = (
            select(RefreshToken)
            .options(selectinload(RefreshToken.user).selectinload(User.roles))
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def revoke(self, token: RefreshToken, at: datetime) -> None:
        token.revoked_at = at
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: UUID, at: datetime) -> int:
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )
        result = await self.session.execute(stmt)
        tokens = list(result.scalars())
        for t in tokens:
            t.revoked_at = at
        await self.session.flush()
        return len(tokens)


class AuditLogRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        *,
        action: str,
        resource: str,
        user_id: UUID | None = None,
        resource_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry = AuditLog(
            action=action,
            resource=resource,
            user_id=user_id,
            resource_id=resource_id,
            ip=ip,
            user_agent=user_agent,
            meta=metadata,
        )
        self.session.add(entry)
        await self.session.flush()
