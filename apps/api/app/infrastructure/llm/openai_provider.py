"""OpenAI-compatible provider.

Works with OpenAI proper or any OpenAI-compatible API (vLLM, LMStudio, etc.) by
varying `base_url` and `api_key`.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.infrastructure.llm.base import (
    ChatMessage,
    ChatResponse,
    StreamChunk,
    ToolCall,
    ToolDef,
)


def _to_openai_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        msg: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            msg["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            msg["tool_call_id"] = m.tool_call_id
        out.append(msg)
    return out


def _to_openai_tools(tools: list[ToolDef] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


class OpenAIProvider:
    def __init__(self, *, model: str, api_key: str | None, base_url: str) -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key or "missing", base_url=base_url)

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDef] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        oa_tools = _to_openai_tools(tools)
        if oa_tools:
            kwargs["tools"] = oa_tools

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        tcs: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            args_raw = tc.function.arguments or "{}"
            try:
                args = json.loads(args_raw)
            except json.JSONDecodeError:
                args = {}
            tcs.append(
                ToolCall(
                    id=tc.id or f"call_{uuid.uuid4().hex[:12]}",
                    name=tc.function.name or "",
                    arguments=args,
                )
            )
        return ChatResponse(
            content=msg.content or "",
            tool_calls=tcs,
            finish_reason=choice.finish_reason or "stop",
        )

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDef] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": _to_openai_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        oa_tools = _to_openai_tools(tools)
        if oa_tools:
            kwargs["tools"] = oa_tools

        # Accumulate tool-call argument deltas across chunks; OpenAI streams
        # them piecewise as JSON fragments.
        tc_acc: dict[int, dict[str, Any]] = {}

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            text_delta = delta.content or None

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = tc_acc.setdefault(
                        tc.index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments

            if text_delta:
                yield StreamChunk(text_delta=text_delta)

            if choice.finish_reason:
                finalized: list[ToolCall] = []
                for slot in tc_acc.values():
                    args_raw = slot["arguments"] or "{}"
                    try:
                        args = json.loads(args_raw)
                    except json.JSONDecodeError:
                        args = {}
                    finalized.append(
                        ToolCall(
                            id=slot["id"] or f"call_{uuid.uuid4().hex[:12]}",
                            name=slot["name"],
                            arguments=args,
                        )
                    )
                yield StreamChunk(
                    text_delta=None,
                    tool_calls=finalized or None,
                    finish_reason=choice.finish_reason,
                )
                return


def get_openai_provider() -> OpenAIProvider:
    return OpenAIProvider(
        model=settings.openai_default_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )
