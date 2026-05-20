"""OpenAI-compatible embedding adapter.

Works against the OpenAI API and any compatible server (Azure OpenAI, vLLM,
text-embeddings-inference, etc.) by switching `OPENAI_BASE_URL`.
"""
from __future__ import annotations

import threading
from typing import ClassVar

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("embeddings.openai")

# Common defaults; can be overridden by model-specific dim probes if needed.
_MODEL_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider:
    _instance: ClassVar["OpenAIEmbeddingProvider | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai"
            )
        self._model_name = settings.embedding_model
        self._dimension = _MODEL_DIMS.get(self._model_name, 1536)
        self._client = httpx.Client(
            base_url=settings.openai_base_url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            timeout=60.0,
        )

    @classmethod
    def get(cls) -> "OpenAIEmbeddingProvider":
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
        # OpenAI supports batching natively; cap at 1k per request.
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):
            batch = texts[i : i + 256]
            resp = self._client.post(
                "/embeddings",
                json={"model": self._model_name, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            out.extend(item["embedding"] for item in data)
        return out
