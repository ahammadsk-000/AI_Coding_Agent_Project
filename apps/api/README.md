# aca-api

FastAPI backend for the AI Coding Agent Platform. See repo root
[README](../../README.md) and [docs/](../../docs/) for the full picture.

## Layout

```
app/
  core/              cross-cutting: config, logging, security, exceptions, deps
  domain/            DDD bounded contexts (users, auth, ...)
    <ctx>/
      models.py      SQLAlchemy 2.0 async models
      schemas.py     Pydantic v2 DTOs
      repository.py  data access (the only place that touches the session)
      service.py     use-cases
  infrastructure/    adapters: db, redis, qdrant, llm, sandbox, git
  api/
    middleware/      request-id, rate-limit
    v1/              versioned HTTP routers (thin)
    router.py        composes v1
  main.py            app factory + lifespan
alembic/             migrations
tests/               pytest suite
```

## Local development (without docker)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

# point at your local services
export DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/ai_coding_agent
export REDIS_URL=redis://localhost:6379/0
export JWT_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
pytest -q              # unit tests
pytest -q tests/integration   # spawns Postgres+Redis via testcontainers
```
