"""Provider factory keyed by name + optional per-conversation model override."""
from __future__ import annotations

from app.core.config import settings
from app.infrastructure.llm.base import LLMProvider
from app.infrastructure.llm.ollama import OllamaProvider
from app.infrastructure.llm.openai_provider import OpenAIProvider


def get_llm_provider(
    *, provider: str | None = None, model: str | None = None
) -> LLMProvider:
    """Return a provider instance, optionally overriding the configured defaults."""
    name = (provider or settings.llm_provider).lower()
    if name == "openai":
        return OpenAIProvider(
            model=model or settings.openai_default_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
    # Default: Ollama. `vllm`/`anthropic` aren't wired yet — fall through to ollama.
    return OllamaProvider(
        model=model or settings.ollama_default_model,
        base_url=settings.ollama_base_url,
    )
