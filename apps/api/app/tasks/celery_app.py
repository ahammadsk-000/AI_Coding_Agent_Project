"""Celery application factory.

One Celery app per process. Broker and result backend both Redis. Tasks are
auto-discovered from `app.tasks.*` modules; each task module is imported below.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

# Import all model modules so SQLAlchemy's Base.metadata has every table registered
# in the worker process. Without this, FK targets like users.id can't be resolved
# during flush of repositories rows from the ingest task.
from app.domain.chat import models as _chat_models  # noqa: F401
from app.domain.memory import models as _memory_models  # noqa: F401
from app.domain.repositories import models as _repo_models  # noqa: F401
from app.domain.users import models as _user_models  # noqa: F401

configure_logging()

celery_app = Celery(
    "aca",
    broker=settings.effective_broker,
    backend=settings.effective_result_backend,
    include=["app.tasks.ingest"],
)

@celery_app.on_after_configure.connect  # type: ignore[misc]
def _start_worker_metrics(sender, **_kwargs) -> None:
    """Expose worker metrics to Prometheus once the worker is configured.

    Fires in the worker main process. No-op when PROMETHEUS_MULTIPROC_DIR is
    unset (e.g. when this module is imported by the api/beat).
    """
    try:
        from app.worker_metrics import start_worker_metrics_server

        start_worker_metrics_server()
    except Exception:  # pragma: no cover — never let metrics kill the worker
        pass


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
    result_expires=60 * 60 * 24,  # 1 day
    task_routes={
        "tasks.ingest.*": {"queue": "ingest"},
    },
    task_default_queue="default",
)
