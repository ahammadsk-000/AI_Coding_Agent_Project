# Architecture

This document is the authoritative architecture reference for the AI Coding Agent Platform.
It expands as each phase ships. **Never break documented contracts** without an ADR.

## 1. Goals & non-goals

**Goals**
- Production-grade, Kubernetes-deployable, multi-tenant AI coding platform.
- Cursor / OpenHands / Continue.dev-level capabilities: RAG over codebases, multi-agent
  workflows, sandboxed execution, GitHub integration, autonomous debugging.
- Local-first: runs end-to-end with Ollama, zero cloud API keys required.
- Pluggable: LLM providers, vector stores, sandbox backends, git providers are interfaces.

**Non-goals (for now)**
- Hosting customer code permanently (we clone, index, work, then GC).
- Building our own LLM. We orchestrate, not train.
- A full IDE — we ship a web workspace; deeper IDE integration lives in editor plugins.

## 2. Architectural style

- **Clean Architecture + DDD**. Domain layer is pure Python. Infrastructure is replaceable.
- **Async-first**. FastAPI + SQLAlchemy 2.0 async + `redis.asyncio` + `httpx.AsyncClient`.
- **Event-driven where natural**. Long-running work (ingest, embed, agent runs) goes
  through Celery + Redis. The API never blocks on these.
- **Hexagonal ports**. `LLMProvider`, `VectorStore`, `Sandbox`, `GitProvider`,
  `EmbeddingModel` are interfaces; concrete classes live in `infrastructure/`.

## 3. Layers

```
api/v1/*       → thin HTTP routers (FastAPI). Validate, authn/authz, delegate.
application/*  → use-case orchestrators. Cross-aggregate workflows.
domain/<ctx>/  → entities, value objects, domain services, repository interfaces.
infrastructure → SQLAlchemy repos, Redis, Qdrant, LLM clients, sandbox, git.
core/          → settings, logging, security primitives, exceptions, middleware.
```

Rules:
- `domain` imports nothing from `infrastructure` or `api`.
- `application` may import `domain` and interface types only.
- `api` may import `application` + `core`.
- `infrastructure` implements interfaces declared in `domain`.

## 4. Services (logical)

| Service       | Responsibility                                          | Phase |
|---------------|---------------------------------------------------------|-------|
| api           | HTTP/WS gateway, authn/authz, routing                   | 1     |
| worker        | Celery: ingest, embed, agent runs, PR gen, reviews      | 2+    |
| sandbox       | Isolated container pool for code execution              | 5     |
| frontend      | React SPA workspace                                     | 1     |

In dev, all run as containers in one Compose network. In prod, each is its own
Kubernetes Deployment with independent HPA.

## 5. Data stores

| Store      | Purpose                                                |
|------------|--------------------------------------------------------|
| Postgres   | System of record: users, repos, runs, audit            |
| Redis      | Cache, rate-limit counters, Celery broker/backend, pub/sub |
| Qdrant     | Vector store for code embeddings                       |
| Object Store (S3-compat, Phase 2+) | Repo snapshots, artifacts, large blobs |

## 6. Cross-cutting

- **Auth**: JWT access token (short TTL) + opaque refresh token (DB-backed, revocable).
  RBAC roles: `admin`, `member`, `viewer` in Phase 1; tenant/org-scoped in Phase 10.
- **Observability**: OpenTelemetry SDK auto-instruments FastAPI, SQLAlchemy, Redis, httpx.
  Logs are JSON via structlog with request_id + trace_id correlation. Prometheus
  `/metrics` endpoint on api + worker.
- **Configuration**: Pydantic Settings, loaded from env. `.env.example` is the contract.
- **Errors**: domain raises typed exceptions; api layer maps them to HTTP via one handler.

## 7. Security posture

See [SECURITY.md](./SECURITY.md). Highlights:
- Argon2 password hashing (passlib).
- JWT signed with HS256 in dev, RS256 in prod (key rotation via JWKS in Phase 10).
- Per-IP + per-user sliding-window rate limit via Redis.
- Audit log for every authn event and sensitive mutation.
- Sandboxed execution is opt-in, default-deny network, CPU/mem/time caps.

## 8. Deployment

- Dev: `docker compose up`.
- Prod: Helm chart in `infra/helm/` (Phase 9). Postgres + Qdrant typically run as
  managed services in production; Helm chart supports both modes.

## 9. ADRs

Decisions that fork architecture get an ADR in `docs/adr/NNNN-title.md`. First ADR
(Phase 1): "Use SQLAlchemy 2.0 async over Tortoise/SQLModel".
