"""Unit tests for file extension -> language detection."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-min-16-characters-long-xx")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@x:5432/x")
os.environ.setdefault("REDIS_URL", "redis://x:6379/0")
os.environ.setdefault("SEED_ADMIN", "false")

from app.infrastructure.parsers.language import detect_language  # noqa: E402


def test_python_extension() -> None:
    assert detect_language(Path("foo.py")) == "python"
    assert detect_language(Path("foo.pyi")) == "python"


def test_typescript_and_tsx() -> None:
    assert detect_language(Path("foo.ts")) == "typescript"
    assert detect_language(Path("foo.tsx")) == "typescript"


def test_dockerfile_by_name() -> None:
    assert detect_language(Path("Dockerfile")) == "dockerfile"


def test_unknown_returns_none() -> None:
    assert detect_language(Path("foo.zzz")) is None


def test_case_insensitive_extension() -> None:
    assert detect_language(Path("FOO.PY")) == "python"
