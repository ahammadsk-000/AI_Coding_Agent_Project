"""Repo insights (additive): an LLM-generated architecture diagram + onboarding
docs, and a data-driven code map. Reuses the file inventory + symbols already in
Postgres; never touches existing flows.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.models import Repository, RepositoryFile
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
