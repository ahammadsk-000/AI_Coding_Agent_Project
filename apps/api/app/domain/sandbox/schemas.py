"""DTOs for the sandbox endpoints."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)


class ClassifyResponse(BaseModel):
    verdict: Literal["allow", "approval", "blocked"]
    reason: str


class SandboxRunRequest(BaseModel):
    """Sent over the WebSocket as the first (and only) client frame."""
    command: str = Field(min_length=1, max_length=4000)
    repository_id: UUID | None = None
    # Must be true to run a command the classifier flagged as needing approval.
    approved: bool = False
