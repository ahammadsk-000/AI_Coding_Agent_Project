"""Minimal web search (additive, best-effort).

Provider selection:
- If TAVILY_API_KEY is set in the environment, use Tavily (reliable, ranked).
- Otherwise fall back to DuckDuckGo's keyless Instant Answer API.

Always degrades gracefully: any failure returns an empty list rather than
raising, so the chat agent's tool call never crashes a conversation.
"""
from __future__ import annotations

import os

import httpx

_TIMEOUT = 15.0


async def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    n = max(1, min(int(max_results or 5), 8))
    key = os.getenv("TAVILY_API_KEY", "").strip()
    try:
        if key:
            return await _tavily(q, n, key)
        return await _duckduckgo(q, n)
    except Exception:  # noqa: BLE001 — best-effort; never break the agent loop
        return []


async def _tavily(query: str, n: int, key: str) -> list[dict[str, str]]:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": key,
                "query": query,
                "max_results": n,
                "search_depth": "basic",
                "include_answer": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
    out: list[dict[str, str]] = []
    for r in (data.get("results") or [])[:n]:
        out.append(
            {
                "title": str(r.get("title", ""))[:200],
                "url": str(r.get("url", "")),
                "snippet": str(r.get("content", ""))[:500],
            }
        )
    return out


async def _duckduckgo(query: str, n: int) -> list[dict[str, str]]:
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, headers={"User-Agent": "Mozilla/5.0 (AI-Coding-Agent)"}
    ) as client:
        resp = await client.get(
            "https://api.duckduckgo.com/",
            params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "no_redirect": "1",
                "skip_disambig": "1",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    out: list[dict[str, str]] = []
    abstract = str(data.get("AbstractText") or "").strip()
    if abstract:
        out.append(
            {
                "title": str(data.get("Heading") or query)[:200],
                "url": str(data.get("AbstractURL") or ""),
                "snippet": abstract[:500],
            }
        )
    for topic in data.get("RelatedTopics") or []:
        if len(out) >= n:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            out.append(
                {
                    "title": str(topic.get("Text"))[:120],
                    "url": str(topic.get("FirstURL") or ""),
                    "snippet": str(topic.get("Text"))[:500],
                }
            )
    return out[:n]
