"""Ollama provider.

Talks to a local Ollama instance via its native `/api/chat` endpoint. Supports
streaming (newline-delimited JSON) and tool calling (Ollama 0.3+ exposes
OpenAI-style `tools` and emits `message.tool_calls`).

Default endpoint comes from `settings.ollama_base_url`. From inside Docker on
Windows/Mac, that's `http://host.docker.internal:11434`; on Linux you'd point
to the host IP or run Ollama in its own container.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.llm.base import (
    ChatMessage,
    ChatResponse,
    StreamChunk,
    ToolCall,
    ToolDef,
)

log = get_logger("ollama")

# Heuristic: when Ollama rejects a request, retry once without `tools`.
# Different errors come from different model templates; matching on a broad set
# of keywords keeps the fallback resilient as Ollama tightens its validation.
_TOOL_REJECT_HINTS = ("tool", "function", "does not support")


def _looks_like_tool_rejection(body_text: str) -> bool:
    lo = body_text.lower()
    return any(hint in lo for hint in _TOOL_REJECT_HINTS)


def _to_ollama_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        msg: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.tool_calls:
            msg["tool_calls"] = _normalize_tool_calls_for_ollama(m.tool_calls)
        out.append(msg)
    return out


def _normalize_tool_calls_for_ollama(
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Coerce stored tool_calls to the shape Ollama's /api/chat parser accepts.

    We store tool_calls in the OpenAI shape (with `arguments` as a JSON string)
    because that's what OpenAI streams back. Ollama wants `arguments` as a real
    JSON object — if we send the string verbatim, its parser emits
    `Value looks like object, but can't find closing '}' symbol`.
    """
    out: list[dict[str, Any]] = []
    for tc in tool_calls:
        fn = tc.get("function", {}) or {}
        args = fn.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args = {}
        out.append(
            {
                "function": {
                    "name": fn.get("name", ""),
                    "arguments": args,
                }
            }
        )
    return out


def _to_ollama_tools(tools: list[ToolDef] | None) -> list[dict[str, Any]] | None:
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


def _parse_tool_calls(raw: list[dict[str, Any]] | None) -> list[ToolCall]:
    out: list[ToolCall] = []
    for tc in raw or []:
        fn = tc.get("function", {})
        args = fn.get("arguments", {})
        # Ollama returns arguments already as a dict; OpenAI returns it as a JSON string.
        if isinstance(args, str):
            try:
                args = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args = {}
        out.append(
            ToolCall(
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=fn.get("name", ""),
                arguments=args,
            )
        )
    return out


class OllamaProvider:
    def __init__(self, *, model: str, base_url: str) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    @property
    def name(self) -> str:
        return "ollama"

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
        body: dict[str, Any] = {
            "model": self._model,
            "messages": _to_ollama_messages(messages),
            "stream": False,
            # `keep_alive: 30m` keeps the model resident in GPU/RAM between calls.
            # Default 5m means the second message after a pause hits a 5-15s
            # cold-start reload.
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                # 4k context covers system prompt + RAG block + a few turns,
                # without paying the latency of the 8k/16k tail.
                "num_ctx": 4096,
            },
        }
        if max_tokens is not None:
            body["options"]["num_predict"] = max_tokens
        ollama_tools = _to_ollama_tools(tools)
        if ollama_tools:
            body["tools"] = ollama_tools

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
            data = await self._post_chat(client, body, allow_tool_fallback=True)
        msg = data.get("message", {}) or {}
        return ChatResponse(
            content=msg.get("content", ""),
            tool_calls=_parse_tool_calls(msg.get("tool_calls")),
            finish_reason=data.get("done_reason") or "stop",
        )

    async def _post_chat(
        self,
        client: httpx.AsyncClient,
        body: dict[str, Any],
        *,
        allow_tool_fallback: bool,
    ) -> dict[str, Any]:
        """POST /api/chat with body-aware error reporting + tool retry fallback."""
        resp = await client.post(f"{self._base_url}/api/chat", json=body)
        if resp.status_code >= 400:
            error_text = resp.text
            if (
                allow_tool_fallback
                and resp.status_code == 400
                and "tools" in body
                and _looks_like_tool_rejection(error_text)
            ):
                log.warning(
                    "ollama_tools_rejected_retrying_without",
                    model=body.get("model"),
                    error=error_text[:300],
                )
                body_no_tools = {k: v for k, v in body.items() if k != "tools"}
                resp = await client.post(
                    f"{self._base_url}/api/chat", json=body_no_tools
                )
            if resp.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"Ollama {resp.status_code}: {resp.text[:500]}",
                    request=resp.request,
                    response=resp,
                )
        return resp.json()

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDef] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": _to_ollama_messages(messages),
            "stream": True,
            "keep_alive": "30m",
            "options": {
                "temperature": temperature,
                "num_ctx": 4096,
            },
        }
        if max_tokens is not None:
            body["options"]["num_predict"] = max_tokens
        ollama_tools = _to_ollama_tools(tools)
        if ollama_tools:
            body["tools"] = ollama_tools

        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            async for chunk in self._stream_chat(
                client, body, allow_tool_fallback=True
            ):
                yield chunk

    async def _stream_chat(
        self,
        client: httpx.AsyncClient,
        body: dict[str, Any],
        *,
        allow_tool_fallback: bool,
    ) -> AsyncIterator[StreamChunk]:
        async with client.stream(
            "POST", f"{self._base_url}/api/chat", json=body
        ) as resp:
            if resp.status_code >= 400:
                error_text = (await resp.aread()).decode("utf-8", errors="replace")
                if (
                    allow_tool_fallback
                    and resp.status_code == 400
                    and "tools" in body
                    and _looks_like_tool_rejection(error_text)
                ):
                    log.warning(
                        "ollama_tools_rejected_retrying_without",
                        model=body.get("model"),
                        error=error_text[:300],
                    )
                    body_no_tools = {k: v for k, v in body.items() if k != "tools"}
                    async for c in self._stream_chat(
                        client, body_no_tools, allow_tool_fallback=False
                    ):
                        yield c
                    return
                raise httpx.HTTPStatusError(
                    f"Ollama {resp.status_code}: {error_text[:500]}",
                    request=resp.request,
                    response=resp,
                )
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = data.get("message", {}) or {}
                delta = msg.get("content") or None
                tcs = _parse_tool_calls(msg.get("tool_calls"))
                if delta or tcs:
                    yield StreamChunk(
                        text_delta=delta,
                        tool_calls=tcs or None,
                    )
                if data.get("done"):
                    yield StreamChunk(
                        text_delta=None,
                        finish_reason=data.get("done_reason") or "stop",
                    )
                    return


def get_ollama_provider() -> OllamaProvider:
    return OllamaProvider(
        model=settings.ollama_default_model,
        base_url=settings.ollama_base_url,
    )
