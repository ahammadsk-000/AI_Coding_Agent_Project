"""Unit tests for clone URL validation."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-min-16-characters-long-xx")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@x:5432/x")
os.environ.setdefault("REDIS_URL", "redis://x:6379/0")
os.environ.setdefault("SEED_ADMIN", "false")

from app.infrastructure.git.clone import CloneError, validate_url  # noqa: E402


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/tiangolo/fastapi",
        "https://github.com/tiangolo/fastapi.git",
        "git@github.com:tiangolo/fastapi.git",
        "/srv/code/myrepo",
    ],
)
def test_valid_urls(url: str) -> None:
    # Should not raise
    validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/repo",
        "http://insecure.example.com/repo",  # only https allowed
        "javascript:alert(1)",
        "../../etc/passwd",
        "",
    ],
)
def test_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(CloneError):
        validate_url(url)
