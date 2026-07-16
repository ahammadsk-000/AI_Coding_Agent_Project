# Interview Prep — AI Coding Agent (End-to-End)

This is your single study document for the project. It has two parts:

- **Part 1 — Understand the project end-to-end.** A from-zero path: where to start,
  what to run, what each piece does, and the exact flows to trace. Read this first
  if the codebase feels overwhelming.
- **Part 2 — Interview questions with model answers.** Every kind of question you can
  expect, grounded in *this* project.

Companion docs: [Ai_coding_agent.md](../Ai_coding_agent.md) (exhaustive file-by-file
guide) and [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) (diagrams). *(There is
also a local one-page cheat sheet, `docs/INTERVIEW_TALKING_POINTS.md`, kept out of git.)*

---

# PART 1 — Understand the project end-to-end

## 0. First, *see it work* (observe before you read)

You understand a system fastest by watching it run. Do these in order and watch
what changes:

1. **Log in** → you get a JWT; the SPA stores it and calls `/users/me`.
2. **Add a repository** (a small public GitHub repo) and click **Ingest** → watch the
   live progress bar (files seen / indexed / chunks). *That bar is server-sent events.*
3. **Open the repo** → see the **metrics dashboard**, **file browser**, and try
   **Insights** (architecture diagram, code map, onboarding docs) and **Audit**.
4. **Search** a concept ("how are options parsed") → see ranked results with scores.
5. **Chat** → ask a code question; watch tokens stream and citations appear.
6. **Agents** → run a task; watch Planner → Researchers → Synthesizer → Critic stream.
7. **RAG Eval** → run a question; see faithfulness / answer-relevance / context-precision.

Now you've seen all seven core flows. The rest is *how they're built*.

## 1. The 60-second mental model

- **It's a monorepo:** one backend (`apps/api`, FastAPI) + one frontend (`apps/web`,
  React/Vite). The Celery worker and sandbox reuse the API image.
- **The backend is layered (Clean Architecture + DDD):**
  `api/v1` (transport) → `domain/<context>` (business logic) → `infrastructure`
  (adapters for LLM/DB/Qdrant/…) → `core` (config, security, logging, metrics).
  **Dependencies point inward; services never import FastAPI.**
- **Three data stores:** Postgres (system of record + full-text search), Qdrant
  (vector embeddings), Redis (cache, rate limits, Celery broker, pub/sub).
- **Long work is async & streamed:** ingestion runs in the background (Celery or an
  inline subprocess) and streams progress via **SSE**; chat streams tokens via
  **WebSocket**.
- **LLMs & embeddings are pluggable** behind Protocols (ports/adapters) — swap
  Ollama ⇄ OpenAI ⇄ Groq with one env var.

## 2. The reading order (where to start in the code)

Follow the "golden path" — the same order the data flows:

| # | File | What to notice |
|---|------|----------------|
| 1 | [apps/api/app/main.py](../apps/api/app/main.py) | App factory: middleware order (request-id → metrics → rate-limit → CORS), lifespan (DB/Redis), `/metrics`, `/health`. |
| 2 | [apps/api/app/core/config.py](../apps/api/app/core/config.py) | The **settings contract** — every env var. `.env.example` mirrors it. |
| 3 | [apps/api/app/api/router.py](../apps/api/app/api/router.py) | Every route group in one place — your table of contents. |
| 4 | [apps/api/app/domain/repositories/service.py](../apps/api/app/domain/repositories/service.py) | `enqueue_ingest()` — Celery task **or** inline subprocess. |
| 5 | [apps/api/app/tasks/ingest.py](../apps/api/app/tasks/ingest.py) | The ingestion pipeline (clone → parse → chunk → embed → index → publish). |
| 6 | [apps/api/app/domain/search/service.py](../apps/api/app/domain/search/service.py) | Hybrid retrieval: dense + sparse + **RRF** + rerank. The heart of RAG. |
| 7 | [apps/api/app/domain/chat/service.py](../apps/api/app/domain/chat/service.py) | The **agent loop** (`send_message_streaming`). |
| 8 | [apps/api/app/domain/chat/tools.py](../apps/api/app/domain/chat/tools.py) | The 4 tools + dispatch. |
| 9 | [apps/api/app/domain/agents/service.py](../apps/api/app/domain/agents/service.py) | The multi-agent pipeline + Reflexion. |
| 10 | [apps/web/src/App.tsx](../apps/web/src/App.tsx) → [apps/web/src/lib/api.ts](../apps/web/src/lib/api.ts) → a page like [chat.tsx](../apps/web/src/routes/chat.tsx) | How the SPA talks to the API. |

