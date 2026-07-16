"""RAG evaluation endpoint — runs retrieval + generation and scores it (LLM-as-judge)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.dependencies import CurrentUser, DbSession
from app.core.exceptions import ConflictError
from app.domain.eval.schemas import RagEvalRequest
from app.domain.eval.service import RagEvalService

router = APIRouter()


@router.post("/rag")
async def evaluate_rag(
    payload: RagEvalRequest, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    try:
        return await RagEvalService(db).evaluate(
            user, payload.query, payload.repository_ids, payload.model
        )
    except Exception as e:  # noqa: BLE001 — surface the real reason
        raise ConflictError(f"RAG eval failed: {type(e).__name__}: {e}") from e
