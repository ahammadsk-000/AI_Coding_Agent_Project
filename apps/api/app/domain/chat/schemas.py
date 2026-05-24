"""Pydantic DTOs for chat."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    title: str = Field(default="New chat", max_length=255)
    repository_ids: list[UUID] = Field(default_factory=list, max_length=20)
    # Optional overrides — empty means "use server defaults from settings".
    llm_provider: Literal["ollama", "openai"] | None = None
    llm_model: str | None = Field(default=None, max_length=128)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    owner_id: UUID
    title: str
    repository_ids: list[UUID]
    llm_provider: str
    llm_model: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: str | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    conversation_id: UUID
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    citations: list[dict[str, Any]] | None = None
    token_count: int
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def _coerce_role(cls, v: object) -> object:
        # SQLAlchemy hands us a MessageRole enum; pydantic's Literal validator
        # wants the plain string. Unwrap.
        return getattr(v, "value", v)


class MessageSend(BaseModel):
    """User-supplied message body. Sent over WS for streaming or REST for one-shot."""
    content: str = Field(min_length=1, max_length=16_384)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationDetail(BaseModel):
    conversation: ConversationRead
    messages: list[MessageRead]


# ---- WebSocket protocol ----
# All events the server pushes share the same shape: {type, ...}. Client only
# needs to render `type=="token"` deltas; everything else is informational.
class WsToken(BaseModel):
    type: Literal["token"] = "token"
    delta: str


class WsToolCallStart(BaseModel):
    type: Literal["tool_call_start"] = "tool_call_start"
    name: str
    arguments: dict[str, Any]
    call_id: str


class WsToolCallResult(BaseModel):
    type: Literal["tool_call_result"] = "tool_call_result"
    call_id: str
    summary: str   # short human-readable summary; full content saved to DB


class WsCitations(BaseModel):
    type: Literal["citations"] = "citations"
    citations: list[dict[str, Any]]


class WsDone(BaseModel):
    type: Literal["done"] = "done"
    message_id: UUID


class WsError(BaseModel):
    type: Literal["error"] = "error"
    message: str