> For the **exhaustive** "what every file does" list, read
> [Ai_coding_agent.md §5–6](../Ai_coding_agent.md). Don't memorize it — understand the
> flows below and you can re-derive any file's job.

## 3. The five flows to be able to trace end-to-end

### A. Ingestion (clone → searchable)
`POST /repositories/{id}/ingest` → `RepositoryService.enqueue_ingest` creates an
`IngestJob` (status `queued`) and dispatches work → `tasks/ingest.py` (or
`ingest_cli.py` subprocess): **git clone** (shallow, size-capped) → **tree-sitter**
parse + symbol extraction → **AST-aware chunking** (tiktoken budget) → **embed**
chunks (batched) → **upsert to Qdrant** (one collection per repo) → store
files/symbols/chunks in **Postgres** → **publish progress to Redis** → frontend shows
it live via **SSE**. Repo flips to `ready`.

### B. Search / RAG retrieval
`SearchService.search`: embed the query → **Qdrant kNN** (dense) *in parallel with*
**Postgres full-text** (`ts_rank_cd`, sparse) → fuse both ranked lists with
**Reciprocal Rank Fusion (k=60)** → optional **cross-encoder rerank** → filter
low-relevance "padding" → return top-k hits with file/line/score.

### C. Chat (RAG + tool-using agent)
WebSocket → `ChatService.send_message_streaming`: persist user message → (skip if
chit-chat) run hybrid search → build a **system prompt** with repo inventory + RAG
context (token-capped ~1500) + recalled **memories** → **stream** the LLM. If it emits
`tool_calls`, execute them (de-duped, capped 2/round & 3/turn), feed results back,
loop (≤ 5 rounds). Stream tokens + citations; persist every message.

### D. Multi-agent pipeline
`AgentOrchestrator.run_stream`: **Planner** splits the task into sub-questions →
one **Researcher** per sub-question (each grounded via SearchService) → **Synthesizer**
combines → **Critic** fact-checks and returns a verdict → **Reflexion** revises once
if the critic flags issues, then re-reviews. Each stage is an SSE event.

### E. RAG evaluation
`RagEvalService.evaluate`: run real retrieval + grounded generation, then score with
an **LLM-as-judge** on **faithfulness** (grounded?), **answer relevance** (on-topic?),
and **context precision** (was the retrieval relevant?). Reference-free.

## 4. Subsystem cheat-sheet (what each area owns)

| Area | Key files | Owns |
|------|-----------|------|
| **Transport** | `api/v1/*`, `api/middleware/*` | HTTP/WS routers (thin), request-id, metrics, rate-limit |
| **Auth** | `domain/auth`, `core/security.py`, `core/dependencies.py` | JWT + refresh rotation, Argon2, RBAC guards |
| **Repositories/Ingest** | `domain/repositories`, `tasks/ingest.py`, `ingest_cli.py` | repo CRUD, the ingestion pipeline |
| **Search/RAG** | `domain/search` | hybrid retrieval, RRF, rerank, context packing |
| **Chat** | `domain/chat` | agent loop, tools, memory capture, streaming |
| **Agents** | `domain/agents` | planner/researcher/synthesizer/critic/reflexion |
| **Insights/Audit/Eval** | `domain/insights`, `domain/audit`, `domain/eval` | diagrams, code map, docs, metrics, similar-code, test-gen, audit, RAG eval |
| **Memory** | `domain/memory` | remember/recall/forget (vector + Postgres) |
| **GitHub** | `domain/github`, `infrastructure/github` | PR create + AI review |
| **Infrastructure** | `infrastructure/*` | LLM, embeddings, Qdrant, tree-sitter, git, redis, websearch, sandbox, db |
| **Cross-cutting** | `core/*` | config, security, logging, metrics, cost, exceptions |
| **Frontend** | `apps/web/src` | pages (`routes/`), typed client (`lib/api.ts`), stores, SSE/WS helpers |

