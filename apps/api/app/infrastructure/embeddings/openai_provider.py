"""OpenAI-compatible embedding adapter.

Works against the OpenAI API and any compatible server (Azure OpenAI, vLLM,
text-embeddings-inference, etc.) by switching `OPENAI_BASE_URL`.
"""
from __future__ import annotations

import threading
import time
from typing import ClassVar

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("embeddings.openai")

# Known embedding dimensions across OpenAI-compatible providers. Anything not
# listed here can be set explicitly via EMBEDDING_DIM.
_MODEL_DIMS = {
    # OpenAI
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    # Jina (free tier, OpenAI-compatible, no credit card)
    "jina-embeddings-v2-small-en": 512,
    "jina-embeddings-v2-base-en": 768,
    "jina-embeddings-v3": 1024,
    # Google Gemini (OpenAI-compatible endpoint)
    "text-embedding-004": 768,
}


class OpenAIEmbeddingProvider:
    _instance: ClassVar["OpenAIEmbeddingProvider | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        # Prefer embedding-specific credentials so chat (e.g. Groq) and
        # embeddings (e.g. OpenAI) can use different providers; fall back to the
        # shared openai_* settings.
        api_key = settings.embedding_api_key or settings.openai_api_key
        base_url = settings.embedding_base_url or settings.openai_base_url
        if not api_key:
            raise RuntimeError(
                "EMBEDDING_API_KEY (or OPENAI_API_KEY) is required when "
                "EMBEDDING_PROVIDER=openai"
            )
        self._model_name = settings.embedding_model
        self._dimension = settings.embedding_dim or _MODEL_DIMS.get(self._model_name, 1536)
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
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
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):
            out.extend(self._embed_batch(texts[i : i + 256]))
        return out

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        """Embed one batch, retrying with backoff on rate limits (429) / 5xx.

        Free embedding tiers (e.g. Jina) impose per-minute limits; backing off
        and retrying lets a large ingest ride through them instead of failing.
        """
        delay = 2.0
        last: httpx.Response | None = None
        for attempt in range(6):
            resp = self._client.post(
                "/embeddings",
                json={"model": self._model_name, "input": batch},
            )
            last = resp
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("retry-after")
                try:
                    wait = float(retry_after) if retry_after else delay
                except ValueError:
                    wait = delay
                wait = min(wait, 30.0)
                log.warning(
                    "embed_rate_limited", status=resp.status_code,
                    attempt=attempt + 1, wait_s=wait,
                )
                time.sleep(wait)
                delay = min(delay * 2, 30.0)
                continue
            resp.raise_for_status()
            return [item["embedding"] for item in resp.json()["data"]]
        # Retries exhausted — surface the last error.
        if last is not None:
            last.raise_for_status()
        return []
