"""Tools the chat agent may call.

These are READ-ONLY tools that operate on data already in Postgres / Qdrant —
no shell exec, no filesystem writes. The full sandbox + edit toolset arrives in
Phase 5+.

Each tool has:
- a JSON-Schema definition (so the LLM knows when/how to call it)
- an async handler that takes the user + parsed args + a session and returns
  a small JSON-serializable result + a short summary string for the UI

The handlers are kept small so the LLM stays in control of the agent loop.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.models import Repository, RepositoryFile
from app.domain.repositories.repository import FileRepo, RepositoryRepo
from app.domain.search.service import SearchService
from app.domain.users.models import User
from app.infrastructure.llm.base import ToolDef


# ---------- tool definitions (passed to the LLM) ----------

TOOL_DEFS: list[ToolDef] = [
    ToolDef(
        name="search_code",
        description=(
            "Search across the user's ingested repositories using hybrid retrieval "
            "(semantic vector + keyword). Returns the most relevant code chunks "
            "with file paths and line ranges. Use this to find where a concept "
            "or symbol lives before reading files."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language or keyword query.",
                },
                "k": {
                    # Accept integer OR string: some models (e.g. Llama via Groq)
                    # emit numeric tool args as strings, and Groq strictly
                    # validates tool calls against this schema. The handler
                    # coerces to int. A single "integer" type would make Groq
                    # reject the whole completion when the model sends "5".
                    "type": ["integer", "string"],
                    "description": "Number of results to return (default 5, max 20).",
                    "default": 5,
                },
                "repository_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of repo IDs to scope the search to. "
                        "Empty / omitted means search all of the user's repos."
                    ),
                    "default": [],
                },
            },
            "required": ["query"],
        },
    ),
    ToolDef(
        name="read_file",
        description=(
            "Read the full content of one file inside a repository. Identify "
            "the repository by its human name (e.g. 'test_repo') and the file "
            "by its path relative to the repo root (e.g. 'bluestyle.css' or "
            "'src/main.py'). Use this when the user asks to see, show, or "
            "explain a specific file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "repository_name": {
                    "type": "string",
                    "description": (
                        "Human name of the repository (e.g. 'test_repo'). "
                        "If unsure, you may also pass the repository UUID."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "File path relative to the repo root, e.g. 'bluestyle.css'."
                    ),
                },
            },
            "required": ["repository_name", "file_path"],
        },
    ),
    ToolDef(
        name="list_files",
        description=(
            "List the files in a repository so the agent can pick one to read."
        ),
        parameters={
            "type": "object",
            "properties": {
                "repository_name": {
                    "type": "string",
                    "description": (
                        "Human name of the repository (e.g. 'test_repo'). "
                        "The repository UUID is also accepted."
                    ),
                },
            },
            "required": ["repository_name"],
        },
    ),
    ToolDef(
        name="web_search",
        description=(
            "Search the public web for up-to-date information BEYOND the user's "
            "ingested repositories — e.g. library documentation, recent API "
            "changes, best practices, or how the user's code compares to the "
            "latest version of a framework. Returns a few results with title, "
            "URL, and snippet. Use ONLY when the answer isn't in the user's code "
            "and genuinely needs external or current knowledge."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search the web for.",
                },
                "max_results": {
                    "type": ["integer", "string"],
                    "description": "How many results to return (default 5, max 8).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    ),
]


# ---------- helpers ----------

def _as_uuid(value: str) -> UUID | None:
    try:
        return UUID(str(value))
    except Exception:
        return None


async def _resolve_repo(
    user: User, name_or_id: str, session: AsyncSession
) -> Repository | None:
    """Look up a repository owned by `user` by UUID first, then by exact name.

    Falls back to a case-insensitive name match so the LLM can pass
    'test_repo', 'TEST_REPO', or the UUID — all work.
    """
    s = (name_or_id or "").strip()
    if not s:
        return None
    repos = RepositoryRepo(session)
    maybe_uuid = _as_uuid(s)
    if maybe_uuid is not None:
        repo = await repos.get_for_owner(maybe_uuid, user.id)
        if repo is not None:
            return repo
    # Try by name (exact, then case-insensitive)
    all_owned = await repos.list_for_owner(user.id)
    for r in all_owned:
        if r.name == s:
            return r
    lower = s.lower()
    for r in all_owned:
        if r.name.lower() == lower:
            return r
    return None


async def _resolve_file_by_path(
    repo: Repository, file_path: str, session: AsyncSession
) -> RepositoryFile | None:
    """Find a file by path within a repo. Exact match, then case-insensitive."""
    path = (file_path or "").strip().lstrip("/")
    if not path:
        return None
    stmt = select(RepositoryFile).where(
        RepositoryFile.repository_id == repo.id,
        RepositoryFile.path == path,
    )
    file = (await session.execute(stmt)).scalar_one_or_none()
    if file is not None:
        return file
    # Fallback: case-insensitive, in case the LLM mangled casing.
    stmt = select(RepositoryFile).where(RepositoryFile.repository_id == repo.id)
    rows = list((await session.execute(stmt)).scalars())
    lp = path.lower()
    for r in rows:
        if r.path.lower() == lp:
            return r
    # Last resort: basename match (e.g. 'bluestyle.css' matches 'styles/bluestyle.css')
    base = path.split("/")[-1].lower()
    for r in rows:
        if r.path.split("/")[-1].lower() == base:
            return r
    return None


# ---------- handlers ----------

async def _handle_search_code(
    user: User, args: dict[str, Any], session: AsyncSession
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}, "search failed: empty query", []
    try:
        k = int(args.get("k", 5) or 5)
    except (TypeError, ValueError):
        k = 5
    k = max(1, min(k, 20))

    raw_ids = args.get("repository_ids") or []
    repo_ids: list[UUID] = []
    for rid in raw_ids:
        u = _as_uuid(rid)
        if u is not None:
            repo_ids.append(u)

    service = SearchService(session)
    hits, _reranked, _took = await service.search(
        user,
        query=query,
        repository_ids=repo_ids,
        k=k,
        mode="hybrid",
        rerank=True,
    )
    result_rows = [
        {
            "repository_id": str(h.repository_id),
            "file_id": str(h.file_id),
            "file_path": h.file_path,
            "language": h.language,
            "start_line": h.start_line,
            "end_line": h.end_line,
            "score": round(h.score, 4),
            "content": h.content,
        }
        for h in hits
    ]
    summary = f"search_code('{query[:60]}') → {len(result_rows)} hit(s)"
    citations = [
        {
            "repository_id": r["repository_id"],
            "file_id": r["file_id"],
            "file_path": r["file_path"],
            "start_line": r["start_line"],
            "end_line": r["end_line"],
        }
        for r in result_rows
    ]
    return {"hits": result_rows}, summary, citations


async def _handle_read_file(
    user: User, args: dict[str, Any], session: AsyncSession
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    # Accept both new (repository_name + file_path) and legacy (repository_id +
    # file_id) parameter names, so older agent prompts / cached tool schemas
    # don't suddenly break.
    repo_ref = str(args.get("repository_name") or args.get("repository_id") or "").strip()
    path_ref = str(args.get("file_path") or "").strip()
    legacy_file_id = _as_uuid(str(args.get("file_id") or ""))

    if not repo_ref:
        return (
            {"error": "repository_name is required"},
            "read_file failed: missing repository_name",
            [],
        )

    repo = await _resolve_repo(user, repo_ref, session)
    if repo is None:
        return (
            {
                "error": (
                    f"repository '{repo_ref}' not found among the user's "
                    "ingested repos"
                )
            },
            f"read_file failed: repo '{repo_ref}' not found",
            [],
        )

    files = FileRepo(session)
    file: RepositoryFile | None = None
    if path_ref:
        file = await _resolve_file_by_path(repo, path_ref, session)
    elif legacy_file_id is not None:
        # Legacy callers passed UUIDs; still honor them.
        file = await files.get_file(legacy_file_id)
        if file is not None and file.repository_id != repo.id:
            file = None

    if file is None:
        return (
            {
                "error": (
                    f"file '{path_ref}' not found in repository '{repo.name}'. "
                    "Call list_files to see what's available."
                )
            },
            f"read_file failed: '{path_ref}' not in {repo.name}",
            [],
        )

    # Re-assemble the full file content by concatenating chunks in line order.
    chunks = await files.list_chunks_for_file(file.id)
    content = "\n".join(c.content for c in chunks)
    summary = f"read_file({file.path}) → {file.lines} lines, {len(content)} chars"
    citation = [
        {
            "repository_id": str(repo.id),
            "file_id": str(file.id),
            "file_path": file.path,
            "start_line": 1,
            "end_line": file.lines,
        }
    ]
    return (
        {
            "repository_id": str(repo.id),
            "repository_name": repo.name,
            "file_id": str(file.id),
            "path": file.path,
            "language": file.language,
            "size_bytes": file.size_bytes,
            "lines": file.lines,
            "content": content,
        },
        summary,
        citation,
    )


async def _handle_list_files(
    user: User, args: dict[str, Any], session: AsyncSession
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    repo_ref = str(args.get("repository_name") or args.get("repository_id") or "").strip()
    if not repo_ref:
        return (
            {"error": "repository_name is required"},
            "list_files failed: missing repository_name",
            [],
        )
    repo = await _resolve_repo(user, repo_ref, session)
    if repo is None:
        return (
            {
                "error": (
                    f"repository '{repo_ref}' not found among the user's "
                    "ingested repos"
                )
            },
            f"list_files failed: repo '{repo_ref}' not found",
            [],
        )
    stmt = (
        select(RepositoryFile)
        .where(RepositoryFile.repository_id == repo.id)
        .order_by(RepositoryFile.path)
    )
    files_rows = list((await session.execute(stmt)).scalars())
    out = [
        {
            "path": f.path,
            "language": f.language,
            "size_bytes": f.size_bytes,
            "lines": f.lines,
        }
        for f in files_rows
    ]
    return (
        {"repository_name": repo.name, "files": out},
        f"list_files({repo.name}) → {len(out)} file(s)",
        [],
    )


async def _handle_web_search(
    user: User, args: dict[str, Any], session: AsyncSession
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required"}, "web_search failed: empty query", []
    try:
        n = int(args.get("max_results", 5) or 5)
    except (TypeError, ValueError):
        n = 5
    n = max(1, min(n, 8))

    from app.infrastructure.websearch import web_search

    results = await web_search(query, n)
    summary = f"web_search('{query[:60]}') → {len(results)} result(s)"
    return {"results": results}, summary, []


# ---------- dispatch ----------

_HANDLERS = {
    "search_code": _handle_search_code,
    "read_file": _handle_read_file,
    "list_files": _handle_list_files,
    "web_search": _handle_web_search,
}


async def execute_tool(
    name: str, args: dict[str, Any], *, user: User, session: AsyncSession
) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """Run a named tool. Returns (result_dict, short_summary, citations)."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}, f"unknown tool: {name}", []
    return await handler(user, args, session)