---

# PART 2 — Interview questions (with model answers)

> How to use: read the question, try to answer out loud, then check the model
> answer. The **★ senior** ones are the depth probes that separate 60% from 90%.

## A. The opener — "Tell me about your project"

**Q: Walk me through your project.**
> "It's a self-hostable **agentic RAG platform over your own codebase**. You point it
> at a git repo; it clones and indexes the code with tree-sitter + embeddings, then you
> can **search** it (hybrid retrieval), **chat** with a RAG + tool-using agent, run a
> **multi-agent** research/audit pipeline, and open GitHub PRs. The backend is async
> **FastAPI + SQLAlchemy 2.0** in a Clean-Architecture/DDD layout; data lives in
> **Postgres (records + full-text), Qdrant (vectors), and Redis**. LLMs and embeddings
> are pluggable behind Protocols, so I can run local Ollama or cloud Groq with one env
> var. I deployed it free-tier on Render + Vercel + Neon + Upstash + Qdrant Cloud."

**Q: What did you build yourself vs. glue together?**
> "I hand-wrote the **agent loop**, the **tool dispatch**, the **hybrid-search fusion
> (RRF)**, the **AST-aware chunker**, the **multi-agent pipeline with a critic/Reflexion
> loop**, the **RAG-eval harness**, and the **provider abstractions**. I glued in
> Postgres/Qdrant/Redis and the LLM/embedding HTTP APIs. I deliberately did *not* use
> LangChain/CrewAI so I understand the mechanics rather than the framework."

## B. Architecture & system design

**Q: Why Clean Architecture + DDD here?**
> "Testability and swappability. Each bounded context has `models` (DB shape),
> `repository` (the only DB access), `schemas` (the Pydantic API boundary), and
> `service` (use case). All external systems sit behind Protocols in
> `infrastructure`, so I can swap an LLM provider or the vector DB without touching
> business logic, and unit-test services with fakes."

**Q: Walk me through what happens on one request. ★**
> Pick ingestion (richest): route → service creates a job row + dispatches → worker
> clones/parses/chunks/embeds/indexes → publishes progress to Redis → SSE to the UI →
> status `ready`. (See Part 1 §3A.)

**Q: How do the three data stores divide responsibility?**
> "Postgres is the **system of record** and does **sparse/full-text** search; Qdrant
> holds the **dense vectors** (ANN); Redis is **ephemeral** — cache, rate-limit
> counters, Celery broker, and pub/sub for progress. I never store truth in Redis."

**Q: How would you scale this to 10× users? ★**
> "Stateless API → horizontal scale behind a load balancer (already have a Helm HPA).
> Move ingestion fully onto Celery workers and scale that pool independently. The
> bottlenecks are **LLM/embedding rate limits** and **ingestion memory** — I batch
> embeddings, retry with backoff, use per-repo Qdrant collections, and token-budget
> the context. Caching frequent search/embeddings would be the next lever."

## C. RAG & retrieval

**Q: Why hybrid search instead of pure vector search?**
> "Dense vectors capture **semantics** ('auth flow') but miss **exact identifiers**
> ('`RefreshToken`'); BM25/full-text nails exact tokens but misses paraphrase. Code
> search needs both, so I run them in parallel and fuse."

**Q: What is Reciprocal Rank Fusion and why use it over score-weighting? ★**
> "RRF scores each doc as Σ 1/(k + rank) across the ranked lists (k=60). It fuses on
> **rank, not raw scores**, so I don't have to normalize incomparable cosine and
> `ts_rank_cd` scales. It's robust and parameter-light."

**Q: What is your chunking strategy and why does it matter? ★**
> "**AST-aware** chunking with tree-sitter: I chunk on symbol boundaries
> (functions/classes) so a chunk is a semantically whole unit, splitting oversized
> symbols by a token-budgeted line window and gap-filling between them. Naive
> fixed-size chunking splits functions mid-body and wrecks retrieval + grounding."

**Q: What's re-ranking and when is it worth it?**
> "After fusion I optionally run a **cross-encoder** (`ms-marco-MiniLM`) that jointly
> encodes (query, chunk) for a precise relevance score, then reorder. It's slower
> (no caching, runs per candidate) so I apply it to a small top-N pool, not the corpus."

