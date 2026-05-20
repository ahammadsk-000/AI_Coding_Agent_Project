"""Pydantic v2 DTOs for the repositories context."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RepositoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1, max_length=1024, description="git URL (https or ssh) or local path")
    source_type: Literal["git", "local", "github"] = "git"
    default_branch: str = Field(default="main", max_length=255)


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    owner_id: UUID
    name: str
    source_type: str
    url: str
    default_branch: str
    status: str
    last_indexed_at: datetime | None
    stats: dict | None
    qdrant_collection: str | None
    created_at: datetime
    updated_at: datetime


class IngestJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    repository_id: UUID
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    files_seen: int
    files_indexed: int
    chunks_indexed: int
    bytes_indexed: int
    celery_task_id: str | None
    created_at: datetime
    updated_at: datetime


class IngestEvent(BaseModel):
    """Server-sent event payload streamed to clients during ingest."""
    type: Literal["status", "progress", "log", "done", "error"]
    status: str | None = None
    files_seen: int | None = None
    files_indexed: int | None = None
    chunks_indexed: int | None = None
    bytes_indexed: int | None = None
    message: str | None = None
    timestamp: datetime
