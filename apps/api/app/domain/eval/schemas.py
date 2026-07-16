"""Schemas for the RAG evaluation endpoint."""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class RagEvalRequest(BaseModel):
    query: str = Field(min_length=1)
    repository_ids: list[UUID] = Field(default_factory=list)
    model: str | None = None
