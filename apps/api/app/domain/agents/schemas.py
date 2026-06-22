"""Schemas for the multi-agent pipeline (planner → researchers → synthesizer)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    task: str = Field(min_length=3, max_length=2000)
    repository_ids: list[UUID] = Field(default_factory=list)
    max_steps: int = Field(default=3, ge=1, le=4)
    model: str | None = None
    # Run a reviewer/critic agent that fact-checks the synthesis (one extra LLM call).
    review: bool = True


class AgentStep(BaseModel):
    title: str
    finding: str = ""
    citations: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


class AgentReview(BaseModel):
    verdict: str  # "accurate" | "issues" | "uncertain"
    notes: str


class AgentRunResponse(BaseModel):
    task: str
    plan: list[str]
    steps: list[AgentStep]
    synthesis: str
    review: AgentReview | None = None
    refined: bool = False  # the critic flagged issues and the synthesis was revised
    model: str
