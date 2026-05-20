"""Pure-unit tests for security primitives — no DB, no app, no containers."""
from __future__ import annotations

import os
import uuid
from datetime import timedelta

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-min-16-characters-long-xx")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@x:5432/x")
os.environ.setdefault("REDIS_URL", "redis://x:6379/0")
os.environ.setdefault("SEED_ADMIN", "false")

from app.core.exceptions import InvalidTokenError  # noqa: E402
from app.core.security import (  # noqa: E402
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_password_hash_and_verify_roundtrip() -> None:
    h = hash_password("hunter2-with-length")
    assert h != "hunter2-with-length"
    assert verify_password("hunter2-with-length", h)
    assert not verify_password("wrong", h)


def test_password_verify_returns_false_on_garbage_hash() -> None:
    assert not verify_password("anything", "not-a-real-hash")


def test_jwt_roundtrip() -> None:
    uid = uuid.uuid4()
    token, exp = create_access_token(subject=uid, extra_claims={"roles": ["admin"]})
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["typ"] == "access"
    assert payload["roles"] == ["admin"]
    assert exp.timestamp() > 0


def test_jwt_expired_is_rejected() -> None:
    token, _ = create_access_token(subject=uuid.uuid4(), ttl=timedelta(seconds=-1))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_jwt_tampered_is_rejected() -> None:
    token, _ = create_access_token(subject=uuid.uuid4())
    bad = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(InvalidTokenError):
        decode_access_token(bad)


def test_refresh_token_is_opaque_and_hashable() -> None:
    raw, h = generate_refresh_token()
    assert len(raw) > 32
    assert h == hash_refresh_token(raw)
    assert hash_refresh_token("different") != h
