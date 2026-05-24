"""Phase 3 hybrid search service.

Pipeline per query
------------------
1. **Dense:** embed query → Qdrant kNN over each authorized repo collection.
2. **Sparse:** Postgres FTS via the `content_tsv` GIN index, ranked by ts_rank_cd.
3. **Fuse:** Reciprocal Rank Fusion (RRF, k=60) over the two ranked lists.
4. **Rerank (optional):** small cross-encoder over top-N candidates for precision.

The service only consumes information already in Postgres + Qdrant — no new
state is persisted. The result objects carry enough metadata (file path, lines,
content) for the UI to render without follow-up reads.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics as M
from app.core.exceptions import NotFoundError
from app.domain.repositories.models import RepositoryStatus
from app.domain.repositories.repository import RepositoryRepo
from app.domain.search.schemas import SearchHit
from app.domain.users.models import User
from app.infrastructure.embeddings import get_embedding_provider
from app.infrastructure.qdrant.client import QdrantService, collection_for

# Thresholds applied when filtering "padded" hits — chunks the dense retriever
# returned just because the corpus is small, not because they're actually
# relevant. Empirically tuned for BAAI/bge-small-en-v1.5 + ms-marco-MiniLM rerank.
_MIN_RERANK_SCORE = -2.0   # cross-encoder: <0 is usually irrelevant; -2 is lenient
_MIN_DENSE_ONLY_SCORE = 0.55  # BGE-small cosine: below ~0.5 is essentially noise


# ---------- internals ----------
@dataclass(slots=True)
class _ScoredChunk:
    chunk_id: UUID
    repository_id: UUID
    file_id: UUID
    file_path: str
    language: str | None
    start_line: int
    end_line: int
    token_count: int
    content: str
    dense_score: float | None = None
    lexical_score: float | None = None


def _rrf_fuse(
    rankings: list[list[_ScoredChunk]], k: int = 60
) -> list[tuple[_ScoredChunk, float]]:
    """Reciprocal Rank Fusion. Each ranking is an ordered list of chunks.

    score(c) = sum_over_rankings(1 / (k + rank(c)))
    The chunk's metadata is taken from whichever ranking saw it first.
    """
    scores: dict[UUID, float] = {}
    seen: dict[UUID, _ScoredChunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            if chunk.chunk_id not in seen:
                seen[chunk.chunk_id] = chunk
            else:
                # Carry forward any score the other ranking populated
                prev = seen[chunk.chunk_id]
                if prev.dense_score is None and chunk.dense_score is not None:
                    prev.dense_score = chunk.dense_score
                if prev.lexical_score is None and chunk.lexical_score is not None:
                    prev.lexical_score = chunk.lexical_score
    fused = sorted(
        ((seen[cid], score) for cid, score in scores.items()),
        key=lambda x: x[1],
        reverse=True,
    )
    return fused


# ---------- service ----------
class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repos = RepositoryRepo(session)
        self.qdrant = QdrantService.get()

    # -- public entrypoints --

    async def search(
        self,
        owner: User,
        *,
        query: str,
        repository_ids: list[UUID],
        k: int,
        mode: str,
        rerank: bool,
    ) -> tuple[list[SearchHit], bool, int]:
        """Run hybrid search and return (hits, reranked_flag, took_ms)."""
        started = time.perf_counter()

        repo_ids = await self._authorize_repos(owner, repository_ids)
        if not repo_ids:
            return [], False, int((time.perf_counter() - started) * 1000)

        # Fetch more than `k` from each side so RRF has material to work with;
        # the reranker (if on) consumes up to `rerank_pool` items.
        rerank_pool = min(max(k * 3, 30), 100)

        dense_task = (
            self._dense_search(repo_ids, query=query, limit=rerank_pool)
            if mode in ("hybrid", "dense")
            else asyncio.sleep(0, result=[])
        )
        lex_task = (
            self._lexical_search(repo_ids, query=query, limit=rerank_pool)
            if mode in ("hybrid", "lexical")
            else asyncio.sleep(0, result=[])
        )
        dense, lexical = await asyncio.gather(dense_task, lex_task)

        if mode == "dense":
            candidates: list[tuple[_ScoredChunk, float]] = [
                (c, c.dense_score or 0.0) for c in dense
            ]
        elif mode == "lexical":
            candidates = [(c, c.lexical_score or 0.0) for c in lexical]
        else:
            candidates = _rrf_fuse([dense, lexical])

        # Filter out orphan Qdrant points whose Postgres chunk row no longer
        # exists (left over from deleted/re-ingested repos). Hydration leaves
        # file_path == "" for these; they're not useful to a caller.
        candidates = [(c, s) for c, s in candidates if c.file_path]

        candidates = candidates[:rerank_pool]

        reranked_flag = False
        if rerank and len(candidates) > 1:
            try:
                reranked = self._rerank(query, [c for c, _ in candidates])
                candidates = [
                    (chunk, score) for chunk, score in zip(reranked["chunks"], reranked["scores"])
                ]
                reranked_flag = True
            except Exception:
                # rerank is best-effort; fall back to fused order silently
                reranked_flag = False

        # Drop "padded" hits — chunks the dense retriever surfaced just because
        # the corpus is small but aren't actually relevant to the query.
        candidates = self._filter_padding(
            candidates, mode=mode, reranked=reranked_flag
        )

        top = candidates[:k]
        hits = [
            SearchHit(
                chunk_id=c.chunk_id,
                repository_id=c.repository_id,
                file_id=c.file_id,
                file_path=c.file_path,
                language=c.language,
                start_line=c.start_line,
                end_line=c.end_line,
                token_count=c.token_count,
                score=float(score),
                dense_score=c.dense_score,
                lexical_score=c.lexical_score,
                rerank_score=float(score) if reranked_flag else None,
                content=c.content,
            )
            for c, score in top
        ]
        elapsed = time.perf_counter() - started
        took_ms = int(elapsed * 1000)
        M.search_requests_total.labels(mode, "true" if reranked_flag else "false").inc()
        M.search_duration_seconds.labels(mode).observe(elapsed)
        return hits, reranked_flag, took_ms

    # -- private helpers --

    @staticmethod
    def _filter_padding(
        candidates: list[tuple[_ScoredChunk, float]],
        *,
        mode: str,
        reranked: bool,
    ) -> list[tuple[_ScoredChunk, float]]:
        """Drop low-relevance hits surfaced by dense kNN on tiny corpora.

        Rules:
        - lexical-only mode: nothing to filter (FTS already matched query tokens).
        - reranked: drop anything below the cross-encoder relevance floor.
        - otherwise: keep chunks that appeared in lexical (real token match) OR
          have a dense score above the "actually similar" threshold.
        """
        if mode == "lexical":
            return candidates
        if reranked:
            return [(c, s) for c, s in candidates if s >= _MIN_RERANK_SCORE]
        return [
            (c, s)
            for c, s in candidates
            if c.lexical_score is not None
            or (c.dense_score is not None and c.dense_score >= _MIN_DENSE_ONLY_SCORE)
        ]

    async def _authorize_repos(
        self, owner: User, requested: list[UUID]
    ) -> list[UUID]:
        """Resolve which repo ids the caller may search.

        Empty `requested` means "all my ready repos". Otherwise we filter the
        requested set against ones the caller owns AND that are in `ready`
        state (an unfinished ingest has no Qdrant collection to query).
        """
        owned = await self.repos.list_for_owner(owner.id)
        owned_ready = {r.id: r for r in owned if r.status == RepositoryStatus.ready}
        if not requested:
            return list(owned_ready.keys())
        out: list[UUID] = []
        for rid in requested:
            if rid in owned_ready:
                out.append(rid)
        return out

    async def _dense_search(
        self, repo_ids: list[UUID], *, query: str, limit: int
    ) -> list[_ScoredChunk]:
        """Qdrant kNN per repo, merged. Runs in a thread (embedder + qdrant are sync)."""
        if not repo_ids:
            return []

        loop = asyncio.get_running_loop()

        def _embed_and_search() -> list[_ScoredChunk]:
            embedder = get_embedding_provider()
            vector = embedder.embed_texts([query])[0]
            results: list[_ScoredChunk] = []
            for rid in repo_ids:
                collection = collection_for(rid)
                try:
                    points = self.qdrant.search(
                        collection=collection, vector=vector, limit=limit
                    )
                except Exception:
                    continue
                for p in points:
                    payload = p.payload or {}
                    chunk_id_str = payload.get("chunk_id")
                    if not chunk_id_str:
                        continue
                    results.append(
                        _ScoredChunk(
                            chunk_id=UUID(chunk_id_str),
                            repository_id=rid,
                            file_id=UUID(payload["file_id"]),
                            file_path="",                 # filled in after DB hydrate
                            language=payload.get("language"),
                            start_line=int(payload.get("start_line", 0)),
                            end_line=int(payload.get("end_line", 0)),
                            token_count=0,                # filled in after DB hydrate
                            content="",                   # filled in after DB hydrate
                            dense_score=float(p.score),
                        )
                    )
            # Sort merged results by dense score descending, take the first `limit`
            results.sort(key=lambda c: c.dense_score or 0.0, reverse=True)
            return results[:limit]

        chunks = await loop.run_in_executor(None, _embed_and_search)
        await self._hydrate(chunks)
        return chunks

    async def _lexical_search(
        self, repo_ids: list[UUID], *, query: str, limit: int
    ) -> list[_ScoredChunk]:
        """Postgres FTS via ts_rank_cd over the content_tsv index."""
        if not repo_ids:
            return []
        # plainto_tsquery is the most forgiving parser; treats input as a phrase
        # of normalized tokens. It avoids the syntax-error footguns of to_tsquery
        # when callers pass raw user text.
        stmt = text(
            """
            SELECT
                cc.id            AS chunk_id,
                cc.repository_id AS repository_id,
                cc.file_id       AS file_id,
                rf.path          AS file_path,
                cc.language      AS language,
                cc.start_line    AS start_line,
                cc.end_line      AS end_line,
                cc.token_count   AS token_count,
                cc.content       AS content,
                ts_rank_cd(cc.content_tsv, plainto_tsquery('english', :q)) AS rank
            FROM code_chunks cc
            JOIN repository_files rf ON rf.id = cc.file_id
            WHERE cc.repository_id IN :repo_ids
              AND cc.content_tsv @@ plainto_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT :limit
            """
        ).bindparams(bindparam("repo_ids", expanding=True))
        rows = (
            await self.session.execute(
                stmt,
                {
                    "q": query,
                    "repo_ids": [str(r) for r in repo_ids],
                    "limit": limit,
                },
            )
        ).mappings().all()

        return [
            _ScoredChunk(
                chunk_id=row["chunk_id"],
                repository_id=row["repository_id"],
                file_id=row["file_id"],
                file_path=row["file_path"],
                language=row["language"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                token_count=row["token_count"],
                content=row["content"],
                lexical_score=float(row["rank"]),
            )
            for row in rows
        ]

    async def _hydrate(self, chunks: list[_ScoredChunk]) -> None:
        """Fill in path/content/token_count from Postgres for dense-only chunks."""
        missing = [c.chunk_id for c in chunks if not c.content]
        if not missing:
            return
        stmt = text(
            """
            SELECT cc.id, rf.path, cc.content, cc.token_count, cc.language
            FROM code_chunks cc
            JOIN repository_files rf ON rf.id = cc.file_id
            WHERE cc.id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))
        rows = (
            await self.session.execute(
                stmt, {"ids": [str(cid) for cid in missing]}
            )
        ).mappings().all()
        by_id: dict[UUID, dict[str, Any]] = {row["id"]: dict(row) for row in rows}
        for c in chunks:
            row = by_id.get(c.chunk_id)
            if not row:
                continue
            c.file_path = row["path"]
            c.content = row["content"]
            c.token_count = int(row["token_count"])
            if c.language is None:
                c.language = row["language"]

    def _rerank(self, query: str, chunks: list[_ScoredChunk]) -> dict[str, list]:
        """Cross-encoder rerank. Lazily imports + caches the model in memory."""
        from app.infrastructure.embeddings.reranker import get_reranker

        ranker = get_reranker()
        pairs = [(query, c.content) for c in chunks]
        scores = ranker.score(pairs)
        # Sort chunks by score desc
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
        return {
            "chunks": [c for c, _ in ranked],
            "scores": [float(s) for _, s in ranked],
        }
