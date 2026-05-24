"""LLM provider abstraction (Phase 4).

Two providers are supported out of the box:
- `ollama`: local OSS models via the Ollama HTTP API (default, no API key).
- `openai`: OpenAI-compatible chat completions (works with OpenAI proper, vLLM
  servers, LMStudio, and other compatible backends — controlled by base_url).

Provider selection is driven by `settings.llm_provider`. Per-conversation
overrides are stored on the Conversation row.
"""
from app.infrastructure.llm.base import (
    ChatMessage,
    ChatResponse,
    LLMProvider,
    StreamChunk,
    ToolCall,
    ToolDef,
)
from app.infrastructure.llm.factory import get_llm_provider

__all__ = [
    "ChatMessage",
    "ChatResponse",
    "LLMProvider",
    "StreamChunk",
    "ToolCall",
    "ToolDef",
    "get_llm_provider",
]
