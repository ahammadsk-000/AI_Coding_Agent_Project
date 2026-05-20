"""Embedding provider interface."""
from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    """Synchronous embedding interface. Workers call this on their own thread."""

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text. Implementations batch internally."""
        ...
