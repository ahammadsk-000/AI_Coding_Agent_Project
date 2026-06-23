"""Repo insights (additive): an LLM-generated architecture diagram + onboarding
docs, and a data-driven code map. Reuses the file inventory + symbols already in
Postgres; never touches existing flows.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.domain.repositories.models import Repository, RepositoryFile
from app.domain.repositories.repository import FileRepo
from app.domain.search.service import SearchService
from app.domain.users.models import User
from app.infrastructure.llm import ChatMessage, get_llm_provider

_DIAGRAM_SYS = (
    "You are an architecture analyst. From a repository's file inventory, produce "
    "a Mermaid `flowchart TD` diagram of its high-level architecture (main "
    "modules/packages/layers and how they relate). STRICT Mermaid syntax: node ids "
    "are simple identifiers; labels go in square brackets like A[\"Label\"]; edges "
    "are `A --> B`, or with a label `A -->|uses| B` (exactly one pipe before AND "
    "after the label, with NO extra `>` after the closing pipe). Output ONLY a "
    "fenced ```mermaid code block — ~8-15 nodes, valid syntax, nothing else."
)

_DOCS_SYS = (
    "You are a technical writer. From a repository's file inventory, write a concise "
    "onboarding guide for a new developer in markdown with these sections: "
    "## Overview, ## Key files & directories, ## How it's structured, and "
    "## Getting started (only if inferable). Be accurate and grounded in the "
    "inventory; do not invent files or commands you can't see."
)


class InsightsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _inventory(self, repo_id) -> str:
        stmt = (
            select(RepositoryFile)
            .where(RepositoryFile.repository_id == repo_id)
            .order_by(RepositoryFile.path)
        )
        files = list((await self.session.execute(stmt)).scalars())
        lines = [
            f"- {f.path} ({f.language or 'text'}, {f.lines} lines)" for f in files[:80]
        ]
        if len(files) > 80:
            lines.append(f"- ...and {len(files) - 80} more file(s)")
        return "\n".join(lines) or "(no files indexed)"

    async def diagram(self, repo: Repository) -> str:
        inv = await self._inventory(repo.id)
        resp = await get_llm_provider().chat(
            [
                ChatMessage(role="system", content=_DIAGRAM_SYS),
                ChatMessage(
                    role="user",
                    content=f"Repository: {repo.name}\nFiles:\n{inv}\n\nProduce the diagram.",
                ),
            ],
            temperature=0.2,
            max_tokens=700,
        )
        return _repair_mermaid(_extract_mermaid(resp.content))

    async def docs(self, repo: Repository) -> str:
        inv = await self._inventory(repo.id)
        resp = await get_llm_provider().chat(
            [
                ChatMessage(role="system", content=_DOCS_SYS),
                ChatMessage(
                    role="user",
                    content=f"Repository: {repo.name}\nFiles:\n{inv}\n\nWrite the onboarding guide.",
                ),
            ],
            temperature=0.3,
            max_tokens=900,
        )
        return resp.content.strip()

    async def codemap(self, repo: Repository) -> str:
        """Data-driven Mermaid graph: repo → top-level directories → files.

        Built from the file inventory (always present), so it works even when
        tree-sitter symbol extraction produced nothing for a repo.
        """
        stmt = (
            select(RepositoryFile.path)
            .where(RepositoryFile.repository_id == repo.id)
            .order_by(RepositoryFile.path)
        )
        paths = [row[0] for row in (await self.session.execute(stmt)).all()]
        return _build_codemap(paths, repo.name)

    async def metrics(self, repo: Repository) -> dict[str, Any]:
        """Repo analytics from the file inventory only — no LLM, always works."""
        stmt = select(
            RepositoryFile.path,
            RepositoryFile.language,
            RepositoryFile.lines,
            RepositoryFile.size_bytes,
        ).where(RepositoryFile.repository_id == repo.id)
        rows = (await self.session.execute(stmt)).all()

        total_files = len(rows)
        total_lines = sum(r.lines for r in rows)
        total_bytes = sum(r.size_bytes for r in rows)
        by_lang: dict[str, dict[str, int]] = defaultdict(lambda: {"files": 0, "lines": 0})
        test_files = 0
        for r in rows:
            lang = r.language or "other"
            by_lang[lang]["files"] += 1
            by_lang[lang]["lines"] += r.lines
            if _is_test_path(r.path):
                test_files += 1

        languages = sorted(
            (
                {"language": k, "files": v["files"], "lines": v["lines"]}
                for k, v in by_lang.items()
            ),
            key=lambda x: x["lines"],
            reverse=True,
        )
        largest = sorted(
            (
                {"path": r.path, "lines": r.lines, "size_bytes": r.size_bytes}
                for r in rows
            ),
            key=lambda x: x["lines"],
            reverse=True,
        )[:10]
        return {
            "total_files": total_files,
            "total_lines": total_lines,
            "total_bytes": total_bytes,
            "languages": languages,
            "largest_files": largest,
            "test_files": test_files,
            "source_files": total_files - test_files,
        }

    async def similar(
        self, owner: User, repo: Repository, file_id: UUID, k: int = 6
    ) -> list[dict[str, Any]]:
        """Find code chunks elsewhere in the repo semantically similar to a file.

        Uses the file's largest chunk as a vector query against Qdrant (reuses
        the existing dense retrieval), then drops same-file hits. No LLM.
        """
        files = FileRepo(self.session)
        target = await files.get_file(file_id)
        if target is None or target.repository_id != repo.id:
            raise NotFoundError("File not found in this repository")
        chunks = await files.list_chunks_for_file(file_id)
        if not chunks:
            return []
        rep = max(chunks, key=lambda c: c.token_count or 0)

        hits, _r, _t = await SearchService(self.session).search(
            owner,
            query=rep.content,
            repository_ids=[repo.id],
            k=k + 6,
            mode="dense",
            rerank=False,
        )
        out: list[dict[str, Any]] = []
        for h in hits:
            if str(h.file_id) == str(file_id):
                continue
            out.append(
                {
                    "file_id": str(h.file_id),
                    "file_path": h.file_path,
                    "language": h.language,
                    "start_line": h.start_line,
                    "end_line": h.end_line,
                    "score": round(float(h.score), 3),
                    "content": h.content,
                }
            )
            if len(out) >= k:
                break
        return out


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


def _extract_mermaid(text: str) -> str:
    m = re.search(r"```(?:mermaid)?\s*\n([\s\S]*?)```", text)
    return (m.group(1) if m else text).strip()


def _san(s: object) -> str:
    """Make a string safe to use inside a Mermaid `["..."]` label."""
    return re.sub(r'["\[\]{}|<>`()]', " ", str(s)).strip()[:60] or "?"


def _build_codemap(paths: list[str], repo_name: str) -> str:
    by_dir: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        parts = p.split("/")
        top = parts[0] if len(parts) > 1 else "(root)"
        by_dir[top].append(p)

    lines = ["flowchart LR", f'  root["{_san(repo_name)}"]']
    if not paths:
        lines.append('  root --> empty["no files indexed yet"]')
        return "\n".join(lines)
    dirs = sorted(by_dir.items(), key=lambda kv: -len(kv[1]))[:12]
    for di, (d, files) in enumerate(dirs):
        did = f"d{di}"
        lines.append(f'  root --> {did}["{_san(d)} ({len(files)})"]')
        for fi, fpath in enumerate(sorted(files)[:8]):
            fname = fpath.split("/")[-1]
            lines.append(f'  {did} --> {did}f{fi}["{_san(fname)}"]')
        if len(files) > 8:
            lines.append(f'  {did} --> {did}more["+{len(files) - 8} more"]')
    return "\n".join(lines)


def _repair_mermaid(code: str) -> str:
    """Fix the most common LLM Mermaid mistake: `-->|label|>` → `-->|label|`."""
    return code.replace("|>", "|")
