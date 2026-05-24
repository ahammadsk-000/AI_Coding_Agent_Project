# syntax=docker/dockerfile:1.7

# ============== base ==============
FROM python:3.12-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# system deps: build essentials for asyncpg/psycopg, libpq for runtime, curl for health,
# git for the worker's repo-ingestion path (GitPython requires the git binary at import time)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ============== deps ==============
FROM base AS deps
COPY pyproject.toml ./
# install runtime deps using pyproject; create a lock-like layer
RUN pip install --upgrade pip && pip install -e ".[dev]" --no-cache-dir

# ============== dev (used by docker-compose) ==============
FROM deps AS dev
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ============== prod ==============
FROM base AS prod
# install only runtime deps (no [dev])
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install . --no-cache-dir

COPY . .

# non-root user
RUN useradd --create-home --shell /bin/bash --uid 10001 app \
    && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
