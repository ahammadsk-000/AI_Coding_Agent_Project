"""User-aggregate use cases: registration, profile update, lookup."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import hash_password
from app.domain.users.models import User
from app.domain.users.repository import RoleRepository, UserRepository
from app.domain.users.schemas import UserCreate, UserUpdate

DEFAULT_ROLE = "member"


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)

    async def register(self, data: UserCreate, *, is_superuser: bool = False) -> User:
        existing = await self.users.get_by_email(data.email)
        if existing:
            raise ConflictError("Email already registered")

        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            is_active=True,
            is_superuser=is_superuser,
        )
        default_role = await self.roles.get_or_create(
            DEFAULT_ROLE, description="Default role assigned to new users"
        )
        user.roles.append(default_role)
        if is_superuser:
            admin_role = await self.roles.get_or_create("admin", description="Full admin")
            user.roles.append(admin_role)
        return await self.users.add(user)

    async def update_profile(self, user_id: UUID, data: UserUpdate) -> User:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        if data.full_name is not None:
            user.full_name = data.full_name
        if data.password is not None:
            user.hashed_password = hash_password(data.password)
        return await self.users.update(user)
