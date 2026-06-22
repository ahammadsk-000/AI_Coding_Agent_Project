"""Repo insights (additive): an LLM-generated architecture diagram + onboarding
docs, and a data-driven code map. Reuses the file inventory + symbols already in
Postgres; never touches existing flows.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.models import CodeSymbol, Repository, RepositoryFile
from app.infrastructure.llm import ChatMessage, get_llm_provider

_DIAGRAM_SYS = (
    "You are an architecture analyst. From a repository's file inventory, produce "
    "a Mermaid `flowchart TD` diagram of its high-level architecture — the main "
    "modules/packages/layers and how they relate. Output ONLY a fenced ```mermaid "
    "code block, nothing else. Keep it to ~8-15 nodes, use short labels, and emit "
    "valid Mermaid syntax."
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
        return _extract_mermaid(resp.content)

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
        """Data-driven Mermaid graph: repo → top files → their top symbols."""
        stmt = (
            select(CodeSymbol.name, CodeSymbol.kind, RepositoryFile.path)
            .join(RepositoryFile, RepositoryFile.id == CodeSymbol.file_id)
            .where(RepositoryFile.repository_id == repo.id)
        )
        rows = (await self.session.execute(stmt)).all()
        return _build_codemap(rows, repo.name)


def _extract_mermaid(text: str) -> str:
    m = re.search(r"```(?:mermaid)?\s*\n([\s\S]*?)```", text)
    return (m.group(1) if m else text).strip()


def _san(s: object) -> str:
    """Make a string safe to use inside a Mermaid `["..."]` label."""
    return re.sub(r'["\[\]{}|<>`()]', " ", str(s)).strip()[:60] or "?"


def _build_codemap(rows, repo_name: str) -> str:
    by_file: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for name, kind, path in rows:
        by_file[path].append((name, kind))
    files = sorted(by_file.items(), key=lambda kv: -len(kv[1]))[:15]

    lines = ["flowchart LR", f'  root["{_san(repo_name)}"]']
    if not files:
        lines.append('  root --> empty["no symbols extracted yet"]')
        return "\n".join(lines)
    for fi, (path, syms) in enumerate(files):
        fid = f"f{fi}"
        lines.append(f'  root --> {fid}["{_san(path)}"]')
        for si, (sname, _kind) in enumerate(syms[:4]):
            lines.append(f'  {fid} --> {fid}s{si}["{_san(sname)}"]')
    return "\n".join(lines)