**Q: How do you keep the prompt from overflowing the context window?**
> "`pack_context` groups hits by file, merges overlapping/adjacent line ranges, and
> greedily packs under a **token budget (~1500)** using tiktoken. The context window
> is a budget you architect, not a dumping ground."

**Q: RAG vs fine-tuning vs long-context — when each? ★**
> "**RAG** for knowledge that changes or is large/proprietary (my case — code changes
> constantly). **Fine-tuning** to change *behavior/format/style* or bake in a skill,
> not for facts. **Long-context** when the whole relevant corpus is small enough to
> fit and recall matters more than cost. They compose."

## D. Embeddings & vector search

**Q: What are embeddings and how do you measure similarity?**
> "Embeddings map text to vectors where distance ≈ semantic similarity. I use **cosine
> similarity** (Qdrant, normalized vectors), which measures angle, ignoring magnitude."

**Q: Why Qdrant / how does ANN work? ★**
> "At scale, exact kNN is O(N·d) per query — too slow. Qdrant uses **HNSW**, a
> navigable small-world graph that gives approximate nearest neighbors in ~log time,
> trading a little recall for huge speed. I use one **collection per repo** with cosine
> distance and payload indexes for filtering."

**Q: You switched embedding providers in production — what broke? ★**
> "Embedding **dimension** and semantics are provider-specific, so vectors from one
> model aren't comparable to another's — switching means the collection must match the
> new dimension (I re-ingest). I also hit **429s** on the hosted API, so I added
> retry-with-backoff and batching."

## E. LLM integration & providers

**Q: How is the app model-agnostic?**
> "An `LLMProvider` Protocol (`chat`, `stream`, tool support) with a `factory` that
> returns Ollama/OpenAI/Groq based on config — even per-conversation. The rest of the
> code depends on the Protocol, never a concrete SDK."

**Q: How does streaming tool-calling actually work? ★**
> "I stream the completion; text deltas go to the user, and tool-call fragments are
> reassembled (OpenAI streams arguments in pieces). When the model finishes with
> `tool_calls`, I execute them, append tool-result messages, and call the model again —
> that's the ReAct loop. When it returns no tool calls, we're done."

**Q: Same prompt, different answers — why? (and how do you make it reproducible)**
> "Sampling. `temperature`/`top_p` inject randomness; even at temp 0 you can see
> nondeterminism from floating-point/batching on the server. For judge/critic calls I
> use **temperature 0** to minimize variance."

## F. Chat agent & tool calling

**Q: What tools does your agent have and why read-only?**
> "`search_code`, `read_file`, `list_files`, and `web_search`. Read-only because the
> chat agent shouldn't mutate state; writes go through explicit, reviewable flows
> (GitHub PR creation, the sandbox)."

**Q: How does the agent decide to stop?**
> "When the LLM returns no `tool_calls`, the loop ends. Hard cap at **5 rounds** as a
> backstop."

**Q: A model spammed a tool in a loop and blew your token budget — what did you do? ★**
> "Real bug I fixed. I now **de-dup identical tool calls** and cap execution to
> **2/round and 3/turn**, then force a prose answer; I cap each tool result fed back to
> ~3000 chars; and I treat provider **rate-limit/413** as terminal with a friendly
> message instead of crashing the turn. A `tool_use_failed` retries once **without**
> tools. Guardrails against runaway agents are a real production concern."

**Q: How do you prevent hallucinated file paths / fake code?**
> "The system prompt forbids inventing paths and requires citing exact `file:line`
> from the retrieved context; I preload the repo file inventory so it uses real names;
> and I detect 'leaked' tool-call text. Grounding + citations make answers verifiable."

## G. Agentic AI (multi-agent, Reflexion, ReAct)

**Q: Difference between a workflow and an agent? ★**
> "A **workflow** has a fixed, developer-defined control flow; an **agent** lets the
> **LLM decide** the next step (which tool, whether to continue). My chat is an agent
> (LLM-driven loop); my multi-agent pipeline is a **structured** orchestration —
> deterministic stages, each powered by an LLM."

**Q: Explain your multi-agent pipeline and why a critic.**
> "Planner → per-sub-question Researchers (grounded) → Synthesizer → **Critic** that
> fact-checks the answer against the researchers' findings and returns
> accurate/issues/uncertain. A single pass can be confidently wrong; an independent
> critic catches unsupported claims."

