"""LLM provider Protocol + shared types."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


@dataclass(slots=True)
class ChatMessage:
    """One message in a chat turn — OpenAI-compatible shape."""
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


@dataclass(slots=True)
class ToolDef:
    """A tool the LLM may call. JSONSchema in `parameters`."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCall:
    """Parsed tool call emitted by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class StreamChunk:
    """One incremental event from a streaming chat call.

    `text_delta` is non-None for text-token events. `tool_calls` is non-None when
    the provider has finalized its tool-call decisions (some providers emit them
    in a single shot at the end, others stream them).
    """
    text_delta: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None


@dataclass(slots=True)
class ChatResponse:
    """Final, non-streaming response."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


class LLMProvider(Protocol):
    """LLM provider interface.

    Implementations may stream over HTTP, run a local model, etc. The Protocol
    only constrains the shape of inputs/outputs, not transport.
    """

    @property
    def name(self) -> str: ...
    @property
    def model(self) -> str: ...

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDef] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Non-streaming chat call. Returns the final response."""
        ...

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDef] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat call. Yields chunks as they arrive."""
        ...
