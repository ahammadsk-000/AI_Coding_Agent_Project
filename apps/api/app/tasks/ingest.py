"""Repository ingestion pipeline as a Celery task.

Flow:
  1. Look up repository + ingest job; mark running.
  2. Shallow-clone into the workspace.
  3. Walk the working tree, filter to allowed languages and size cap.
  4. For each file:
       - detect language
       - tree-sitter parse + extract symbols (best-effort)
       - chunk (AST-aware, line-window fallback)
       - persist file/symbol/chunk rows in batches
  5. Embed all chunks in batches and upsert to Qdrant.
  6. Publish progress events on a Redis pub/sub channel for SSE consumers.
  7. Mark job done + repository ready; write stats.

The task uses synchronous SQLAlchemy via the existing async engine via
`asyncio.run`. Keeping the worker code synchronous from Celery's view avoids
event-loop pitfalls with task pools.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.repositories.models import (
    CodeChunk,
    CodeSymbol,
    IngestStatus,
    RepositoryFile,
    RepositoryStatus,
)
from app.domain.repositories.repository import FileRepo, IngestJobRepo, RepositoryRepo
from app.infrastructure.db.session import dispose_engine, session_factory
from app.infrastructure.embeddings import get_embedding_provider
from app.infrastructure.git.clone import file_sha256, shallow_clone, workdir_for
from app.infrastructure.parsers.chunker import chunk_file
from app.infrastructure.parsers.language import detect_language
from app.infrastructure.parsers.tree_sitter import extract_symbols
from app.infrastructure.qdrant.client import QdrantService, collection_for
from app.infrastructure.redis.client import get_redis

log = get_task_logger(__name__)


# ---------- progress publishing ----------
def _events_channel(job_id: str) -> str:
    return f"ingest:events:{job_id}"


async def _publish(job_id: str, event: dict[str, Any]) -> None:
    redis = get_redis()
    await redis.publish(_events_channel(job_id), json.dumps(event, default=str))


def _publish_sync(job_id: str, event: dict[str, Any]) -> None:
    """Best-effort fire-and-forget publish from a sync context."""
    try:
        asyncio.run(_publish(job_id, event))
    except RuntimeError:
        # already inside a loop (shouldn't happen in worker); fall back to sync redis
        import redis as redis_sync

        client = redis_sync.from_url(settings.effective_broker, decode_responses=True)
        client.publish(_events_channel(job_id), json.dumps(event, default=str))


# ---------- per-file processing ----------
@dataclass(slots=True)
class FileResult:
    file_row: RepositoryFile
    symbol_rows: list[CodeSymbol]
    chunk_rows: list[CodeChunk]
    chunk_contents: list[str]   # parallel to chunk_rows
    bytes_in: int


_IGNORED_DIRS = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
                 ".next", ".cache", ".turbo", "target", "vendor", ".idea", ".vscode"}


def _walk_repo(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in _IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def _process_file(
    *,
    repo_id: uuid.UUID,
    root: Path,
    path: Path,
) -> FileResult | None:
    rel = path.relative_to(root).as_posix()
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0 or size > settings.ingest_max_file_bytes:
        return None
    language = detect_language(path)
    if language is None or language not in settings.ingest_allowed_langs:
        return None

    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None

    symbols = extract_symbols(source=raw, language=language, file_path=rel)
    chunks = chunk_file(
        source=source,
        symbols=symbols,
        target_tokens=settings.ingest_chunk_target_tokens,
        overlap_tokens=settings.ingest_chunk_overlap_tokens,
    )
    if not chunks:
        return None

    sha = file_sha256(path)
    file_row = RepositoryFile(
        id=uuid.uuid4(),
        repository_id=repo_id,
        path=rel,
        language=language,
        sha=sha,
        size_bytes=size,
        lines=source.count("\n") + 1,
    )

    sym_rows: list[CodeSymbol] = []
    sym_id_by_idx: dict[int, uuid.UUID] = {}
    for i, s in enumerate(symbols):
        sid = uuid.uuid4()
        sym_id_by_idx[i] = sid
        sym_rows.append(
            CodeSymbol(
                id=sid,
                file_id=file_row.id,
                kind=s.kind,
                name=s.name,
                qualified_name=s.qualified_name,
                signature=s.signature,
                start_line=s.start_line,
                end_line=s.end_line,
            )
        )

    chunk_rows: list[CodeChunk] = []
    chunk_contents: list[str] = []
    for c in chunks:
        sid = sym_id_by_idx.get(c.symbol_index) if c.symbol_index is not None else None
        cid = uuid.uuid4()
        chunk_rows.append(
            CodeChunk(
                id=cid,
                repository_id=repo_id,
                file_id=file_row.id,
                symbol_id=sid,
                content=c.content,
                language=language,
                start_line=c.start_line,
                end_line=c.end_line,
                token_count=c.token_count,
                vector_id=cid.hex,
            )
        )
        chunk_contents.append(c.content)

    return FileResult(
        file_row=file_row,
        symbol_rows=sym_rows,
        chunk_rows=chunk_rows,
        chunk_contents=chunk_contents,
        bytes_in=size,
    )


# ---------- task entrypoint ----------
@shared_task(
    name="tasks.ingest.repository",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 0},  # we manage retries explicitly; one shot
    queue="ingest",
)
def ingest_repository(self, repository_id: str, job_id: str) -> dict[str, Any]:
    """Synchronous Celery entry; delegates to async core via asyncio.run."""
    return asyncio.run(_ingest_repository_async(repository_id, job_id))


async def _ingest_repository_async(repository_id: str, job_id: str) -> dict[str, Any]:
    # Each Celery task call runs in its own asyncio.run() loop, but the module-level
    # async engine carries pooled asyncpg connections bound to the previous task's
    # (now-closed) loop. Dispose the pool so connections are recreated in this loop.
    await dispose_engine()

    repo_uuid = uuid.UUID(repository_id)
    job_uuid = uuid.UUID(job_id)
    workspace = Path(settings.ingest_workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    stats: dict[str, Any] = {
        "files_seen": 0, "files_indexed": 0, "chunks_indexed": 0, "bytes_indexed": 0
    }

    async with session_factory() as session:  # type: AsyncSession
        repos = RepositoryRepo(session)
        jobs = IngestJobRepo(session)
        files = FileRepo(session)

        repo = await repos.get(repo_uuid)
        job = await jobs.get(job_uuid)
        if repo is None or job is None:
            return {"ok": False, "error": "repository or job not found"}

        await jobs.mark_running(job)
        await session.commit()

    _publish_sync(job_id, {"type": "status", "status": "running"})

    embedder = get_embedding_provider()
    qdrant = QdrantService.get()
    coll_name = collection_for(repo_uuid)
    qdrant.ensure_collection(coll_name, embedder.dimension)

    dest = workdir_for(workspace, repository_id)
    try:
        # ---- clone ----
        _publish_sync(job_id, {"type": "log", "message": "cloning repository"})
        clone = shallow_clone(
            url=repo.url,
            branch=repo.default_branch,
            dest=dest,
            max_bytes=settings.ingest_max_repo_bytes,
        )

        # ---- process files ----
        results: list[FileResult] = []
        files_seen = 0
        for path in _walk_repo(clone.workdir):
            files_seen += 1
            res = _process_file(repo_id=repo_uuid, root=clone.workdir, path=path)
            if res is not None:
                results.append(res)

            if files_seen % 50 == 0:
                _publish_sync(job_id, {
                    "type": "progress",
                    "files_seen": files_seen,
                    "files_indexed": len(results),
                })

        stats["files_seen"] = files_seen
        stats["files_indexed"] = len(results)
        stats["bytes_indexed"] = sum(r.bytes_in for r in results)

        # ---- persist file/symbol/chunk rows + embed + upsert per batch ----
        async with session_factory() as session:
            files_repo = FileRepo(session)
            # Wipe old ingest artifacts for this repo (Phase 2 is full re-ingest)
            await files_repo.delete_all_for_repo(repo_uuid)
            await session.flush()

            all_chunks_contents: list[str] = []
            all_chunks_rows: list[CodeChunk] = []
            for res in results:
                files_repo.stage_file(res.file_row)
                files_repo.stage_symbols(res.symbol_rows)
                files_repo.stage_chunks(res.chunk_rows)
                all_chunks_contents.extend(res.chunk_contents)
                all_chunks_rows.extend(res.chunk_rows)
            await files_repo.flush()
            await session.commit()

            # ---- embed + upsert in batches ----
            batch_size = settings.ingest_embed_batch_size
            points_batch: list[tuple[str, list[float], dict[str, Any]]] = []
            for i in range(0, len(all_chunks_contents), batch_size):
                texts = all_chunks_contents[i : i + batch_size]
                vecs = embedder.embed_texts(texts)
                for j, vec in enumerate(vecs):
                    chunk = all_chunks_rows[i + j]
                    points_batch.append((
                        chunk.vector_id or chunk.id.hex,
                        vec,
                        {
                            "chunk_id": str(chunk.id),
                            "repository_id": str(chunk.repository_id),
                            "file_id": str(chunk.file_id),
                            "symbol_id": str(chunk.symbol_id) if chunk.symbol_id else None,
                            "language": chunk.language,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                        },
                    ))
                if len(points_batch) >= batch_size:
                    qdrant.upsert_chunks(collection=coll_name, points=points_batch)
                    points_batch = []
                stats["chunks_indexed"] += len(vecs)
                _publish_sync(job_id, {
                    "type": "progress",
                    "files_seen": stats["files_seen"],
                    "files_indexed": stats["files_indexed"],
                    "chunks_indexed": stats["chunks_indexed"],
                })
            if points_batch:
                qdrant.upsert_chunks(collection=coll_name, points=points_batch)

        # ---- finalize ----
        async with session_factory() as session:
            repos = RepositoryRepo(session)
            jobs = IngestJobRepo(session)
            repo_db = await repos.get(repo_uuid)
            job_db = await jobs.get(job_uuid)
            if repo_db is not None:
                repo_db.qdrant_collection = coll_name
                # Persist the actual branch we cloned so re-ingests skip the fallback.
                if clone.branch and clone.branch != "HEAD" and repo_db.default_branch != clone.branch:
                    repo_db.default_branch = clone.branch
                await repos.set_stats(repo_db, {**stats, "commit_sha": clone.commit_sha,
                                                "duration_s": round(time.monotonic() - started, 2)})
                await repos.set_status(repo_db, RepositoryStatus.ready)
            if job_db is not None:
                await jobs.update_progress(
                    job_db,
                    files_seen=stats["files_seen"],
                    files_indexed=stats["files_indexed"],
                    chunks_indexed=stats["chunks_indexed"],
                    bytes_indexed=stats["bytes_indexed"],
                )
                await jobs.mark_done(job_db)
            await session.commit()

        from app.core import metrics as M
        M.ingest_jobs_total.labels("succeeded").inc()
        M.ingest_files_indexed_total.inc(stats["files_indexed"])
        M.ingest_chunks_indexed_total.inc(stats["chunks_indexed"])

        _publish_sync(job_id, {"type": "done", "status": "succeeded", **stats})
        return {"ok": True, **stats}

    except Exception as e:
        log.exception("ingest_failed", extra={"repository_id": repository_id, "job_id": job_id})
        async with session_factory() as session:
            repos = RepositoryRepo(session)
            jobs = IngestJobRepo(session)
            repo_db = await repos.get(repo_uuid)
            job_db = await jobs.get(job_uuid)
            if repo_db is not None:
                await repos.set_status(repo_db, RepositoryStatus.failed)
            if job_db is not None:
                await jobs.mark_failed(job_db, error=str(e))
            await session.commit()
        from app.core import metrics as M
        M.ingest_jobs_total.labels("failed").inc()
        _publish_sync(job_id, {"type": "error", "status": "failed", "message": str(e)})
        return {"ok": False, "error": str(e)}
