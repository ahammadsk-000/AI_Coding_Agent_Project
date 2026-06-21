"""One-shot CLI to run a single repository ingestion in its own process.

Used by the free-tier deployment (``INGEST_INLINE=true``) so ingestion can run
without a separate always-on Celery worker. Invoked as::

    python -m app.ingest_cli <repository_id> <job_id>

Running in a dedicated process gives the ingest pipeline its own asyncio loop
and SQLAlchemy engine — the same isolation a Celery worker provides — so it
never disturbs the API process's connection pool. Progress is published to
Redis pub/sub exactly as the Celery task does, so the SSE endpoint streams it
unchanged.
"""
from __future__ import annotations

import asyncio
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "usage: python -m app.ingest_cli <repository_id> <job_id>",
            file=sys.stderr,
        )
        return 2
    repository_id, job_id = sys.argv[1], sys.argv[2]

    # Import lazily so the module loads fast and only pulls ingestion deps when
    # actually run as a subprocess.
    from app.tasks.ingest import _ingest_repository_async

    result = asyncio.run(_ingest_repository_async(repository_id, job_id))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
