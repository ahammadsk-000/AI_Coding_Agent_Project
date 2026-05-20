# AI Coding Agent Platform

An open, production-grade, Kubernetes-deployable AI coding platform — think Cursor /
OpenHands / Continue.dev / Devin, built as an extensible monorepo.

> **Status:** Phase 2 of 10 — repository ingestion (clone → tree-sitter parse →
> AST-aware chunk → embeddings → Qdrant), Celery worker pool, SSE progress.
> See [docs/PHASES.md](docs/PHASES.md) for the full roadmap.

## What it does (target state)

- 💬 Streaming chat over your codebase with multi-file context
- 🧠 Repository ingestion, AST parsing (tree-sitter), embeddings → Qdrant
- 🔎 Hybrid RAG (BM25 + dense) with token-aware context budgeting
- 🤖 Multi-agent workflows (planner / coder / tester / reviewer) on LangGraph
- 🖥️ Sandboxed shell execution in disposable Docker containers
- 🔗 GitHub App: clone, branch, PR generation, AI code review comments
- 🪪 JWT + RBAC, audit logs, per-IP and per-user rate limits
- 📊 OpenTelemetry traces, Prometheus metrics, Loki logs, Grafana dashboards
- ☸️ Helm chart for production; Docker Compose for dev

## Quick start (dev)

Prereqs: Docker Desktop (or Docker + Compose v2), GNU Make optional.

```bash
cp .env.example .env
docker compose up --build
```

Then open:
- Frontend → http://localhost:3000
- API docs → http://localhost:8000/docs
- Health   → http://localhost:8000/health
- Metrics  → http://localhost:8000/metrics
- Qdrant   → http://localhost:6333/dashboard
- Flower (Celery) → http://localhost:5555

Default seeded admin (created on first boot if `SEED_ADMIN=true`):
- email: `admin@local.test`
- password: `changeme123!`

Change the password immediately via `PATCH /api/v1/users/me` or by registering a new
admin and disabling the seed.

## Repository layout

```
apps/
  api/        FastAPI backend (Python 3.12)
  web/        React + Vite + TypeScript frontend
  worker/     Celery workers (Phase 2+)
  sandbox/    Sandbox runner image (Phase 5)
packages/     Shared libraries (Phase 7+)
infra/
  docker/     Init scripts, base images
  nginx/      Reverse proxy
  k8s/        Raw K8s manifests (Phase 9)
  helm/       Helm chart (Phase 9)
docs/         Architecture, ADRs, runbooks
scripts/      Dev/CI helpers
```

## Development

```bash
make dev        # docker compose up --build
make api-sh     # shell into the api container
make api-test   # run backend tests
make api-fmt    # ruff format + check
make api-mig msg="add foo"  # alembic revision --autogenerate
make api-upgrade            # alembic upgrade head
make web-dev    # run vite dev server outside docker
```

Without Make, the equivalent commands are listed in [Makefile](./Makefile).

## Testing

- Backend: `pytest` with `pytest-asyncio`. Integration tests use `testcontainers`
  to spin up real Postgres + Redis. Run: `make api-test`.
- Frontend: `vitest` + React Testing Library. Run: `pnpm --filter web test`.

## Deploying

Phase 1 ships Docker Compose for local + a single-node staging. Helm chart lands in
Phase 9.

## License

MIT (placeholder — pick your final license before publishing).
