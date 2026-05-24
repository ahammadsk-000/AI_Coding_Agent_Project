"""DTOs for memory."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4096)
    scope: Literal["user", "project", "conversation"] = "user"
    repository_id: UUID | None = None
    conversation_id: UUID | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    owner_id: UUID
    scope: Literal["user", "project", "conversation"]
    repository_id: UUID | None
    conversation_id: UUID | None
    content: str
    source: Literal["explicit", "extracted"]
    importance: float
    access_count: int
    last_accessed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("scope", "source", mode="before")
    @classmethod
    def _coerce_enum(cls, v: object) -> object:
        return getattr(v, "value", v)
