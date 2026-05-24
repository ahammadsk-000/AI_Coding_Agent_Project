"""Phase 3: search + context endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.domain.search.context import pack_context
from app.domain.search.schemas import (
    ContextRequest,
    ContextResponse,
    SearchRequest,
    SearchResponse,
)
from app.domain.search.service import SearchService

search_router = APIRouter()
context_router = APIRouter()


@search_router.post("", response_model=SearchResponse)
async def search(
    payload: SearchRequest, user: CurrentUser, db: DbSession
) -> SearchResponse:
    """Hybrid (or pure dense / pure lexical) search across the caller's repos."""
    service = SearchService(db)
    hits, reranked, took_ms = await service.search(
        user,
        query=payload.query,
        repository_ids=payload.repository_ids,
        k=payload.k,
        mode=payload.mode,
        rerank=payload.rerank,
    )
    return SearchResponse(
        query=payload.query,
        mode=payload.mode,
        reranked=reranked,
        took_ms=took_ms,
        hits=hits,
    )


@context_router.post("/build", response_model=ContextResponse)
async def build_context(
    payload: ContextRequest, user: CurrentUser, db: DbSession
) -> ContextResponse:
    """Search + token-aware packing in a single round trip.

    Designed for the eventual Phase 4 chat layer: send the user's prompt, get
    back a prompt-ready bundle of file-grouped chunks under `max_tokens`.
    """
    service = SearchService(db)
    hits, _reranked, _took = await service.search(
        user,
        query=payload.query,
        repository_ids=payload.repository_ids,
        k=payload.k,
        mode="hybrid",
        rerank=payload.rerank,
    )
    files, total, truncated = pack_context(hits, max_tokens=payload.max_tokens)
    return ContextResponse(
        query=payload.query,
        total_tokens=total,
        max_tokens=payload.max_tokens,
        truncated=truncated,
        files=files,
    )
