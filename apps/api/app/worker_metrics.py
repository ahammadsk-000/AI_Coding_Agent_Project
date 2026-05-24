"""Expose Celery worker metrics to Prometheus (Phase 8 consolidation).

Celery's prefork pool runs tasks in forked child processes, so metrics
incremented during a task live in a child — not the main process. We use
prometheus_client's multiprocess mode: every process writes metric samples to
files under `PROMETHEUS_MULTIPROC_DIR`, and a tiny HTTP server in the worker's
main process aggregates them via `MultiProcessCollector` for Prometheus to
scrape.

Activated only when `PROMETHEUS_MULTIPROC_DIR` is set (compose sets it for the
worker, not the api — the api uses the normal in-process registry).
"""
from __future__ import annotations

import glob
import os

from app.core.logging import get_logger

log = get_logger("worker_metrics")


def _clear_multiproc_dir(mp_dir: str) -> None:
    """Remove stale per-process metric files from a previous worker run."""
    for f in glob.glob(os.path.join(mp_dir, "*.db")):
        try:
            os.remove(f)
        except OSError:
            pass


def start_worker_metrics_server(port: int = 9100) -> None:
    """Start the aggregating metrics HTTP server in the worker main process."""
    mp_dir = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not mp_dir:
        log.info("worker_metrics_disabled", reason="PROMETHEUS_MULTIPROC_DIR unset")
        return
    os.makedirs(mp_dir, exist_ok=True)
    _clear_multiproc_dir(mp_dir)

    from prometheus_client import CollectorRegistry, start_http_server
    from prometheus_client import multiprocess

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    start_http_server(port, registry=registry)
    log.info("worker_metrics_started", port=port, multiproc_dir=mp_dir)
