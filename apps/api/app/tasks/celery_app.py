"""Celery application factory.

One Celery app per process. Broker and result backend both Redis. Tasks are
auto-discovered from `app.tasks.*` modules; each task module is imported below.
"""
from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "aca",
    broker=settings.effective_broker,
    backend=settings.effective_result_backend,
    include=["app.tasks.ingest"],
)

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