**Q: What is Reflexion and how did you implement it? ★**
> "Self-correction from feedback: if the critic returns **issues**, I feed its critique
> back to the synthesizer to **revise once**, then **re-review**. It's a bounded
> improvement loop (one iteration) so it can't spin forever."

**Q: ReAct — what is it?**
> "Reason + Act: the model interleaves reasoning with tool actions and observations.
> My chat loop is exactly this — think, call a tool, read the result, continue."

## H. Evaluation

**Q: How do you know your RAG is any good? ★**
> "I built a **RAG-eval harness** (LLM-as-judge) that scores **faithfulness** (claims
> grounded in retrieved code), **answer relevance**, and **context precision** — the
> RAGAS triad, reference-free so it needs no labels. It runs the real pipeline, so it
> catches retrieval *and* generation regressions."

**Q: What's the weakness of LLM-as-judge and how do you mitigate it?**
> "Judges are biased and noisy (verbosity/position bias, self-preference). I mitigate
> with **temperature 0**, focused single-metric prompts, and a forced `SCORE:` format I
> parse. For rigor you'd add human-labeled goldens and correlate."

## I. MCP (Model Context Protocol)

**Q: What is MCP and what did you build? ★**
> "MCP is an open standard that lets any AI host (Claude Desktop, IDEs) connect to
> external tools/data uniformly — think 'USB-C for AI tools'. I built a **FastMCP
> server** exposing `search_code`/`read_file`/`list_repositories` as MCP tools over
> stdio; it's a thin client on my REST API, so Claude Desktop can search my indexed
> repos. Architecture: Host → (MCP) → my server → (REST) → hybrid search."

## J. Streaming (WebSocket vs SSE)

**Q: Why WebSocket for chat but SSE for ingestion/agents? ★**
> "Chat is **bidirectional** and interactive (send message, stream tokens, allow
> stop) → WebSocket. Ingest/agents/audit are **server→client only** progress → SSE,
> which is simpler, works over plain HTTP, and auto-reconnects. I use a `fetch`-based
> SSE reader so I can send the `Authorization` header (the browser `EventSource`
> can't)."

**Q: A gotcha you hit with SSE? ★**
> "My SSE stream showed nothing at first. Two causes: (1) the streaming endpoint used
> the request-scoped DB session, which FastAPI tears down before the stream body runs
> — I open a **fresh session inside the generator**; (2) my parser split on `\n\n` but
> the server emitted `\r\n\r\n` — I normalize CRLF. Classic streaming-lifecycle bugs."

## K. Data & persistence

**Q: Why async SQLAlchemy 2.0?**
> "The workload is I/O-bound (DB + LLM + vector calls). Async lets one process handle
> many concurrent requests without thread-per-request overhead. 2.0's typed
> `Mapped[...]` models are clean and mypy-friendly."

**Q: How does Postgres full-text search work here?**
> "A generated **STORED `content_tsv`** column with a **GIN index** on `code_chunks`;
> queries use `plainto_tsquery` + `ts_rank_cd`. `plainto_tsquery` is forgiving of raw
> user text (no syntax-error footguns)."

**Q: A production DB gotcha you solved? ★**
> "On Neon, **asyncpg rejects the `sslmode` query param** that libpq uses — I strip
> `sslmode`/`channel_binding` from the URL and pass `ssl=require` via `connect_args`."

## L. Auth & security

**Q: Explain your auth.**
> "Argon2id password hashing; short-lived **JWT access** tokens + opaque **refresh**
> tokens with **single-use rotation** (a used refresh token is revoked). RBAC via role
> guards in dependencies. The frontend refreshes once on a 401 and retries."

**Q: How is the sandbox hardened? ★**
> "Disposable Docker containers with `network_mode=none`, `cap_drop=ALL`,
> `no-new-privileges`, read-only root + tmpfs workspace, non-root user, memory/CPU/pids
> caps, and a hard timeout — plus a **command-policy classifier** that hard-blocks
> destructive patterns and gates network/installs behind approval. On managed cloud
> there's no Docker socket, so it's disabled behind a feature flag."

**Q: Prompt injection — do you handle it?**
> "It's the part juniors skip. My mitigations: read-only tools, grounding + citation
> requirements, chit-chat/leaked-tool-call detection, and never executing model output
> directly (writes are gated). A fuller answer: treat retrieved content as untrusted,
> separate instructions from data, and add output validation."

## M. Deployment & scaling

**Q: How is it deployed?**
> "Three ways: **docker-compose** (9 services) locally, a **Helm chart** (HPA/PDB/
> NetworkPolicy/Ingress) for K8s, and a **free-tier managed split** — Render (API),
> Vercel (SPA), Neon (PG), Upstash (Redis), Qdrant Cloud, Groq (LLM), Jina
> (embeddings)."

