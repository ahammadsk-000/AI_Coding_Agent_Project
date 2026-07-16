"""RAG evaluation harness (additive).

Runs the real retrieval + generation pipeline for a query, then scores it with
an **LLM-as-judge** on the standard RAG metrics (RAGAS-style):

- **Faithfulness** — are the answer's claims grounded in the retrieved context?
- **Answer relevance** — does the answer actually address the question?
- **Context precision** — is the retrieved context relevant to the question?

No ground-truth labels are required (so no context *recall*), which makes this a
reference-free eval that works on any indexed repo. Reuses `SearchService` and the
LLM provider; persists nothing.
"""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.search.context import pack_context
from app.domain.search.service import SearchService
from app.domain.users.models import User
from app.infrastructure.llm import ChatMessage, get_llm_provider

_ANSWER_SYS = (
    "You are a code assistant. Answer the question using ONLY the provided context. "
    "Be concise and specific. If the context does not contain the answer, say so."
)

_FAITHFULNESS_SYS = (
    "You are a strict RAG evaluator judging FAITHFULNESS. Given CONTEXT and an "
    "ANSWER, decide whether every factual claim in the answer is supported by the "
    "context. Reply with exactly one line 'SCORE: <0.0-1.0>' (1.0 = fully grounded, "
    "0.0 = hallucinated/unsupported) then one short sentence of justification."
)

_ANSWER_RELEVANCE_SYS = (
    "You are a RAG evaluator judging ANSWER RELEVANCE. Given a QUESTION and an "
    "ANSWER, decide how directly and completely the answer addresses the question. "
    "Reply with exactly one line 'SCORE: <0.0-1.0>' then one short sentence."
)

_CONTEXT_PRECISION_SYS = (
    "You are a RAG evaluator judging CONTEXT PRECISION. Given a QUESTION and the "
    "retrieved CONTEXT, decide how relevant the context is to answering the "
    "question (is it on-topic and useful, or padded with irrelevant chunks?). "
    "Reply with exactly one line 'SCORE: <0.0-1.0>' then one short sentence."
)


class RagEvalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.search = SearchService(session)

    async def evaluate(
        self,
        owner: User,
        query: str,
        repository_ids: list[UUID],
        model: str | None,
    ) -> dict[str, Any]:
        provider = get_llm_provider(model=model or None)

        # 1. Retrieve (the real hybrid pipeline).
        hits, reranked, took_ms = await self.search.search(
            owner,
            query=query,
            repository_ids=repository_ids,
            k=8,
            mode="hybrid",
            rerank=True,
        )
        files, _total, _trunc = pack_context(hits, max_tokens=1500)
        contexts: list[dict[str, Any]] = []
        blocks: list[str] = []
        for f in files:
            for c in f.chunks:
                blocks.append(f"## {f.file_path}:{c.start_line}-{c.end_line}\n{c.content}")
                contexts.append(
                    {
                        "file_path": f.file_path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "content": c.content,
                    }
                )
        context_text = "\n\n".join(blocks)

        if not contexts:
            return {
                "query": query,
                "answer": "",
                "contexts": [],
                "retrieved": 0,
                "reranked": reranked,
                "took_ms": took_ms,
                "metrics": {},
                "note": "No context was retrieved — nothing to evaluate. Ingest a repo or broaden the query.",
                "model": provider.model,
            }

        # 2. Generate the answer grounded in the retrieved context.
        answer = await self._answer(provider, query, context_text)

        # 3. Judge (LLM-as-judge) — three reference-free metrics.
        faithfulness = await self._judge(
            provider, _FAITHFULNESS_SYS, f"CONTEXT:\n{context_text}\n\nANSWER:\n{answer}"
        )
        answer_relevance = await self._judge(
            provider, _ANSWER_RELEVANCE_SYS, f"QUESTION:\n{query}\n\nANSWER:\n{answer}"
        )
        context_precision = await self._judge(
            provider, _CONTEXT_PRECISION_SYS, f"QUESTION:\n{query}\n\nCONTEXT:\n{context_text}"
        )
        metrics = {
            "faithfulness": faithfulness,
            "answer_relevance": answer_relevance,
            "context_precision": context_precision,
        }
        overall = round(
            sum(m["score"] for m in metrics.values()) / len(metrics), 3
        )

        return {
            "query": query,
            "answer": answer,
            "contexts": contexts,
            "retrieved": len(contexts),
            "reranked": reranked,
            "took_ms": took_ms,
            "metrics": metrics,
            "overall": overall,
            "model": provider.model,
        }

    async def _answer(self, provider: Any, query: str, context_text: str) -> str:
        try:
            resp = await provider.chat(
                [
                    ChatMessage(role="system", content=_ANSWER_SYS),
                    ChatMessage(
                        role="user",
                        content=f"Context:\n{context_text}\n\nQuestion: {query}",
                    ),
                ],
                temperature=0.2,
                max_tokens=600,
            )
            return resp.content.strip()
        except Exception as e:  # noqa: BLE001
            return f"(answer generation failed: {type(e).__name__}: {e})"

    async def _judge(self, provider: Any, system: str, user: str) -> dict[str, Any]:
        try:
            resp = await provider.chat(
                [
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ],
                temperature=0.0,
                max_tokens=200,
            )
            text = resp.content.strip()
            return {"score": _parse_score(text), "reason": _strip_score_line(text)}
        except Exception as e:  # noqa: BLE001
            return {"score": 0.0, "reason": f"(judge failed: {type(e).__name__}: {e})"}


def _parse_score(text: str) -> float:
    m = re.search(r"score\s*[:=]?\s*(\d(?:\.\d+)?)", text, re.IGNORECASE)
    if not m:
        return 0.0
    try:
        return max(0.0, min(1.0, round(float(m.group(1)), 3)))
    except ValueError:
        return 0.0


def _strip_score_line(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not re.match(r"\s*score\s*[:=]", ln, re.IGNORECASE)]
    return "\n".join(lines).strip() or text
