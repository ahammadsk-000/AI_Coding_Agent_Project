"""Security primitives: password hashing and JWT encoding/decoding."""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.exceptions import InvalidTokenError

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# ---------- Passwords ----------
def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ---------- JWT (access) ----------
def create_access_token(
    *,
    subject: str | UUID,
    extra_claims: dict[str, Any] | None = None,
    ttl: timedelta | None = None,
) -> tuple[str, datetime]:
    """Return (encoded_jwt, expires_at)."""
    now = datetime.now(UTC)
    exp = now + (ttl or timedelta(minutes=settings.jwt_access_ttl_min))
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "typ": "access",
        "jti": secrets.token_hex(8),
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, exp


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise InvalidTokenError("Token expired") from e
    except jwt.InvalidTokenError as e:
        raise InvalidTokenError("Invalid token") from e
    if payload.get("typ") != "access":
        raise InvalidTokenError("Wrong token type")
    return payload


# ---------- Refresh tokens (opaque) ----------
def generate_refresh_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hex_hash). Store only the hash."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    import hashlib

    return hashlib.sha256(raw.encode()).hexdigest()
