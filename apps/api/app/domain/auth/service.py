"""Authentication use cases: login, refresh, logout.

Concerned only with credentials, tokens, and persistence — never with HTTP.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import InvalidTokenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from app.domain.auth.schemas import TokenPair
from app.domain.users.models import RefreshToken, User
from app.domain.users.repository import (
    AuditLogRepository,
    RefreshTokenRepository,
    UserRepository,
)


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.audit = AuditLogRepository(session)

    # ---------- internals ----------
    async def _issue_tokens(
        self, user: User, *, ip: str | None, user_agent: str | None
    ) -> TokenPair:
        access, access_exp = create_access_token(
            subject=user.id,
            extra_claims={
                "roles": [r.name for r in user.roles],
                "is_superuser": user.is_superuser,
            },
        )
        raw_refresh, refresh_hash = generate_refresh_token()
        refresh_exp = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_ttl_days)
        await self.refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                token_hash=refresh_hash,
                expires_at=refresh_exp,
                user_agent=(user_agent or "")[:512] or None,
                ip=ip,
            )
        )
        return TokenPair(
            access_token=access,
            refresh_token=raw_refresh,
            access_token_expires_at=access_exp,
            refresh_token_expires_at=refresh_exp,
        )

    # ---------- public use cases ----------
    async def authenticate(
        self, *, email: str, password: str, ip: str | None, user_agent: str | None
    ) -> tuple[User, TokenPair]:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            await self.audit.record(
                action="login_failed",
                resource="user",
                resource_id=email,
                ip=ip,
                user_agent=user_agent,
            )
            raise UnauthorizedError("Invalid credentials")
        if not user.is_active:
            raise UnauthorizedError("Account disabled")

        tokens = await self._issue_tokens(user, ip=ip, user_agent=user_agent)
        await self.audit.record(
            action="login_success",
            resource="user",
            user_id=user.id,
            resource_id=str(user.id),
            ip=ip,
            user_agent=user_agent,
        )
        return user, tokens

    async def refresh(
        self, *, raw_refresh: str, ip: str | None, user_agent: str | None
    ) -> tuple[User, TokenPair]:
        token = await self.refresh_tokens.get_active_by_hash(hash_refresh_token(raw_refresh))
        if token is None:
            raise InvalidTokenError("Refresh token invalid or revoked")
        now = datetime.now(UTC)
        if token.expires_at.replace(tzinfo=UTC) < now:
            await self.refresh_tokens.revoke(token, now)
            raise InvalidTokenError("Refresh token expired")
        if not token.user.is_active:
            raise UnauthorizedError("Account disabled")

        # Single-use rotation: revoke the presented token, issue a fresh pair.
        await self.refresh_tokens.revoke(token, now)
        tokens = await self._issue_tokens(token.user, ip=ip, user_agent=user_agent)
        await self.audit.record(
            action="token_refresh",
            resource="user",
            user_id=token.user.id,
            resource_id=str(token.user.id),
            ip=ip,
            user_agent=user_agent,
        )
        return token.user, tokens

    async def logout(self, *, raw_refresh: str, user: User, ip: str | None) -> None:
        token = await self.refresh_tokens.get_active_by_hash(hash_refresh_token(raw_refresh))
        if token is not None and token.user_id == user.id:
            await self.refresh_tokens.revoke(token, datetime.now(UTC))
        await self.audit.record(
            action="logout",
            resource="user",
            user_id=user.id,
            resource_id=str(user.id),
            ip=ip,
        )