**Q: What did you trade off on the free tier? ★**
> "No Celery worker → ingestion runs as an **inline subprocess** (its own engine/loop);
> no Docker socket → **sandbox disabled** via a build flag; and Groq's **6000 TPM** free
> limit forced the tool-call/token caps. Graceful degradation, not feature removal."

## N. Observability & cost

**Q: How do you observe the system?**
> "Prometheus metrics (`aca_*`: HTTP, LLM calls/tokens/latency, tool calls, search,
> ingest), structured **structlog** with a `request_id` propagated per request, and a
> Grafana dashboard. I bridge Celery via multiprocess metrics."

**Q: How do you track LLM cost?**
> "`core/cost.py` counts tokens with **tiktoken** and multiplies by a per-1M-token
> price table (local models = free). It feeds a Prometheus cost counter, and the
> Agents page shows an estimated-token meter."

## O. Failure modes & tradeoffs (senior signal) ★

- **"Where does this break under load?"** LLM/embedding rate limits first; then
  ingestion memory; then Postgres FTS on huge repos. Mitigations above.
- **"What's the weakest part?"** Retrieval quality is the whole game — garbage
  retrieval → garbage answer, so my eval harness targets exactly that. Also, on the
  free tier tree-sitter symbol extraction sometimes yields nothing, so the code map
  falls back to the file tree.
- **"What would you do with more time?"** Add multi-query/HyDE retrieval, a proper
  labeled eval set, semantic caching, and reintroduce a real agent framework
  (LangGraph) for one flow to compare.

## P. Behavioral / project-story

- **"Hardest bug?"** The SSE-shows-nothing bug (DB-session lifecycle + CRLF parsing) —
  good because it's about *streaming internals*, not a typo.
- **"A decision you'd defend?"** Hand-rolling the agent loop instead of LangChain — it
  cost more time but I can explain every line, which is the point in an interview.
- **"Something you cut?"** Kept the sandbox out of the cloud deploy — the honest
  trade-off for zero-cost hosting, hidden behind a flag rather than deleted.

## Q. Rapid-fire / gotchas

- **Temp 0 ≠ deterministic** on hosted APIs (batching/float). Yes.
- **Why per-repo Qdrant collections?** Isolation + easy delete/re-ingest + smaller ANN graphs.
- **Why RRF k=60?** The paper's default; it flattens the contribution curve so no
  single high rank dominates.
- **What's a cross-encoder vs bi-encoder?** Bi-encoder embeds query and doc separately
  (cacheable, fast, for retrieval); cross-encoder encodes them **together** (accurate,
  uncacheable, for reranking a small set).
- **Fail-open rate limiter?** If Redis is down, allow the request — availability over a
  perfect limit for a non-critical control.

## R. Good questions to ask the interviewer

- "How do you evaluate LLM features here — offline evals, online metrics, or vibes?"
- "RAG, fine-tuning, or long-context for your use case — and why?"
- "Where's your biggest reliability or cost pain in the LLM stack today?"
- "Are you using an agent framework or hand-rolled loops, and how's that going?"

---

## Final tips

- **Lead with the flow, not the file list.** Interviewers want to see you reason about
  data movement and trade-offs.
- **Be honest about scope.** "Single agent here, multi-agent there; read-only tools;
  sandbox off in cloud" — honesty about limits reads as senior, not weak.
- **Have one deep story ready** (the streaming bug or the tool-runaway fix) — a real
  debugging narrative beats reciting buzzwords.
- **Know the numbers:** RRF k=60, ~1500-token context budget, ≤5 tool rounds, 2/3 tool
  caps, 384-dim bge-small, 6000 TPM free tier.
