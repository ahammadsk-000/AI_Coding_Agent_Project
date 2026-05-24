"""Qdrant collection management + bulk upsert.

We keep one collection per repository, named `repo_<uuid_hex>`. This isolates
per-repo deletes and lets us scope searches without filtering by repo_id in
every query (still indexed via payload for cross-repo searches in Phase 3).
"""
from __future__ import annotations

import threading
from typing import Any, ClassVar
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("qdrant")


def collection_for(repo_id: UUID) -> str:
    return f"repo_{repo_id.hex}"


class QdrantService:
    _instance: ClassVar["QdrantService | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=60.0,
            prefer_grpc=False,
        )

    @classmethod
    def get(cls) -> "QdrantService":
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    # ---------- collection lifecycle ----------
    def ensure_collection(self, name: str, dimension: int) -> None:
        if self._client.collection_exists(name):
            return
        log.info("create_qdrant_collection", name=name, dim=dimension)
        self._client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
            hnsw_config=qm.HnswConfigDiff(m=16, ef_construct=128),
            optimizers_config=qm.OptimizersConfigDiff(default_segment_number=2),
        )
        # Payload indexes for common filters
        self._client.create_payload_index(name, "file_path", qm.PayloadSchemaType.KEYWORD)
        self._client.create_payload_index(name, "language", qm.PayloadSchemaType.KEYWORD)
        self._client.create_payload_index(name, "symbol_kind", qm.PayloadSchemaType.KEYWORD)

    def delete_collection(self, name: str) -> None:
        if self._client.collection_exists(name):
            self._client.delete_collection(name)

    # ---------- writes ----------
    def upsert_chunks(
        self,
        *,
        collection: str,
        points: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        """`points` is a list of (point_id, vector, payload)."""
        if not points:
            return
        batch = [
            qm.PointStruct(id=pid, vector=vec, payload=payload)
            for pid, vec, payload in points
        ]
        self._client.upsert(collection_name=collection, points=batch, wait=False)

    # ---------- reads (used in Phase 3) ----------
    def search(
        self,
        *,
        collection: str,
        vector: list[float],
        limit: int = 10,
        filters: qm.Filter | None = None,
    ) -> list[qm.ScoredPoint]:
        return self._client.search(
            collection_name=collection,
            query_vector=vector,
            limit=limit,
            query_filter=filters,
            with_payload=True,
        )

    # ---------- point deletion (Phase 7) ----------
    def delete_points(self, *, collection: str, point_ids: list[str]) -> None:
        if not point_ids:
            return
        if not self._client.collection_exists(collection):
            return
        self._client.delete(
            collection_name=collection,
            points_selector=qm.PointIdsList(points=point_ids),
            wait=False,
        )
