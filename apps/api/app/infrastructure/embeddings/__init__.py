"""Embedding provider abstraction + factory."""
from __future__ import annotations

from app.core.config import settings
from app.infrastructure.embeddings.base import EmbeddingProvider


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider singleton."""
    if settings.embedding_provider == "openai":
        from app.infrastructure.embeddings.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider.get()
    from app.infrastructure.embeddings.local import LocalEmbeddingProvider

    return LocalEmbeddingProvider.get()


__all__ = ["EmbeddingProvider", "get_embedding_provider"]
