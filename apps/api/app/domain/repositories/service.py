"""Application service for the repositories context.

Use cases:
- create a repository entry for an owner
- enqueue an ingestion job
- list a user's repositories / jobs
- delete a repository (cascades cleanup of files/symbols/chunks)

This module never talks to git / tree-sitter / Qdrant directly; it dispatches a
Celery task that handles the heavy lifting (see app.tasks.ingest).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.repositories.models import (
    IngestJob,
    Repository,
    RepositoryStatus,
)
from app.domain.repositories.repository import IngestJobRepo, RepositoryRepo
from app.domain.repositories.schemas import RepositoryCreate
from app.domain.users.models import User


class RepositoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repos = RepositoryRepo(session)
        self.jobs = IngestJobRepo(session)

    async def create(self, owner: User, data: RepositoryCreate) -> Repository:
        # Detect duplicate (owner, url) early — DB also enforces uq constraint
        existing = await self.repos.list_for_owner(owner.id)
        if any(r.url == data.url for r in existing):
            raise ConflictError("Repository already registered for this user")

        repo = Repository(
            owner_id=owner.id,
            name=data.name,
            url=data.url,
            source_type=data.source_type,  # type: ignore[arg-type]
            default_branch=data.default_branch,
            status=RepositoryStatus.new,
            qdrant_collection=None,  # set on first successful ingest
        )
        return await self.repos.add(repo)

    async def list_mine(self, owner: User) -> list[Repository]:
        return await self.repos.list_for_owner(owner.id)

    async def get_mine(self, owner: User, repo_id: UUID) -> Repository:
        repo = await self.repos.get_for_owner(repo_id, owner.id)
        if repo is None:
            raise NotFoundError("Repository not found")
        return repo

    async def delete_mine(self, owner: User, repo_id: UUID) -> None:
        repo = await self.get_mine(owner, repo_id)
        await self.repos.delete(repo)

    async def enqueue_ingest(self, owner: User, repo_id: UUID) -> IngestJob:
        """Create an ingest job row and dispatch the Celery task."""
        repo = await self.get_mine(owner, repo_id)
        if repo.status == RepositoryStatus.ingesting:
            raise ConflictError("An ingest is already in progress for this repository")

        job = IngestJob(repository_id=repo.id)
        await self.jobs.add(job)
        await self.repos.set_status(repo, RepositoryStatus.ingesting)
        # Commit early so the worker can see the row, then dispatch outside the txn.
        await self.session.commit()

        # Late import: only the API path needs Celery; worker imports its own.
        from app.tasks.ingest import ingest_repository

        async_result = ingest_repository.delay(str(repo.id), str(job.id))
        # Re-attach session for follow-up update
        merged = await self.jobs.get(job.id)
        if merged is not None:
            merged.celery_task_id = async_result.id
            await self.session.flush()
        return merged or job

    async def get_job(self, owner: User, repo_id: UUID, job_id: UUID) -> IngestJob:
        repo = await self.get_mine(owner, repo_id)
        job = await self.jobs.get(job_id)
        if job is None or job.repository_id != repo.id:
            raise NotFoundError("Ingest job not found")
        return job

    async def list_jobs(self, owner: User, repo_id: UUID) -> list[IngestJob]:
        repo = await self.get_mine(owner, repo_id)
        return await self.jobs.list_for_repo(repo.id)

    def assert_owner(self, owner: User, repo: Repository) -> None:
        if repo.owner_id != owner.id and not owner.is_superuser:
            raise ForbiddenError("Not the repository owner")
