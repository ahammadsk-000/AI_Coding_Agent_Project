# Build phases

Each phase ships a slice that is **independently runnable and tested**. The previous
phase's API contracts are immutable unless an ADR explicitly supersedes them.

## Phase 1 — Foundations  ← CURRENT
- Monorepo, Docker Compose dev stack
- FastAPI app: config, logging, exceptions, request-id, CORS, metrics endpoint
- Postgres + async SQLAlchemy + Alembic + initial migration
- Redis client
- JWT auth (access + refresh), Argon2 hashing
- RBAC scaffolding (roles, user_roles, `require_role` dependency)
- Audit log table + middleware
- Endpoints: `/health`, `/ready`, `/metrics`, `/api/v1/auth/{register,login,refresh,logout}`, `/api/v1/users/me`
- React + Vite + TS + Tailwind + Zustand + React Query + shadcn-style UI
- Routes: `/login`, `/register`, `/dashboard` (auth-gated)
- Nginx reverse proxy
- Pytest suite (unit + integration via testcontainers)
- GitHub Actions: lint, type-check, test, build images

## Phase 2 — Repository ingestion
- `repositories` domain: clone, snapshot, language detection
- Tree-sitter parsers for ts, js, py, go, rust, java
- Symbol extraction (functions, classes, imports)
- Dependency graph (call graph + import graph) persisted in Postgres
- Semantic chunking (AST-aware) writing into `code_chunks`
- Embedding pipeline → Qdrant collection per repo
- Celery workers + Flower
- API: `POST /repos`, `GET /repos/{id}`, `POST /repos/{id}/ingest`, ingest status SSE

## Phase 3 — RAG + context engine
- Hybrid retrieval (BM25 via Postgres tsvector + dense via Qdrant + reranker)
- Context budgeter (token-aware packing)
- File-aware conversation context (open files, cursor, recent edits)
- API: `POST /search`, `POST /context/build`

## Phase 4 — Agents + tool calling
- `LLMProvider` interface; Ollama + OpenAI-compatible adapters
- LangGraph state machine: planner → researcher → coder → tester → reviewer
- Tools: `read_file`, `write_file`, `grep`, `glob`, `shell_exec`, `web_search`
- Streaming agent runs over WebSocket
- Run/step persistence + replay

## Phase 5 — Sandboxed terminal
- Docker-in-Docker sandbox pool (firecracker as Phase 10 upgrade)
- Network: default deny, allowlist per repo
- CPU/mem/time caps via cgroups
- Command approval workflow for destructive ops
- Streaming stdout/stderr over WS

## Phase 6 — GitHub integration
- GitHub App + OAuth login
- Webhook receiver (push, PR, issue_comment)
- PR generation (branch, diff, body, draft)
- AI code review comments via Checks API

## Phase 7 — Memory + multi-agent
- Per-user, per-project, per-conversation memory tiers
- Vector + summary memory with decay
- CrewAI for roleplay-style multi-agent (research vs coding crews)

## Phase 8 — Observability
- OTel collector, Tempo, Prometheus, Loki, Grafana dashboards
- Agent execution traces (spans per tool call)
- Token usage + cost metrics per user/org

## Phase 9 — Kubernetes
- Helm chart, values for dev/staging/prod
- HPA, PDB, NetworkPolicy
- Cert-manager + ingress-nginx
- GitOps via Argo CD (optional)

## Phase 10 — Enterprise
- Multi-tenant orgs + workspaces
- Fine-grained RBAC (resource-level)
- SSO (OIDC) + SCIM
- Billing-ready metering hooks
- Plugin/tool marketplace
