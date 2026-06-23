"""Automated repo audit (additive).

A fan-out reviewer: pick the top-N most substantial source files, and have an
LLM reviewer flag real issues (bugs, security, smells, perf) in each — streamed
file-by-file with severity. Token-heavy, so it is explicitly scoped by `depth`
and reuses the existing chunks (no re-clone).
"""
from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.repositories.repository import FileRepo
from app.domain.repositories.service import RepositoryService
from app.domain.users.models import User
from app.infrastructure.llm import ChatMessage, get_llm_provider

log = get_logger("audit")

_AUDIT_SYS = (
    "You are a senior code reviewer. Review the given source file for REAL, "
    "specific issues: bugs, security vulnerabilities, missing error handling, and "
    "notable code smells or performance problems. Return ONLY a JSON array; each "
    "item is an object with keys: severity ('high'|'medium'|'low'), category "
    "('bug'|'security'|'smell'|'perf'), line (integer or null), title (short), and "
    "detail (one or two sentences justified by the code). Report only genuine "
    "issues you can defend from the code shown. If the file looks clean, return []."
)

_MAX_FILE_CHARS = 12_000
_VALID_SEV = {"high", "medium", "low"}
_VALID_CAT = {"bug", "security", "smell", "perf"}


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.files = FileRepo(session)

    async def run_stream(
        self, owner: User, repo_id: UUID, depth: int, model: str | None
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        repo = await RepositoryService(self.session).get_mine(owner, repo_id)  # authz/404

        rows = await self.files.list_files_with_chunk_counts(repo.id)
        files = [f for f, _cnt in rows]
        # Prefer real source over tests; fall back to everything if that's all there is.
        source = [f for f in files if not _is_test_path(f.path)]
        pool = source or files
        pool.sort(key=lambda f: f.lines, reverse=True)
        selected = pool[:depth]

        yield ("start", {"files": [f.path for f in selected], "depth": len(selected)})

        provider = get_llm_provider(model=model or None)
        all_findings: list[dict[str, Any]] = []
        for f in selected:
            try:
                content = await self._file_content(f.id)
                findings = await self._review_file(provider, f.path, content)
                for fd in findings:
                    fd["file"] = f.path
                all_findings.extend(findings)
                yield ("file", {"path": f.path, "findings": findings})
            except Exception as e:  # noqa: BLE001
                yield (
                    "file",
                    {"path": f.path, "findings": [], "error": f"{type(e).__name__}: {e}"},
                )

        yield ("summary", _summarize(all_findings))
        yield ("done", {"model": provider.model})

    async def _file_content(self, file_id: UUID) -> str:
        chunks = await self.files.list_chunks_for_file(file_id)
        chunks = sorted(chunks, key=lambda c: c.start_line)
        text = "\n".join(c.content for c in chunks)
        return text[:_MAX_FILE_CHARS]

    async def _review_file(
        self, provider: Any, path: str, content: str
    ) -> list[dict[str, Any]]:
        if not content.strip():
            return []
        msgs = [
            ChatMessage(role="system", content=_AUDIT_SYS),
            ChatMessage(role="user", content=f"File: {path}\n\n```\n{content}\n```"),
        ]
        resp = await provider.chat(msgs, temperature=0.1, max_tokens=700)
        return _parse_findings(resp.content)


def _parse_findings(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        sev = str(it.get("severity", "low")).lower()
        if sev not in _VALID_SEV:
            sev = "low"
        cat = str(it.get("category", "smell")).lower()
        if cat not in _VALID_CAT:
            cat = "smell"
        title = str(it.get("title", "")).strip()[:200]
        detail = str(it.get("detail", "")).strip()[:600]
        raw_line = it.get("line")
        line: int | None = None
        if isinstance(raw_line, bool):
            line = None
        elif isinstance(raw_line, (int, float)):
            line = int(raw_line)
        elif isinstance(raw_line, str) and raw_line.strip().isdigit():
            line = int(raw_line.strip())
        if not title and not detail:
            continue
        out.append(
            {"severity": sev, "category": cat, "line": line, "title": title, "detail": detail}
        )
    return out[:12]


def _summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_sev = {"high": 0, "medium": 0, "low": 0}
    by_cat: dict[str, int] = {}
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
    return {"total": len(findings), "by_severity": by_sev, "by_category": by_cat}


def _is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    if any(seg in {"test", "tests", "__tests__", "spec", "specs"} for seg in parts):
        return True
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith(("_test.py", "_test.go", "_test.rb"))
        or ".test." in name
        or ".spec." in name
    )
