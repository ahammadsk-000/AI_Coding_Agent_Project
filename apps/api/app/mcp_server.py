"""MCP server (FastMCP) exposing the AI Coding Agent's code tools.

This turns your indexed repositories into **Model Context Protocol** tools, so any
MCP host — Claude Desktop, an IDE, another agent — can search and read your code
through a standard protocol. It is a thin client over the REST API, so it works
against your live deployment (or a local one).

It is intentionally NOT part of the web/worker runtime and is not imported by the
app — you run it on demand as a local process (stdio transport).

Run it:
    pip install fastmcp httpx
    export ACA_API_URL=https://your-api.onrender.com   # or http://localhost:8000
    export ACA_EMAIL=you@example.com
    export ACA_PASSWORD=your-password
    python -m app.mcp_server

Then register it with an MCP host (see docs/MCP.md for a Claude Desktop config).
"""
from __future__ import annotations

import os
from typing import Any

import httpx

try:
    from fastmcp import FastMCP
except ImportError as e:  # pragma: no cover - only hit when the dep is missing
    raise SystemExit(
        "fastmcp is not installed. Run: pip install fastmcp httpx"
    ) from e

API_URL = os.getenv("ACA_API_URL", "http://localhost:8000").rstrip("/")
EMAIL = os.getenv("ACA_EMAIL", "")
PASSWORD = os.getenv("ACA_PASSWORD", "")

mcp = FastMCP("AI Coding Agent")

_token: str | None = None


async def _auth(client: httpx.AsyncClient) -> str:
    """Log in once and cache the access token for the process lifetime."""
    global _token
    if _token:
        return _token
    if not EMAIL or not PASSWORD:
        raise RuntimeError("Set ACA_EMAIL and ACA_PASSWORD environment variables.")
    resp = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )
    resp.raise_for_status()
    _token = resp.json()["tokens"]["access_token"]
    return _token


async def _get(client: httpx.AsyncClient, path: str) -> Any:
    r = await client.get(path, headers={"authorization": f"Bearer {await _auth(client)}"})
    r.raise_for_status()
    return r.json()


@mcp.tool
async def list_repositories() -> str:
    """List the user's ingested repositories with their name and status."""
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        repos = await _get(client, "/api/v1/repositories")
    if not repos:
        return "No repositories ingested yet."
    return "\n".join(f"- {r['name']} ({r['status']})" for r in repos)


@mcp.tool
async def search_code(query: str, k: int = 5) -> str:
    """Search the user's indexed code with hybrid (semantic + keyword) retrieval.

    Args:
        query: What to look for (natural language or keywords).
        k: How many results to return (1-20).
    """
    k = max(1, min(int(k), 20))
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        r = await client.post(
            "/api/v1/search",
            headers={"authorization": f"Bearer {await _auth(client)}"},
            json={
                "query": query,
                "k": k,
                "mode": "hybrid",
                "rerank": True,
                "repository_ids": [],
            },
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
    if not hits:
        return "No matches found."
    parts = [
        f"### {h['file_path']}:{h['start_line']}-{h['end_line']}  (score {h['score']:.3f})\n"
        f"{h['content']}"
        for h in hits
    ]
    return "\n\n".join(parts)


@mcp.tool
async def read_file(repository_name: str, file_path: str) -> str:
    """Read a file's full content from a repository, by repo name and file path."""
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as client:
        repos = await _get(client, "/api/v1/repositories")
        repo = next(
            (r for r in repos if r["name"].lower() == repository_name.lower()), None
        )
        if repo is None:
            return f"Repository '{repository_name}' not found."
        files = await _get(client, f"/api/v1/repositories/{repo['id']}/files")
        target = next(
            (
                f
                for f in files
                if f["path"].lower() == file_path.lower()
                or f["path"].split("/")[-1].lower() == file_path.lower()
            ),
            None,
        )
        if target is None:
            return f"File '{file_path}' not found in '{repository_name}'."
        chunks = await _get(
            client, f"/api/v1/repositories/{repo['id']}/files/{target['id']}/chunks"
        )
    return "\n".join(c["content"] for c in chunks) or "(empty file)"


if __name__ == "__main__":
    mcp.run()
