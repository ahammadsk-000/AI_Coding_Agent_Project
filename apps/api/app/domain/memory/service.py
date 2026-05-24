"""Memory service: store, recall, and forget durable facts.

Each memory's text is embedded and upserted into a single shared Qdrant
collection (`aca_memories`) with owner_id / scope / repository_id in the
payload, so recall can filter to the right owner (and optionally a repo) before
ranking by vector similarity. Postgres `memories` is the source of truth for
text + metadata.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from uuid import UUID

from qdrant_client.http import models as qm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics as M
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.domain.memory.models import Memory, MemoryScope, MemorySource
from app.domain.memory.repository import MemoryRepo
from app.domain.users.models import User
from app.infrastructure.embeddings import get_embedding_provider
from app.infrastructure.qdrant.client import QdrantService

log = get_logger("memory")

MEMORY_COLLECTION = "aca_memories"


@dataclass(slots=True)
class RecalledMemory:
    id: UUID
    content: str
    scope: str
    score: float


class MemoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MemoryRepo(session)
        self.qdrant = QdrantService.get()

    # ---------- write ----------

    async def remember(
        self,
        owner: User,
        *,
        content: str,
        scope: MemoryScope = MemoryScope.user,
        repository_id: UUID | None = None,
        conversation_id: UUID | None = None,
        source: MemorySource = MemorySource.explicit,
        importance: float = 0.5,
    ) -> Memory:
        content = content.strip()
        # Dedupe exact repeats.
        existing = await self.repo.find_duplicate(owner.id, content)
        if existing is not None:
            return existing

        mem = Memory(
            id=uuid.uuid4(),
            owner_id=owner.id,
            scope=scope,
            repository_id=repository_id,
            conversation_id=conversation_id,
            content=content,
            source=source,
            importance=importance,
            vector_id=None,
        )
        mem.vector_id = mem.id.hex
        await self.repo.add(mem)

        # Embed + upsert into Qdrant (sync libs → run in a thread).
        await self._index(mem)
        M.memory_writes_total.labels(mem.scope.value, mem.source.value).inc()
        return mem

    async def _index(self, mem: Memory) -> None:
        loop = asyncio.get_running_loop()

        def _embed_and_upsert() -> None:
            embedder = get_embedding_provider()
            self.qdrant.ensure_collection(MEMORY_COLLECTION, embedder.dimension)
            vec = embedder.embed_texts([mem.content])[0]
            payload = {
                "memory_id": str(mem.id),
                "owner_id": str(mem.owner_id),
                "scope": mem.scope.value,
                "repository_id": str(mem.repository_id) if mem.repository_id else None,
            }
            self.qdrant.upsert_chunks(
                collection=MEMORY_COLLECTION,
                points=[(mem.vector_id or mem.id.hex, vec, payload)],
            )

        await loop.run_in_executor(None, _embed_and_upsert)

    # ---------- recall ----------

    async def recall(
        self,
        owner: User,
        *,
        query: str,
        repository_ids: list[UUID] | None = None,
        k: int = 5,
    ) -> list[RecalledMemory]:
        """Vector-search this owner's memories for ones relevant to `query`."""
        if not query.strip():
            return []
        loop = asyncio.get_running_loop()

        # Owner filter is mandatory; repo filter is additive (user-scoped
        # memories always apply, project-scoped only for the named repos).
        repo_strs = [str(r) for r in (repository_ids or [])]

        def _search() -> list[tuple[str, float]]:
            embedder = get_embedding_provider()
            if not self.qdrant._client.collection_exists(MEMORY_COLLECTION):  # noqa: SLF001
                return []
            vec = embedder.embed_texts([query])[0]
            owner_filter = qm.Filter(
                must=[
                    qm.FieldCondition(
                        key="owner_id",
                        match=qm.MatchValue(value=str(owner.id)),
                    )
                ]
            )
            points = self.qdrant.search(
                collection=MEMORY_COLLECTION,
                vector=vec,
                limit=k * 2,
                filters=owner_filter,
            )
            out: list[tuple[str, float]] = []
            for p in points:
                payload = p.payload or {}
                mid = payload.get("memory_id")
                if not mid:
                    continue
                scope = payload.get("scope")
                rid = payload.get("repository_id")
                # project-scoped memories only apply when their repo is in scope
                if scope == "project" and repo_strs and rid not in repo_strs:
                    continue
                out.append((mid, float(p.score)))
            return out

        scored = await loop.run_in_executor(None, _search)
        if not scored:
            return []

        ids = [UUID(mid) for mid, _ in scored]
        score_by_id = {mid: s for mid, s in scored}
        mems = await self.repo.get_many(ids)
        await self.repo.mark_accessed(ids)

        result = [
            RecalledMemory(
                id=m.id,
                content=m.content,
                scope=m.scope.value,
                score=score_by_id.get(str(m.id), 0.0),
            )
            for m in mems
        ]
        result.sort(key=lambda r: r.score, reverse=True)
        if result:
            M.memory_recalls_total.inc()
        return result[:k]

    # ---------- list / delete ----------

    async def list_memories(
        self, owner: User, scope: MemoryScope | None = None
    ) -> list[Memory]:
        return await self.repo.list_for_owner(owner.id, scope)

    async def forget(self, owner: User, memory_id: UUID) -> None:
        mem = await self.repo.get_for_owner(memory_id, owner.id)
        if mem is None:
            raise NotFoundError("Memory not found")
        vector_id = mem.vector_id or mem.id.hex
        await self.repo.delete(mem)
        # Best-effort vector cleanup.
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self.qdrant.delete_points(
                collection=MEMORY_COLLECTION, point_ids=[vector_id]
            ),
        )
