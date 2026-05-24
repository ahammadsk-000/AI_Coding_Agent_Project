"""Repository + ingestion endpoints.

POST   /api/v1/repositories                 → register a repo
GET    /api/v1/repositories                 → list mine
GET    /api/v1/repositories/{id}            → get one
DELETE /api/v1/repositories/{id}            → delete (cascades cleanup)
POST   /api/v1/repositories/{id}/ingest     → enqueue an ingest, returns job
GET    /api/v1/repositories/{id}/jobs       → list recent jobs
GET    /api/v1/repositories/{id}/jobs/{jid} → job status
GET    /api/v1/repositories/{id}/jobs/{jid}/events (SSE) → live progress stream
"""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Response, status
from sse_starlette.sse import EventSourceResponse

from app.core.dependencies import CurrentUser, DbSession
from app.domain.repositories.schemas import (
    CodeChunkPreview,
    IngestJobRead,
    RepositoryCreate,
    RepositoryFileRead,
    RepositoryRead,
)
from app.domain.repositories.service import RepositoryService
from app.infrastructure.redis.client import get_redis

router = APIRouter()


@router.post("", response_model=RepositoryRead, status_code=status.HTTP_201_CREATED)
async def create_repository(
    payload: RepositoryCreate, user: CurrentUser, db: DbSession
) -> RepositoryRead:
    repo = await RepositoryService(db).create(user, payload)
    return RepositoryRead.model_validate(repo)


@router.get("", response_model=list[RepositoryRead])
async def list_repositories(user: CurrentUser, db: DbSession) -> list[RepositoryRead]:
    repos = await RepositoryService(db).list_mine(user)
    return [RepositoryRead.model_validate(r) for r in repos]


@router.get("/{repo_id}", response_model=RepositoryRead)
async def get_repository(repo_id: UUID, user: CurrentUser, db: DbSession) -> RepositoryRead:
    repo = await RepositoryService(db).get_mine(user, repo_id)
    return RepositoryRead.model_validate(repo)


@router.delete("/{repo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(repo_id: UUID, user: CurrentUser, db: DbSession) -> Response:
    await RepositoryService(db).delete_mine(user, repo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{repo_id}/ingest", response_model=IngestJobRead, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_ingest(
    repo_id: UUID, user: CurrentUser, db: DbSession
) -> IngestJobRead:
    job = await RepositoryService(db).enqueue_ingest(user, repo_id)
    return IngestJobRead.model_validate(job)


@router.get("/{repo_id}/jobs", response_model=list[IngestJobRead])
async def list_jobs(repo_id: UUID, user: CurrentUser, db: DbSession) -> list[IngestJobRead]:
    jobs = await RepositoryService(db).list_jobs(user, repo_id)
    return [IngestJobRead.model_validate(j) for j in jobs]


@router.get("/{repo_id}/files", response_model=list[RepositoryFileRead])
async def list_files(
    repo_id: UUID, user: CurrentUser, db: DbSession
) -> list[RepositoryFileRead]:
    rows = await RepositoryService(db).list_files(user, repo_id)
    return [
        RepositoryFileRead(
            id=f.id,
            path=f.path,
            language=f.language,
            size_bytes=f.size_bytes,
            lines=f.lines,
            chunk_count=chunk_count,
        )
        for f, chunk_count in rows
    ]


@router.get(
    "/{repo_id}/files/{file_id}/chunks", response_model=list[CodeChunkPreview]
)
async def list_file_chunks(
    repo_id: UUID, file_id: UUID, user: CurrentUser, db: DbSession
) -> list[CodeChunkPreview]:
    chunks = await RepositoryService(db).list_file_chunks(user, repo_id, file_id)
    return [CodeChunkPreview.model_validate(c) for c in chunks]


@router.get("/{repo_id}/jobs/{job_id}", response_model=IngestJobRead)
async def get_job(
    repo_id: UUID, job_id: UUID, user: CurrentUser, db: DbSession
) -> IngestJobRead:
    job = await RepositoryService(db).get_job(user, repo_id, job_id)
    return IngestJobRead.model_validate(job)


@router.get("/{repo_id}/jobs/{job_id}/events")
async def job_events(
    repo_id: UUID, job_id: UUID, user: CurrentUser, db: DbSession
) -> EventSourceResponse:
    """Stream ingest events via SSE.

    Subscribes to the Redis pub/sub channel that the worker publishes to. Sends
    a snapshot of the current job state first so late connectors can resume.
    """
    # authorize: confirm the job belongs to a repo owned by the user
    job = await RepositoryService(db).get_job(user, repo_id, job_id)

    async def event_gen():
        # initial snapshot
        yield {
            "event": "snapshot",
            "data": json.dumps(IngestJobRead.model_validate(job).model_dump(mode="json")),
        }
        # if the job already finished, close immediately
        if job.status in {"succeeded", "failed", "canceled"}:
            yield {"event": "close", "data": "done"}
            return

        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"ingest:events:{job_id}")
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg is None:
                    # heartbeat to keep proxies from killing the connection
                    yield {"event": "ping", "data": "keepalive"}
                    continue
                payload = msg.get("data")
                if not payload:
                    continue
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                ev_type = parsed.get("type", "message")
                yield {"event": ev_type, "data": json.dumps(parsed)}
                if ev_type in {"done", "error"}:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(f"ingest:events:{job_id}")
            await pubsub.aclose()

    return EventSourceResponse(event_gen())
