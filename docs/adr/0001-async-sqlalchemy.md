# ADR 0001 — Use SQLAlchemy 2.0 async (over Tortoise / SQLModel / raw asyncpg)

- Status: Accepted
- Date: 2026-05-21

## Context

We need an async-capable ORM for FastAPI that:
- Has first-class async/await on Postgres
- Plays well with Alembic for migrations
- Is widely used (hiring + community support)
- Doesn't lock us out of complex SQL when we need it (window funcs, CTEs, JSONB ops)

Candidates: SQLAlchemy 2.0 async, Tortoise ORM, SQLModel, raw asyncpg.

## Decision

**SQLAlchemy 2.0 async.**

## Rationale

- **Alembic integration is native.** Tortoise's Aerich is less mature; SQLModel inherits
  Alembic via SQLAlchemy but adds a Pydantic coupling we don't want at the data layer.
- **Escape hatches.** When we need recursive CTEs for the call-graph queries in Phase 2,
  raw `text()` and Core constructs are available without leaving the ORM.
- **Hiring + ecosystem.** SQLAlchemy is the lingua franca; engineers can ramp instantly.
- **Type-safe with 2.0 style.** `Mapped[...]` + `mapped_column` give us static analysis
  parity with SQLModel without the Pydantic mixing.

## Consequences

- Slightly more verbose model definitions than SQLModel.
- Repository pattern is mandatory — we never call `session.execute()` from routers.
- Domain `schemas.py` (Pydantic) and `models.py` (SQLAlchemy) are intentionally separate.
