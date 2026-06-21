# AI Coding Agent Platform — End-to-End Guide

> A complete walkthrough of this codebase for a new engineer. Read this top to
> bottom and you will understand **what the project is, how it is structured, what
> every file does, and how the pieces fit together**.

---

## 1. What is this project?

An **open, self-hostable AI coding platform** — comparable to Cursor, OpenHands,
Continue.dev, or Devin — built as an extensible monorepo.

The core idea: **bring your own LLM** (local [Ollama](https://ollama.com) or OpenAI),
**point it at your git repositories**, and then **chat, search, review, and run code**
against them with full Retrieval-Augmented Generation (RAG) and a hardened code sandbox.

### What you can do with it

- **Ingest a repository** — clone it, parse it with tree-sitter, chunk it AST-aware,
  embed every chunk, and store the vectors in Qdrant.
- **Search the code** — hybrid search (dense vector similarity + Postgres full-text),
  fused with Reciprocal Rank Fusion, optionally reranked with a cross-encoder.
- **Chat with an agent** — a multi-turn LLM agent that retrieves context (RAG), calls
  read-only tools (`search_code`, `read_file`, `list_files`), streams tokens over
  WebSocket, and remembers durable facts.
- **Run commands in a sandbox** — disposable, network-isolated, non-root, resource-capped
  Docker containers, gated by a command-safety policy.
- **Create & review GitHub PRs** — generate a PR from file changes, or have the LLM
  review an existing PR's diff.
- **Store memory** — durable user/project/conversation-scoped facts recalled by vector search.
- **Observe everything** — Prometheus metrics, token/cost accounting, Grafana dashboards.
- **Deploy** — Docker Compose for local/single-node, or a Helm chart for Kubernetes.

### Project status

Phases **1–9 of 10 are complete**. Phase 10 (enterprise: multi-tenant orgs, fine-grained
RBAC, SSO/SCIM, billing, plugin marketplace) is planned. See
[docs/PHASES.md](docs/PHASES.md) for the full roadmap.

| Phase | Capability | Status |
|------:|------------|:------:|
| 1 | Monorepo foundations: FastAPI + React, JWT auth + RBAC, rate limits, Docker stack | ✅ |
| 2 | Repository ingestion: clone → tree-sitter parse → AST-aware chunk → embeddings → Qdrant, Celery workers, live SSE progress | ✅ |
| 3 | Hybrid search: Qdrant dense + Postgres BM25, Reciprocal Rank Fusion, cross-encoder reranker | ✅ |
| 4 | Chat / RAG: LLM provider abstraction (Ollama + OpenAI), WebSocket token streaming, conversation history | ✅ |
| 5 | Sandbox: hardened, disposable Docker containers (network-isolated, non-root, resource-capped) with a command-policy gate | ✅ |
| 6 | GitHub: PR generation and AI code review via PAT | ✅ |
| 7 | Memory: project / user memory store | ✅ |
| 8 | Observability: Prometheus metrics (incl. Celery multiprocess), cost accounting, Grafana dashboards | ✅ |
| 9 | Deployment: Helm chart with HPA / PDB / NetworkPolicy / Ingress | ✅ |
| 10 | Enterprise: orgs, fine-grained RBAC, SSO/SCIM, billing, marketplace | ⏳ planned |

---

## 2. Technology stack at a glance

### Backend (`apps/api`)

| Concern | Choice |
|---------|--------|
| Language | Python 3.12 |
| Web framework | FastAPI 0.115 (async) |
| ASGI server | uvicorn |
| ORM | SQLAlchemy 2.0 (async, `Mapped[...]` typing) |
| DB driver | asyncpg (app), psycopg (Alembic migrations) |
| Migrations | Alembic |
| Background jobs | Celery 5.4 (Redis broker/backend) |
| Database | PostgreSQL 16 (with `citext`, `pgcrypto`, `pg_trgm` extensions) |
| Cache / broker / pub-sub | Redis 7 (`redis.asyncio`) |
| Vector store | Qdrant v1.11 |
| Embeddings | sentence-transformers (`BAAI/bge-small-en-v1.5`, 384-dim) or OpenAI |
| Reranker | sentence-transformers CrossEncoder (`ms-marco-MiniLM-L-6-v2`) |
| Code parsing | tree-sitter (via `tree-sitter-languages` prebuilt grammars) |
| Token counting | tiktoken (`cl100k_base`) |
| LLM providers | Ollama (local) + OpenAI (and OpenAI-compatible servers) |
| Sandbox | Docker SDK for Python (sibling containers) |
| Auth | JWT (HS256 dev / RS256 prod), Argon2 password hashing (passlib) |
| Logging | structlog (JSON in prod, colored console in dev) |
| Metrics | prometheus-client |
| HTTP client | httpx (async) |

### Frontend (`apps/web`)

| Concern | Choice |
|---------|--------|
| Language | TypeScript 5.6 |
| UI library | React 18.3 |
| Build tool | Vite 5.4 |
| Router | React Router v6 |
| Server state | TanStack React Query 5 |
| Client state | Zustand 5 (auth persisted to localStorage) |
| Styling | Tailwind CSS 3.4 (dark mode via CSS variables) |
| UI components | Custom shadcn-style `Button` / `Input` (no heavy UI lib) |
| Code highlighting | react-syntax-highlighter (Prism.js, `vscDarkPlus`) |
| Icons | lucide-react |
| Testing | Vitest + React Testing Library + jsdom |
| Package manager | pnpm 9 |

### Infrastructure

- **Docker Compose** — local/single-node full stack (9 services).
- **Nginx** — reverse proxy (API + WebSocket + web), and the production SPA server.
- **Prometheus + Grafana** — metrics scraping and dashboards.
- **Flower** — Celery task monitor.
- **Helm chart** (`infra/helm/aca`) — Kubernetes deployment with HPA, PDB, NetworkPolicy, Ingress.
- **GitHub Actions** — CI (lint/test/build) and weekly security audits.

---

## 3. Architecture overview

The backend follows **Clean Architecture + Domain-Driven Design**, async-first, with
hexagonal "ports and adapters". The layering is the single most important thing to
understand:

```
┌─────────────────────────────────────────────────────────────┐
│  api/v1/*           Thin HTTP & WebSocket routers            │  ← transport
├─────────────────────────────────────────────────────────────┤
│  domain/<context>/  Business logic, organized per bounded    │  ← the "what"
│    ├── models.py        SQLAlchemy ORM entities             │
│    ├── repository.py     Data-access layer (DB queries)     │
│    ├── schemas.py        Pydantic DTOs (request/response)   │
│    └── service.py        Use-case orchestration             │
├─────────────────────────────────────────────────────────────┤
│  infrastructure/*   Concrete adapters: LLM, embeddings,     │  ← the "how"
│                     Qdrant, Redis, git, github, parsers,    │
│                     sandbox, db engine                      │
├─────────────────────────────────────────────────────────────┤
│  core/*             Cross-cutting: config, security,        │  ← plumbing
│                     logging, metrics, cost, exceptions      │
└─────────────────────────────────────────────────────────────┘
```

**The golden rule of the layered pattern** (you'll see it in every domain):

- `models.py` = SQLAlchemy ORM tables (the database shape).
- `repository.py` = the only place that touches the DB session for that context.
- `schemas.py` = Pydantic models for the API boundary (never leaks ORM objects).
- `service.py` = orchestrates repositories + infrastructure to fulfill a use case.

### Runtime services

| Service | Role | Image |
|---------|------|-------|
| `api` | HTTP/WebSocket gateway (FastAPI) | built from `apps/api` |
| `worker` | Celery worker for ingestion/embedding | **same image** as `api` |
| `web` | React SPA | built from `apps/web` |
| `postgres` | System of record | `postgres:16` |
| `redis` | Cache, rate-limit store, Celery broker, pub/sub | `redis:7` |
| `qdrant` | Vector embeddings store | `qdrant:v1.11.3` |
| `flower` | Celery monitoring UI | from `apps/api` |
| `nginx` | Reverse proxy | `nginx` |
| `prometheus` / `grafana` | Metrics + dashboards | official images |

> **Note:** The Celery worker and the sandbox both run *from the API image* — there are
> **no** separate `apps/worker` or `apps/sandbox` directories. The sandbox spawns
> *sibling* Docker containers via the mounted Docker socket.

### A typical request flow (ingestion example)

1. User registers a repo → `POST /api/v1/repositories` → `RepositoryService.create()`
   inserts a `Repository` row (status `new`).
2. User triggers ingest → `RepositoryService.enqueue_ingest()` creates an `IngestJob`
   row and dispatches a **Celery task** (`app.tasks.ingest`).
3. The **worker** clones the repo, walks files, detects language, extracts symbols with
   tree-sitter, chunks AST-aware, embeds chunks, upserts vectors to **Qdrant**, and
   publishes **progress events on Redis pub/sub**.
4. The frontend streams those progress events live via **Server-Sent Events (SSE)**.
5. When done, the repo flips to status `ready` and is searchable / chattable.

---

## 4. Repository layout

```
AI_Coding_Agent_Project/
├── apps/
│   ├── api/                  FastAPI backend (Python 3.12)
│   └── web/                  React + Vite + TypeScript frontend
├── infra/
│   ├── docker/               Postgres init scripts
│   ├── nginx/                Reverse proxy + SPA server configs
│   ├── prometheus/           Scrape config
│   ├── grafana/              Datasource + dashboard provisioning
│   └── helm/aca/             Kubernetes Helm chart (Phase 9)
├── docs/                     ARCHITECTURE, PHASES, SECURITY, ADRs
├── scripts/                  Dev/CI helpers
├── .github/workflows/        CI + security pipelines
├── docker-compose.yml        Full local stack
├── Makefile                  Developer convenience commands
├── Ai_coding_agent.bat       Windows one-click launcher
├── Ai_coding_agent_stop.bat  Windows stop script
├── .env.example              Configuration contract
└── README.md
```

---

## 5. Backend deep dive (`apps/api`)

### 5.1 Application entry & plumbing

| File | What it does |
|------|--------------|
| [apps/api/app/main.py](apps/api/app/main.py) | FastAPI application factory and ASGI entrypoint. Composes CORS, metrics, rate-limit, and request-ID middleware; manages DB/Redis lifespan startup/shutdown; optionally seeds an admin user on first boot; exposes `/metrics` (Prometheus) and `/health`. |
| [apps/api/app/core/config.py](apps/api/app/core/config.py) | Centralized **Pydantic Settings** loaded from environment variables. Defines every config group: API, security (JWT algo/TTL, Argon2), database (asyncpg), Redis, Qdrant, LLM providers, ingestion caps, Celery, GitHub PAT, sandbox limits, rate limits. Also derives the **sync DSN** used by Alembic. The `.env.example` is the human-readable contract for this file. |
| [apps/api/app/core/security.py](apps/api/app/core/security.py) | Cryptographic primitives: Argon2 password hashing (passlib), JWT access-token creation/decoding (configurable TTL + subject claim), and opaque SHA256-hashed refresh tokens. Includes token-type and expiry validation. |
| [apps/api/app/core/dependencies.py](apps/api/app/core/dependencies.py) | FastAPI dependency injectors: async DB session, current-user extraction from the `Bearer` token, and **RBAC role guards** that raise `ForbiddenError` when a user lacks a required role. |
| [apps/api/app/core/exceptions.py](apps/api/app/core/exceptions.py) | Typed domain exception hierarchy (`DomainError` base → `NotFoundError` 404, `ConflictError` 409, `UnauthorizedError` 401, `ForbiddenError` 403, `RateLimitedError` 429, `ValidationDomainError` 422). A single FastAPI handler serializes them to JSON with code, message, details, and `request_id`. |
| [apps/api/app/core/logging.py](apps/api/app/core/logging.py) | Structured logging via **structlog**, with context-var `request_id`/`trace_id` propagation. Redacts sensitive keys (password, token, api_key…). JSON renderer in production, colored console in development; bridges stdlib loggers (uvicorn, SQLAlchemy). |
| [apps/api/app/core/metrics.py](apps/api/app/core/metrics.py) | Prometheus metric definitions following the `aca_<area>_<thing>_<unit>` convention — counters (HTTP requests, LLM calls, tokens, tool invocations, chat messages, search, ingest, memory) and latency histograms. |
| [apps/api/app/core/cost.py](apps/api/app/core/cost.py) | Token counting with tiktoken (`cl100k_base`) and USD cost estimation from a static per-1M-token price table for OpenAI models. Local models default to free. |

### 5.2 API routing & middleware

| File | What it does |
|------|--------------|
| [apps/api/app/api/router.py](apps/api/app/api/router.py) | Top-level router that mounts all v1 sub-routers under `/api/v1` (health, auth, users, repositories, search, chat, memory, sandbox, github). |
| [apps/api/app/api/middleware/request_id.py](apps/api/app/api/middleware/request_id.py) | Extracts or generates a UUID4 `X-Request-ID`, binds it to structlog contextvars, and echoes it in the response — every log line in a request carries the same correlation ID. |
| [apps/api/app/api/middleware/metrics.py](apps/api/app/api/middleware/metrics.py) | Records HTTP request count and latency per `(method, route-template, status)`. Skips `/metrics` itself to avoid self-referential noise. |
| [apps/api/app/api/middleware/rate_limit.py](apps/api/app/api/middleware/rate_limit.py) | **Sliding-window rate limiter** (60s) backed by Redis, keyed per `(subject, route_group)` where the subject is the user ID (authed) or client IP (anon). Different limits per group (auth 10/min, authed API 300/min, anon 30/min). **Fails open** if Redis is down. |

### 5.3 API endpoints (`apps/api/app/api/v1`)

These are **thin** routers — they validate input, call a domain service, and serialize the result.

| File | Endpoints |
|------|-----------|
| [auth.py](apps/api/app/api/v1/auth.py) | `register`, `login` (logs IP/user-agent), `refresh`, `logout`. Returns a user + token pair. |
| [users.py](apps/api/app/api/v1/users.py) | `GET /me` (current user), `PATCH /me` (update profile). |
| [repositories.py](apps/api/app/api/v1/repositories.py) | Register/list/get/delete repos; enqueue ingest jobs; list/poll job status; **stream job progress via SSE**; file & chunk preview endpoints. |
| [search.py](apps/api/app/api/v1/search.py) | Hybrid/dense/lexical search across the user's repos (optional rerank); `context/build` combines search + token-aware packing under a `max_tokens` budget. |
| [chat.py](apps/api/app/api/v1/chat.py) | REST CRUD for conversations and messages; **WebSocket** for streaming agent replies (auth via `?access_token=` query param, JSON frame protocol). |
| [memory.py](apps/api/app/api/v1/memory.py) | List/create/delete durable memories scoped to user/project/conversation, with importance scores. |
| [sandbox.py](apps/api/app/api/v1/sandbox.py) | `classify` a command (verdict + reason); **WebSocket** to stream isolated container execution with approval-gate enforcement. |
| [github.py](apps/api/app/api/v1/github.py) | GitHub `status`, `create PR`, and `review PR` — all using the server-side PAT. |
| [health.py](apps/api/app/api/v1/health.py) | `ping`, `ready` (checks Postgres/Redis connectivity), and overall status. |

### 5.4 Domain layer (`apps/api/app/domain`)

Each bounded context follows the `models / repository / schemas / service` pattern.

#### `auth` — Authentication & credentials
- [service.py](apps/api/app/domain/auth/service.py) — `AuthService` verifies credentials
  (Argon2), issues token pairs, **rotates refresh tokens with single-use revocation**, and
  writes audit events (`login_failed`, `login_success`, `token_refresh`, `logout`).
- [schemas.py](apps/api/app/domain/auth/schemas.py) — `LoginRequest`, `TokenPair`,
  `RefreshRequest`, `LoginResponse`.

#### `users` — Accounts, roles, audit
- [models.py](apps/api/app/domain/users/models.py) — `Role`, `User` (email as **CITEXT**,
  eager-loaded roles), `RefreshToken` (hashed, revocable), `AuditLog` (JSONB metadata).
- [repository.py](apps/api/app/domain/users/repository.py) — `UserRepository`,
  `RoleRepository`, `RefreshTokenRepository`, `AuditLogRepository`.
- [schemas.py](apps/api/app/domain/users/schemas.py) — `RoleRead`, `UserCreate`,
  `UserUpdate`, `UserRead`.
- [service.py](apps/api/app/domain/users/service.py) — `UserService.register()` (dedupes
  email, hashes password, auto-assigns `member`/`admin` role) and `update_profile()`.

#### `repositories` — Code ingestion & index
- [models.py](apps/api/app/domain/repositories/models.py) — `Repository`, `RepositoryFile`,
  `CodeSymbol`, `CodeChunk`, `IngestJob` (with status enums and stats counters).
- [repository.py](apps/api/app/domain/repositories/repository.py) — `RepositoryRepo`,
  `IngestJobRepo` (progress updates), `FileRepo` (bulk staging of files/symbols/chunks
  during ingest).
- [schemas.py](apps/api/app/domain/repositories/schemas.py) — `RepositoryCreate/Read`,
  `IngestJobRead`, `IngestEvent` (the SSE payload), `RepositoryFileRead`, `CodeChunkPreview`.
- [service.py](apps/api/app/domain/repositories/service.py) — `RepositoryService`:
  create/list/get/delete, `enqueue_ingest()` (creates job + dispatches Celery task), job
  tracking, and file/chunk listing for the detail page. Enforces `(owner, url)` uniqueness
  and ownership checks.

#### `search` — Hybrid retrieval & RAG context (Phase 3)
- [service.py](apps/api/app/domain/search/service.py) — `SearchService` implements the
  full retrieval pipeline: **(1)** dense kNN via Qdrant, **(2)** sparse Postgres FTS
  (`plainto_tsquery` + `ts_rank_cd` on a GIN-indexed `content_tsv` column), **(3)**
  **Reciprocal Rank Fusion (RRF, k=60)**, **(4)** optional cross-encoder rerank.
- [context.py](apps/api/app/domain/search/context.py) — `pack_context()` groups hits by
  file, merges overlapping/adjacent line ranges, and greedily packs them under a token
  budget for prompt injection.
- [schemas.py](apps/api/app/domain/search/schemas.py) — `SearchRequest/Response`,
  `SearchHit` (with dense/lexical/rerank sub-scores), `ContextRequest/Response`, `ContextFile`.

#### `chat` — Conversational agent (Phase 4)
- [models.py](apps/api/app/domain/chat/models.py) — `Conversation` (owner, title,
  `repository_ids`, provider/model) and `Message` (role enum, content, tool_calls,
  citations, token_count).
- [repository.py](apps/api/app/domain/chat/repository.py) — `ConversationRepo` (with last-
  message preview + count) and `MessageRepo` (`to_openai_history()` formats messages for
  the LLM).
- [schemas.py](apps/api/app/domain/chat/schemas.py) — REST DTOs plus the **WebSocket event
  schemas** (`WsToken`, `WsToolCallStart/Result`, `WsCitations`, `WsDone`, `WsError`).
- [service.py](apps/api/app/domain/chat/service.py) — `ChatService` runs the **agent loop
  (up to 5 rounds)**: embed the user message → fetch RAG context (capped ~1500 tokens) →
  inject a system prompt with the repo inventory + durable memories → stream the LLM →
  execute tool calls → persist every message. Detects chit-chat (skips RAG) and "remember X"
  cues (auto-saves a memory).
- [tools.py](apps/api/app/domain/chat/tools.py) — Three **read-only** agent tools as
  JSON-schema + handlers: `search_code`, `read_file`, `list_files`. Each returns
  `(result, summary, citations)`.

#### `memory` — Durable facts (Phase 7)
- [models.py](apps/api/app/domain/memory/models.py) — `Memory` (scope enum
  user/project/conversation, source explicit/extracted, importance, `vector_id`, access tracking).
- [repository.py](apps/api/app/domain/memory/repository.py) — `MemoryRepo` with CRUD,
  `mark_accessed()`, and exact-text `find_duplicate()` dedup.
- [schemas.py](apps/api/app/domain/memory/schemas.py) — `MemoryCreate`, `MemoryRead`.
- [service.py](apps/api/app/domain/memory/service.py) — `MemoryService`: `remember()`
  (dedupe → embed → upsert to Qdrant with owner/scope payload filters), `recall()` (vector
  search filtered by owner/scope, marks accessed, sorts by score), `forget()`.

#### `github` — PR creation & review (Phase 6)
- [service.py](apps/api/app/domain/github/service.py) — `GitHubService`: `status()`,
  `create_pr()` (branch off base SHA → commit each file → open PR), `review_pr()` (fetch
  diff capped ~24k chars → call the LLM → optionally post the review as a PR comment).
- [schemas.py](apps/api/app/domain/github/schemas.py) — `GitHubStatus`, `FileChange`,
  `CreatePRRequest/Response`, `ReviewPRRequest/Response`.

#### `sandbox` — Command execution (Phase 5)
- [schemas.py](apps/api/app/domain/sandbox/schemas.py) — `ClassifyRequest`,
  `ClassifyResponse` (verdict allow/approval/blocked), `SandboxRunRequest`. (The execution
  logic lives in `infrastructure/sandbox`.)

### 5.5 Infrastructure layer (`apps/api/app/infrastructure`)

Concrete adapters behind the domain's abstract "ports".

#### Database
- [db/base.py](apps/api/app/infrastructure/db/base.py) — SQLAlchemy 2.0 async
  `DeclarativeBase` plus `UUIDPkMixin` and `TimestampMixin`.
- [db/session.py](apps/api/app/infrastructure/db/session.py) — Process-wide `AsyncEngine`
  (pool_size=10, max_overflow=20, pre-ping), `session_factory()`, `session_iter()` (FastAPI
  dependency), `dispose_engine()`.

#### Embeddings (provider abstraction)
- [embeddings/base.py](apps/api/app/infrastructure/embeddings/base.py) — `EmbeddingProvider`
  Protocol (`model_name`, `dimension`, `embed_texts`).
- [embeddings/local.py](apps/api/app/infrastructure/embeddings/local.py) — Thread-safe
  singleton wrapping sentence-transformers; default `BAAI/bge-small-en-v1.5` (384-dim,
  CPU-friendly), normalized embeddings, lazy double-checked loading.
- [embeddings/openai_provider.py](apps/api/app/infrastructure/embeddings/openai_provider.py)
  — OpenAI-compatible embeddings via httpx (batches of 256), with a model→dimension map.
- [embeddings/reranker.py](apps/api/app/infrastructure/embeddings/reranker.py) — Cross-encoder
  reranker (`ms-marco-MiniLM-L-6-v2`, ~22 MB) scoring `(query, document)` pairs, lazy-loaded.

#### LLM (provider abstraction)
- [llm/base.py](apps/api/app/infrastructure/llm/base.py) — `LLMProvider` Protocol plus the
  shared types: `ChatMessage`, `ToolDef`, `ToolCall`, `StreamChunk`, `ChatResponse`.
- [llm/factory.py](apps/api/app/infrastructure/llm/factory.py) — `get_llm_provider()` returns
  an `OllamaProvider` or `OpenAIProvider` based on config, with per-conversation model override.
- [llm/ollama.py](apps/api/app/infrastructure/llm/ollama.py) — Talks to local Ollama
  `/api/chat`. Streams NDJSON, supports tool calling (Ollama 0.3+), auto-retries without
  tools on 400, normalizes tool-call formats, `keep_alive: 30m` to avoid cold-starts.
- [llm/openai_provider.py](apps/api/app/infrastructure/llm/openai_provider.py) — Wraps
  `AsyncOpenAI`; works with OpenAI or any compatible server (vLLM, LM Studio) via `base_url`.
  Reassembles streamed tool-call argument fragments.

#### Code parsing & chunking
- [parsers/language.py](apps/api/app/infrastructure/parsers/language.py) — Extension→language
  map (30+ languages) with filename special-cases (Dockerfile, Makefile, …).
- [parsers/tree_sitter.py](apps/api/app/infrastructure/parsers/tree_sitter.py) — Tree-sitter
  AST parsing via prebuilt `tree-sitter-languages` grammars; per-language capture queries
  extract function/class/method/interface symbols → `SymbolSpan`. Falls back gracefully.
- [parsers/chunker.py](apps/api/app/infrastructure/parsers/chunker.py) — **AST-aware chunker**
  using tiktoken for token budgeting: emit symbol-sized chunks, split oversized symbols via
  line-window, gap-fill between symbols, fall back to pure line-window for unsupported langs.

#### External services
- [git/clone.py](apps/api/app/infrastructure/git/clone.py) — Safe bounded cloning via
  GitPython: URL validation, `--depth=1 --single-branch`, size cap, `.git` removal,
  `detect_default_branch()` via `git ls-remote --symref`.
- [github/client.py](apps/api/app/infrastructure/github/client.py) — Thin async GitHub REST
  client (Bearer token): `whoami`, `get_repo`, branch/file ops, `create_pull`, `get_pull_diff`,
  `comment_on_issue`. Raises `GitHubError` on 4xx/5xx.
- [qdrant/client.py](apps/api/app/infrastructure/qdrant/client.py) — Thread-safe
  `QdrantService`: one collection per repo (`repo_<uuid>`), COSINE distance, HNSW config,
  payload indexes; `ensure_collection`, `upsert_chunks`, `search`, `delete_points`.
- [redis/client.py](apps/api/app/infrastructure/redis/client.py) — Process-wide
  `redis.asyncio` client singleton (`get_redis`, `close_redis`).

#### Sandbox (Phase 5)
- [sandbox/policy.py](apps/api/app/infrastructure/sandbox/policy.py) — Command classification
  via 15+ regex rules. **Hard-blocks** destructive patterns (`rm -rf /`, fork bombs, device
  writes, docker socket access, mounts); **requires approval** for network tools, package
  installs, `sudo`, recursive deletes, `git push`. Returns `allow`/`approval`/`blocked`.
- [sandbox/service.py](apps/api/app/infrastructure/sandbox/service.py) — `SandboxService`
  spawns **sibling Docker containers** with heavy isolation: `network_mode=none`,
  `cap_drop=ALL`, `no-new-privileges`, read-only root + tmpfs `/workspace`, non-root user,
  memory/CPU/pids caps, hard wall-clock timeout, auto-remove. `run_stream()` streams combined
  stdout/stderr + exit code over an asyncio queue with a watchdog.

### 5.6 Background tasks (`apps/api/app/tasks`)

| File | What it does |
|------|--------------|
| [tasks/celery_app.py](apps/api/app/tasks/celery_app.py) | Celery app factory: Redis broker/backend, task autodiscovery, model registration (so workers resolve ORM FKs), routing (ingest → `ingest` queue), multiprocess metrics server, JSON serialization, late acking. |
| [tasks/ingest.py](apps/api/app/tasks/ingest.py) | The **ingestion task**: shallow-clone → walk files (filter ignored dirs / size / allowed languages) → detect language → extract symbols → AST-aware chunk → batch-insert files/symbols/chunks → embed in batches → upsert to Qdrant → publish progress on Redis pub/sub → mark job complete. |
| [apps/api/app/worker_metrics.py](apps/api/app/worker_metrics.py) | Prometheus **multiprocess** aggregation for Celery: clears stale metric files and serves aggregated per-child metrics via `MultiProcessCollector` when `PROMETHEUS_MULTIPROC_DIR` is set. |

### 5.7 Database migrations (`apps/api/alembic`)

| File | What it creates |
|------|-----------------|
| [alembic.ini](apps/api/alembic.ini) | Alembic config; `sqlalchemy.url` is set dynamically to the **sync** DSN (psycopg) for migrations. |
| [alembic/env.py](apps/api/alembic/env.py) | Migration environment; imports domain models onto `Base.metadata`, supports offline/online modes. |
| [versions/0001_initial.py](apps/api/alembic/versions/0001_initial.py) | Auth/RBAC foundation: `roles`, `users` (email CITEXT), `user_roles`, `refresh_tokens`, `audit_logs`. Enables `pgcrypto`, `citext`, `pg_trgm`. |
| [versions/0002_repositories.py](apps/api/alembic/versions/0002_repositories.py) | Ingestion schema: `repositories`, `repository_files`, `code_symbols`, `code_chunks`, `ingest_jobs` + their enums. |
| [versions/0003_search.py](apps/api/alembic/versions/0003_search.py) | Adds a generated STORED `content_tsv` column + GIN index on `code_chunks` for full-text search. |
| [versions/0004_chat.py](apps/api/alembic/versions/0004_chat.py) | Chat schema: `conversations`, `messages` (+ `message_role` enum). |
| [versions/0005_memory.py](apps/api/alembic/versions/0005_memory.py) | Memory schema: `memories` (+ scope/source enums, indexes). |

### 5.8 Backend build & tests

| File | What it does |
|------|--------------|
| [apps/api/pyproject.toml](apps/api/pyproject.toml) | Package metadata (`aca-api`, Python 3.12+), runtime dependencies, and dev extras (pytest, mypy, ruff). |
| [apps/api/Dockerfile](apps/api/Dockerfile) | Multi-stage build (base → deps → dev/prod). Installs system deps (libpq, git for GitPython), a dev stage with hot-reload, and a prod stage with a non-root user (uid 10001), 2 uvicorn workers, and a healthcheck. |
| `apps/api/tests/` | pytest suite: `conftest.py` (fixtures), `test_auth.py`, `test_chunker.py`, `test_clone_validation.py`, `test_health.py`, `test_language_detect.py`, `test_repositories_api.py`, `test_security_unit.py`. Integration tests use `testcontainers` for real Postgres + Redis. |

---

## 6. Frontend deep dive (`apps/web`)

A modern, type-safe React SPA. Key patterns: **TanStack Query** for server state,
**Zustand** for auth (persisted), **SSE** for ingest progress, **WebSocket** for chat &
sandbox streaming, automatic **token refresh on 401**.

### 6.1 App shell & config

| File | What it does |
|------|--------------|
| [src/main.tsx](apps/web/src/main.tsx) | React 18 root: `BrowserRouter` + `QueryClientProvider` (retry 1, 30s staleTime, no refetch on focus) + StrictMode. |
| [src/App.tsx](apps/web/src/App.tsx) | Route table: public `/login`, `/register`; everything else wrapped in `RequireAuth + AppShell` (`/dashboard`, `/repositories/:id`, `/search`, `/chat/:id`, `/memory`, `/sandbox`, `/github`). |
| [src/index.css](apps/web/src/index.css) | Tailwind directives + light/dark CSS variables. |
| [src/env.d.ts](apps/web/src/env.d.ts) | Vite env typings (`VITE_API_BASE_URL`, `VITE_WS_BASE_URL`). |
| [index.html](apps/web/index.html) | SPA entry (`#root`, dark class, Vite module script). |
| [vite.config.ts](apps/web/vite.config.ts) | `@/` → `src/` alias; Vitest config (jsdom, globals, setup file). |
| [tsconfig.json](apps/web/tsconfig.json) | ES2022, strict, path aliasing, `react-jsx`. |
| [tailwind.config.ts](apps/web/tailwind.config.ts) | Dark mode via class; semantic color tokens wired to CSS variables. |
| [postcss.config.js](apps/web/postcss.config.js) | Tailwind + Autoprefixer. |
| [.eslintrc.cjs](apps/web/.eslintrc.cjs) | ESLint: TS + react-hooks + react-refresh. |
| [package.json](apps/web/package.json) | Dependencies & scripts (`dev`, `build` = `tsc --noEmit && vite build`, `test`, `lint`). |

### 6.2 Layout & UI components

| File | What it does |
|------|--------------|
| [src/components/layout/require-auth.tsx](apps/web/src/components/layout/require-auth.tsx) | Guard HOC: checks for an access token, hydrates the user via `GET /me`, redirects to `/login` if missing. |
| [src/components/layout/shell.tsx](apps/web/src/components/layout/shell.tsx) | Two-column app layout: sidebar nav (Dashboard, Repositories, Search, Chat, Memory, Sandbox, GitHub) + user email + logout. |
| [src/components/ui/button.tsx](apps/web/src/components/ui/button.tsx) | shadcn-style button: variants (default/outline/ghost/destructive), sizes, loading state. |
| [src/components/ui/input.tsx](apps/web/src/components/ui/input.tsx) | Styled text input with focus ring + disabled state. |

### 6.3 API & networking helpers

| File | What it does |
|------|--------------|
| [src/lib/api.ts](apps/web/src/lib/api.ts) | The **central typed API client**. Injects `Authorization: Bearer`, handles **401 → single refresh attempt**, raises a structured `ApiError`, and exposes typed methods for every endpoint (auth, repos, search, context, chat, memory, sandbox, github). Builds SSE & WebSocket URLs (token in query string). |
| [src/lib/sse.ts](apps/web/src/lib/sse.ts) | `readSse()` async generator: fetches `text/event-stream` with a Bearer header (something the browser `EventSource` can't do), parses the SSE protocol, yields `{event, data}`. |
| [src/lib/utils.ts](apps/web/src/lib/utils.ts) | `cn()` — clsx + tailwind-merge classname composition. |

### 6.4 State stores (Zustand)

| File | What it does |
|------|--------------|
| [src/stores/auth-store.ts](apps/web/src/stores/auth-store.ts) | Auth state **persisted to localStorage** (`aca.auth`): tokens, expiries, user, hydrated flag. Only token fields are persisted. |
| [src/stores/repos-store.ts](apps/web/src/stores/repos-store.ts) | Ephemeral live ingest progress per job (files seen/indexed, chunks, status), driven by SSE events on the repo detail page. |

### 6.5 Route pages (`src/routes`)

| File | What it does |
|------|--------------|
| [login.tsx](apps/web/src/routes/login.tsx) | Email/password login → store tokens + user → redirect to the originally requested page. |
| [register.tsx](apps/web/src/routes/register.tsx) | Register → auto-login. |
| [dashboard.tsx](apps/web/src/routes/dashboard.tsx) | Welcome cards: user info, live platform status (10s refetch), roadmap. |
| [repositories.tsx](apps/web/src/routes/repositories.tsx) | List/create/delete repos, trigger ingest; status + stats; 5s refetch with query invalidation. |
| [repository-detail.tsx](apps/web/src/routes/repository-detail.tsx) | Repo header, **live ingest progress via SSE**, job history, file browser, chunk previews with Prism.js highlighting. |
| [search.tsx](apps/web/src/routes/search.tsx) | Search form (mode toggle, rerank checkbox, repo scoping); results with rank/score/sub-scores and highlighted code. |
| [chat.tsx](apps/web/src/routes/chat.tsx) | Conversation sidebar + chat thread; **WebSocket streaming** of tokens, tool calls, and citations; markdown-lite code highlighting; stop button. |
| [memory.tsx](apps/web/src/routes/memory.tsx) | Add/list/forget memories with scope badges, source, and access count. |
| [sandbox.tsx](apps/web/src/routes/sandbox.tsx) | Repo + command input → WebSocket run with classify verdict, approval prompt, ANSI-stripped output. |
| [github.tsx](apps/web/src/routes/github.tsx) | GitHub status; review a PR; create a PR (form). |

### 6.6 Frontend tests & build

| File | What it does |
|------|--------------|
| [src/test/setup.ts](apps/web/src/test/setup.ts) | Imports jest-dom matchers for Vitest. |
| [src/routes/__tests__/login.test.tsx](apps/web/src/routes/__tests__/login.test.tsx) | Renders `LoginPage` in a `MemoryRouter`, asserts inputs/button present. |
| [apps/web/Dockerfile](apps/web/Dockerfile) | Multi-stage: Node 20 Alpine + pnpm → deps → dev (Vite) / prod (nginx 1.27 serving `dist`). |

---

## 7. Infrastructure & deployment

### 7.1 Docker Compose (local stack)

[docker-compose.yml](docker-compose.yml) orchestrates **9 services**: `postgres:16`,
`redis:7`, `qdrant:v1.11.3`, `api`, `worker`, `web`, `flower`, `nginx`, `prometheus`,
`grafana`. Health checks gate startup order; named volumes persist data (`postgres_data`,
`qdrant_data`, `hf_cache`, `ingest_workspace`, etc.). The `api` mounts
`/var/run/docker.sock` so the Phase-5 sandbox can spawn sibling containers; the `worker`
exposes port 9100 for multiprocess Prometheus metrics.

### 7.2 Nginx

| File | What it does |
|------|--------------|
| [infra/nginx/nginx.conf](infra/nginx/nginx.conf) | Reverse proxy: gzip, WebSocket upgrade map, upstreams for `api:8000` and `web:3000`, security headers, routes `/api/` and `/ws/` (3600s read timeout for streaming) to the API, `/` to the web app. |
| [infra/nginx/web.conf](infra/nginx/web.conf) | Production SPA server baked into the web image: serves `dist`, SPA fallback to `index.html`, 30-day asset cache. |

### 7.3 Observability

| File | What it does |
|------|--------------|
| [infra/prometheus/prometheus.yml](infra/prometheus/prometheus.yml) | Scrapes `api:8000/metrics`, `worker:9100`, and Prometheus itself, every 15s. |
| [infra/grafana/provisioning/datasources/prometheus.yml](infra/grafana/provisioning/datasources/prometheus.yml) | Registers the Prometheus datasource. |
| [infra/grafana/provisioning/dashboards/dashboards.yml](infra/grafana/provisioning/dashboards/dashboards.yml) | File-based dashboard provider. |
| [infra/grafana/provisioning/dashboards/aca-overview.json](infra/grafana/provisioning/dashboards/aca-overview.json) | "ACA – Overview" dashboard: 9 panels (LLM req rate, tokens, est. cost USD, tool calls, tokens/s, LLM latency p50/p95, HTTP rate by status, HTTP latency p95 by route, search queries/s). |

### 7.4 Postgres init

| File | What it does |
|------|--------------|
| [infra/docker/postgres/init/01-extensions.sql](infra/docker/postgres/init/01-extensions.sql) | Creates `pgcrypto`, `citext`, and `pg_trgm` on first boot. |

### 7.5 Helm chart (`infra/helm/aca`) — Kubernetes (Phase 9)

| File | What it does |
|------|--------------|
| [Chart.yaml](infra/helm/aca/Chart.yaml) | Helm chart metadata (v0.1.0). |
| [values.yaml](infra/helm/aca/values.yaml) | Production-leaning defaults: api/worker/web replicas + resources, HPA, PDB, bundled postgres/redis/qdrant, ConfigMap, secrets, ingress, NetworkPolicy. |
| [values-dev.yaml](infra/helm/aca/values-dev.yaml) | Local-dev overrides: `imagePullPolicy: Never`, single replicas, autoscaling/PDB off, `SEED_ADMIN=true`. |
| [README.md](infra/helm/aca/README.md) | Install/upgrade instructions, prod hardening notes, limitations. |
| `templates/api.yaml` | API Deployment (Alembic migrate init + uvicorn, probes). |
| `templates/worker.yaml` | Celery worker Deployment (multiproc metrics, hf_cache volume). |
| `templates/web.yaml` | Web Deployment. |
| `templates/postgres.yaml` `redis.yaml` `qdrant.yaml` | Bundled stateful backends. |
| `templates/hpa.yaml` | HorizontalPodAutoscaler for api + worker. |
| `templates/pdb.yaml` | PodDisruptionBudget for api. |
| `templates/ingress.yaml` | Nginx ingress routing `/api` and `/`. |
| `templates/networkpolicy.yaml` | Default-deny ingress with explicit allows. |
| `templates/configmap.yaml` `secret.yaml` | Non-secret config / base64 secrets. |
| `templates/serviceaccount.yaml` `_helpers.tpl` `NOTES.txt` | RBAC SA, shared template helpers, post-install notes. |

### 7.6 Root tooling & config

| File | What it does |
|------|--------------|
| [Makefile](Makefile) | ~23 convenience targets: `dev`, `up/down/logs/ps/clean`, `api-sh/api-test/api-fmt/api-mig/api-upgrade`, `worker-*`, `web-*`. |
| [Ai_coding_agent.bat](Ai_coding_agent.bat) | Windows **one-click launcher**: checks Docker, starts Ollama on the host, creates `.env` on first run, brings up the stack, waits for health, opens the browser. |
| [Ai_coding_agent_stop.bat](Ai_coding_agent_stop.bat) | Stops all containers (`docker compose down`, volumes preserved) and kills the Ollama process. |
| [scripts/dev-bootstrap.sh](scripts/dev-bootstrap.sh) | Cross-platform bootstrap: copy `.env`, generate a random `JWT_SECRET`, `docker compose up --build -d`. |
| [.env.example](.env.example) | **The configuration contract.** Groups: general, API, security (JWT/seed admin), Postgres/Redis/Qdrant, LLM providers, GitHub PAT, embeddings, rate limits, ingestion caps, Celery, observability, frontend Vite vars. Never commit a real `.env`. |
| [.pre-commit-config.yaml](.pre-commit-config.yaml) | Pre-commit hooks: whitespace/EOF/secret checks, ruff (format + lint), prettier. |
| [.github/workflows/ci.yml](.github/workflows/ci.yml) | CI: backend lint/type/test (with Postgres + Redis services), frontend lint/type/test/build, Docker image builds. |
| [.github/workflows/security.yml](.github/workflows/security.yml) | Weekly + on-push security audits: `pip-audit` (Python), `pnpm audit` (Node). |
| `.editorconfig` / `.gitattributes` / `.gitignore` | Editor settings, line-ending normalization, and ignore rules (notably blocks `.env` secrets). |

### 7.7 Documentation (`docs/`)

| File | What it does |
|------|--------------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The authoritative reference: goals, Clean Architecture + DDD style, layer responsibilities, services, data stores, auth, observability, config, errors, security, deployment. |
| [docs/PHASES.md](docs/PHASES.md) | The full 10-phase roadmap with the detailed scope of each phase. |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, auth design (Argon2id, JWT, refresh rotation), RBAC, rate limits, sandbox hardening, secrets handling, audit logging, security headers, dependency hygiene. |
| [docs/adr/0001-async-sqlalchemy.md](docs/adr/0001-async-sqlalchemy.md) | ADR explaining the choice of SQLAlchemy 2.0 async over alternatives, and the resulting repository + separate-schemas pattern. |

---

## 8. How to run it

### Windows (one-click)

```bat
Ai_coding_agent.bat        :: starts Ollama + all containers, opens the app
Ai_coding_agent_stop.bat   :: stops all containers + Ollama
```

### Any platform (Docker Compose)

Prereqs: Docker Desktop. For local LLM chat, install [Ollama](https://ollama.com) and
pull a model (`ollama pull llama3.2`).

```bash
cp .env.example .env
docker compose up --build
```

Then open:

| URL | What |
|-----|------|
| http://localhost:3000 | Frontend |
| http://localhost:8000/docs | API docs (Swagger) |
| http://localhost:8000/health | Health |
| http://localhost:8000/metrics | Prometheus metrics |
| http://localhost:6333/dashboard | Qdrant |
| http://localhost:5555 | Flower (Celery) |
| http://localhost:9090 | Prometheus |
| http://localhost:3001 | Grafana (*AI Coding Agent – Overview*) |

**Default seeded admin** (if `SEED_ADMIN=true`): `admin@local.test` / `changeme123!` —
change immediately and disable the seed before exposing this anywhere.

### LLM providers

Configure in `.env`:

- **Ollama (default, local):** `LLM_PROVIDER=ollama`,
  `OLLAMA_DEFAULT_MODEL=llama3.2:latest`. Containers reach the host's Ollama via
  `host.docker.internal:11434`. If chat fails with `ConnectError: All connection attempts
  failed`, Ollama isn't running — start it (`ollama serve`) or use the Windows launcher.
- **OpenAI:** `LLM_PROVIDER=openai` + `OPENAI_API_KEY`.

GitHub PR generation/review needs `GITHUB_TOKEN` (a PAT) in `.env` — server-side only,
never sent to the frontend.

---

## 9. Common development commands

```bash
make dev                     # docker compose up --build
make api-sh                  # shell into the api container
make api-test                # run backend tests (pytest)
make api-fmt                 # ruff format + check
make api-mig msg="add foo"   # alembic revision --autogenerate
make api-upgrade             # alembic upgrade head
make web-dev                 # run the Vite dev server outside docker
pnpm --filter web test       # frontend tests (vitest)
```

> **Tip:** after adding new frontend imports, Vite's dep cache can go stale. If a new page
> 404s, remove `apps/web/node_modules/.vite` and `docker compose restart web`.

---

## 10. Mental model — putting it together

If you remember only a few things:

1. **It's a monorepo** with one backend (`apps/api`) and one frontend (`apps/web`). The
   worker and sandbox reuse the API image.
2. **The backend is layered**: routers (`api/v1`) → services (`domain/*/service.py`) →
   repositories (`domain/*/repository.py`) + infrastructure adapters
   (`infrastructure/*`). Pydantic `schemas.py` guard the API boundary; SQLAlchemy
   `models.py` are the DB.
3. **Three data stores**: Postgres (system of record + full-text search), Qdrant (vectors),
   Redis (cache, rate limits, Celery broker, pub/sub).
4. **Long work is async** via Celery (ingestion), streamed to the UI via SSE (ingest
   progress) and WebSocket (chat, sandbox).
5. **LLMs and embeddings are pluggable** behind Protocols — swap Ollama ⇄ OpenAI with one
   env var.
6. **Everything is observable** (Prometheus metrics + cost accounting) and **deployable**
   (Docker Compose locally, Helm on Kubernetes).

Start by reading [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), then trace one feature
end-to-end (ingestion is the richest): `api/v1/repositories.py` → `domain/repositories/service.py`
→ `tasks/ingest.py` → `infrastructure/{git,parsers,embeddings,qdrant}`. After that, the
rest of the codebase will feel familiar.
```
