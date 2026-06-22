"""Multi-agent orchestrator (additive — does not touch the single-agent chat).

A simple, robust planner → researchers → synthesizer pipeline:

1. **Planner** turns the user's task into a few focused sub-questions.
2. **Researcher** (one per sub-question) answers it grounded ONLY in code
   retrieved via the existing Phase-3 hybrid search.
3. **Synthesizer** combines the findings into one final answer.

Reuses `SearchService` (retrieval) and the LLM provider abstraction. Every LLM
call is guarded so a failure (e.g. a rate limit) degrades gracefully into a
partial result rather than a 500.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.agents.schemas import AgentRunRequest, AgentRunResponse, AgentStep
from app.domain.search.context import pack_context
from app.domain.search.service import SearchService
from app.domain.users.models import User
from app.infrastructure.llm import ChatMessage, get_llm_provider

log = get_logger("agents")

_PLAN_SYS = (
    "You are a planning agent for a codebase assistant. Break the user's task "
    "into a few focused, independent sub-questions that can each be answered by "
    "searching the code. Return ONLY a JSON array of short question strings — no "
    "prose, no numbering."
)

_RESEARCH_SYS = (
    "You are a research agent. Answer the sub-question using ONLY the provided "
    "code excerpts. Be concise and specific, reference file paths, and if the "
    "excerpts don't cover it, say so plainly. Do not invent code."
)

_SYNTH_SYS = (
    "You are a synthesis agent. Combine the research findings into one clear, "
    "well-structured answer to the user's original task. Use markdown (headings, "
    "bullet points). Be accurate and concise; don't just repeat the findings."
)


class AgentOrchestrator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.search = SearchService(session)

    async def run(self, owner: User, req: AgentRunRequest) -> AgentRunResponse:
        provider = get_llm_provider(model=req.model or None)
        plan = await self._plan(provider, req.task, req.max_steps)
        steps: list[AgentStep] = []
        for sub in plan:
            steps.append(await self._research(provider, owner, sub, req.repository_ids))
        synthesis = await self._synthesize(provider, req.task, steps)
        return AgentRunResponse(
            task=req.task,
            plan=plan,
            steps=steps,
            synthesis=synthesis,
            model=provider.model,
        )

    async def _plan(self, provider: Any, task: str, max_steps: int) -> list[str]:
        msgs = [
            ChatMessage(role="system", content=_PLAN_SYS),
            ChatMessage(
                role="user",
                content=(
                    f"Task: {task}\n\nReturn at most {max_steps} sub-questions as "
                    "a JSON array of strings."
                ),
            ),
        ]
        try:
            resp = await provider.chat(msgs, temperature=0.2, max_tokens=300)
            return self._parse_list(resp.content, max_steps, fallback=task)
        except Exception as e:  # noqa: BLE001
            log.warning("agent_plan_failed", error=str(e))
            return [task]

    async def _research(
        self, provider: Any, owner: User, sub: str, repo_ids: list[Any]
    ) -> AgentStep:
        try:
            hits, _r, _t = await self.search.search(
                owner,
                query=sub,
                repository_ids=repo_ids,
                k=8,
                mode="hybrid",
                rerank=False,
            )
            files, _total, _trunc = pack_context(hits, max_tokens=1200)
            blocks: list[str] = []
            citations: list[dict[str, Any]] = []
            for f in files:
                for c in f.chunks:
                    blocks.append(
                        f"## {f.file_path}:{c.start_line}-{c.end_line}\n"
                        f"```\n{c.content}\n```"
                    )
                    citations.append(
                        {
                            "repository_id": str(c.repository_id),
                            "file_id": str(c.file_id),
                            "file_path": c.file_path,
                            "start_line": c.start_line,
                            "end_line": c.end_line,
                        }
                    )
            context = "\n\n".join(blocks) or "(no relevant code found)"
            msgs = [
                ChatMessage(role="system", content=_RESEARCH_SYS),
                ChatMessage(
                    role="user",
                    content=f"Sub-question: {sub}\n\nCode excerpts:\n{context}",
                ),
            ]
            resp = await provider.chat(msgs, temperature=0.2, max_tokens=500)
            return AgentStep(title=sub, finding=resp.content.strip(), citations=citations)
        except Exception as e:  # noqa: BLE001
            return AgentStep(title=sub, finding="", citations=[], error=f"{type(e).__name__}: {e}")

    async def _synthesize(self, provider: Any, task: str, steps: list[AgentStep]) -> str:
        findings = "\n\n".join(
            f"### {s.title}\n{s.finding}" for s in steps if s.finding.strip()
        )
        if not findings:
            return (
                "No findings were produced — the research steps failed (often an "
                "LLM rate limit on the free tier). Try again later or pick a "
                "lighter model."
            )
        msgs = [
            ChatMessage(role="system", content=_SYNTH_SYS),
            ChatMessage(
                role="user",
                content=f"Original task: {task}\n\nResearch findings:\n{findings}",
            ),
        ]
        try:
            resp = await provider.chat(msgs, temperature=0.3, max_tokens=800)
            return resp.content.strip()
        except Exception as e:  # noqa: BLE001
            return f"(synthesis failed: {type(e).__name__}: {e})"

    @staticmethod
    def _parse_list(text: str, max_n: int, fallback: str) -> list[str]:
        """Parse the planner output into a list of sub-questions, defensively."""
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m:
            try:
                arr = json.loads(m.group(0))
                items = [str(x).strip() for x in arr if str(x).strip()]
                if items:
                    return items[:max_n]
            except Exception:  # noqa: BLE001
                pass
        # Fallback: strip list markers from lines.
        cleaned = [re.sub(r"^[\d.)\-*\s]+", "", ln).strip() for ln in text.splitlines()]
        items = [ln for ln in cleaned if len(ln) > 5][:max_n]
        return items or [fallback]
