"""Typed domain exceptions and a single FastAPI handler that maps them to HTTP.

Routers and services raise these; they never construct HTTPException directly. This
keeps the domain layer framework-agnostic and the error contract centralised.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base class for all domain exceptions."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"


class ConflictError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"


class UnauthorizedError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "unauthorized"


class ForbiddenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"


class InvalidTokenError(UnauthorizedError):
    error_code = "invalid_token"


class RateLimitedError(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limited"


class ValidationDomainError(DomainError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"


def _build_payload(exc: DomainError, request: Request) -> dict[str, Any]:
    return {
        "error": {
            "code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
        "request_id": getattr(request.state, "request_id", None),
    }


async def _domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(status_code=exc.status_code, content=_build_payload(exc, request))


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    from app.core.logging import get_logger

    get_logger("app.unhandled").exception("unhandled_exception", error=str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {"code": "internal_error", "message": "Internal server error", "details": {}},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
