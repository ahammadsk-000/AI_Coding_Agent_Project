"""Data access for repositories context."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories.models import (
    CodeChunk,
    CodeSymbol,
    IngestJob,
    IngestStatus,
    Repository,
    RepositoryFile,
    RepositoryStatus,
)


class RepositoryRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, repo_id: UUID) -> Repository | None:
        return (
            await self.session.execute(select(Repository).where(Repository.id == repo_id))
        ).scalar_one_or_none()

    async def get_for_owner(self, repo_id: UUID, owner_id: UUID) -> Repository | None:
        stmt = select(Repository).where(
            Repository.id == repo_id, Repository.owner_id == owner_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_owner(self, owner_id: UUID) -> list[Repository]:
        stmt = (
            select(Repository)
            .where(Repository.owner_id == owner_id)
            .order_by(Repository.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars())

    async def add(self, repo: Repository) -> Repository:
        self.session.add(repo)
        await self.session.flush()
        return repo

    async def set_status(self, repo: Repository, status: RepositoryStatus) -> None:
        repo.status = status
        await self.session.flush()

    async def set_stats(self, repo: Repository, stats: dict[str, Any]) -> None:
        repo.stats = stats
        repo.last_indexed_at = datetime.utcnow()
        await self.session.flush()

    async def delete(self, repo: Repository) -> None:
        await self.session.delete(repo)
        await self.session.flush()


class IngestJobRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, job_id: UUID) -> IngestJob | None:
        return (
            await self.session.execute(select(IngestJob).where(IngestJob.id == job_id))
        ).scalar_one_or_none()

    async def list_for_repo(self, repo_id: UUID, limit: int = 20) -> list[IngestJob]:
        stmt = (
            select(IngestJob)
            .where(IngestJob.repository_id == repo_id)
            .order_by(IngestJob.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def add(self, job: IngestJob) -> IngestJob:
        self.session.add(job)
        await self.session.flush()
        return job

    async def update_progress(
        self,
        job: IngestJob,
        *,
        files_seen: int | None = None,
        files_indexed: int | None = None,
        chunks_indexed: int | None = None,
        bytes_indexed: int | None = None,
    ) -> None:
        if files_seen is not None:
            job.files_seen = files_seen
        if files_indexed is not None:
            job.files_indexed = files_indexed
        if chunks_indexed is not None:
            job.chunks_indexed = chunks_indexed
        if bytes_indexed is not None:
            job.bytes_indexed = bytes_indexed
        await self.session.flush()

    async def mark_running(self, job: IngestJob, celery_task_id: str | None = None) -> None:
        job.status = IngestStatus.running
        job.started_at = datetime.utcnow()
        if celery_task_id:
            job.celery_task_id = celery_task_id
        await self.session.flush()

    async def mark_done(self, job: IngestJob) -> None:
        job.status = IngestStatus.succeeded
        job.finished_at = datetime.utcnow()
        await self.session.flush()

    async def mark_failed(self, job: IngestJob, error: str) -> None:
        job.status = IngestStatus.failed
        job.finished_at = datetime.utcnow()
        job.error = error[:8192]
        await self.session.flush()


class FileRepo:
    """Bulk-friendly persistence for files / symbols / chunks during ingest."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def delete_all_for_repo(self, repo_id: UUID) -> None:
        # cascades to files -> symbols & chunks
        await self.session.execute(
            RepositoryFile.__table__.delete().where(RepositoryFile.repository_id == repo_id)
        )
        await self.session.flush()

    def stage_file(self, file: RepositoryFile) -> None:
        self.session.add(file)

    def stage_symbols(self, symbols: list[CodeSymbol]) -> None:
        self.session.add_all(symbols)

    def stage_chunks(self, chunks: list[CodeChunk]) -> None:
        self.session.add_all(chunks)

    async def flush(self) -> None:
        await self.session.flush()
