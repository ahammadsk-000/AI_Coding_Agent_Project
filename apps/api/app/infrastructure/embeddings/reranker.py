"""Cross-encoder reranker for Phase 3 hybrid search.

Loads `sentence-transformers/ms-marco-MiniLM-L-6-v2` lazily on first use, caches
the model in process memory. Reranking improves precision-at-k significantly
over RRF alone — typical lift is 10-20 percentage points on code retrieval.

The model is ~22 MB. First call downloads it from HuggingFace (cached to the
HF_HOME volume already mounted in docker-compose for the worker; for the api
container, a process-local download is fine — it happens once per container).
"""
from __future__ import annotations

import threading
from typing import ClassVar

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("reranker")

# Default cross-encoder; small + fast + strong on text-retrieval reranking.
DEFAULT_RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    _instance: ClassVar["CrossEncoderReranker | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, model_name: str) -> None:
        # Lazy import keeps fastapi process startup fast and the cross-encoder
        # dependency optional for environments that don't need rerank.
        from sentence_transformers import CrossEncoder

        log.info("loading_reranker", model=model_name)
        self._model = CrossEncoder(model_name, max_length=512)
        self._model_name = model_name

    @classmethod
    def get(cls) -> "CrossEncoderReranker":
        if cls._instance is not None:
            return cls._instance
        with cls._lock:
            if cls._instance is None:
                model = getattr(
                    settings, "rerank_model", DEFAULT_RERANK_MODEL
                ) or DEFAULT_RERANK_MODEL
                cls._instance = cls(model)
        return cls._instance

    @property
    def model_name(self) -> str:
        return self._model_name

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Return one relevance score per (query, document) pair."""
        if not pairs:
            return []
        # sentence-transformers' CrossEncoder returns numpy array of shape (n,)
        out = self._model.predict(pairs, convert_to_numpy=True, show_progress_bar=False)
        return [float(x) for x in out.tolist()]


def get_reranker() -> CrossEncoderReranker:
    return CrossEncoderReranker.get()
