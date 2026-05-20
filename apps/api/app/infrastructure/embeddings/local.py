"""Local embeddings via sentence-transformers.

Default model: BAAI/bge-small-en-v1.5 (384-dim, fast on CPU).
Loaded once per process, lazily, behind a singleton.
"""
from __future__ import annotations

import threading
from typing import ClassVar

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("embeddings.local")


class LocalEmbeddingProvider:
    _instance: ClassVar["LocalEmbeddingProvider | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model_name = settings.embedding_model
        log.info("loading_embedding_model", model=self._model_name)
        self._model = SentenceTransformer(self._model_name)
        # `get_sentence_embedding_dimension` is the public API for dim.
        self._dimension = int(self._model.get_sentence_embedding_dimension() or 384)
        self._batch_size = settings.ingest_embed_batch_size
        log.info("embedding_model_ready", model=self._model_name, dim=self._dimension)

    @classmethod
    def get(cls) -> "LocalEmbeddingProvider":
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [vec.tolist() for vec in vectors]
