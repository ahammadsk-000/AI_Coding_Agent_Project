"""DTOs for the Phase 3 search + context endpoints."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    repository_ids: list[UUID] = Field(default_factory=list, max_length=20)
    k: int = Field(default=10, ge=1, le=100)
    mode: Literal["hybrid", "dense", "lexical"] = "hybrid"
    rerank: bool = True


class SearchHit(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    chunk_id: UUID
    repository_id: UUID
    file_id: UUID
    file_path: str
    language: str | None
    start_line: int
    end_line: int
    token_count: int
    score: float           # final score after fusion (+ optional rerank)
    dense_score: float | None = None
    lexical_score: float | None = None
    rerank_score: float | None = None
    content: str


class SearchResponse(BaseModel):
    query: str
    mode: Literal["hybrid", "dense", "lexical"]
    reranked: bool
    took_ms: int
    hits: list[SearchHit]


class ContextRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2048)
    repository_ids: list[UUID] = Field(default_factory=list, max_length=20)
    max_tokens: int = Field(default=4096, ge=128, le=64_000)
    k: int = Field(default=30, ge=1, le=200)
    rerank: bool = True


class ContextFile(BaseModel):
    """Chunks grouped by file, in document order, suitable for prompt packing."""
    repository_id: UUID
    file_id: UUID
    file_path: str
    language: str | None
    chunks: list[SearchHit]


class ContextResponse(BaseModel):
    query: str
    total_tokens: int
    max_tokens: int
    truncated: bool
    files: list[ContextFile]
