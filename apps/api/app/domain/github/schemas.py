"""DTOs for GitHub endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GitHubStatus(BaseModel):
    configured: bool
    login: str | None = None
    name: str | None = None


class FileChange(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(max_length=1_000_000)


class CreatePRRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    base: str = Field(default="main", max_length=255)
    branch: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(default="", max_length=20_000)
    draft: bool = False
    changes: list[FileChange] = Field(min_length=1, max_length=50)


class CreatePRResponse(BaseModel):
    number: int
    url: str
    branch: str


class ReviewPRRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=100)
    repo: str = Field(min_length=1, max_length=100)
    number: int = Field(ge=1)
    post_comment: bool = True


class ReviewPRResponse(BaseModel):
    review: str
    comment_url: str | None = None
    diff_truncated: bool = False
