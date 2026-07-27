# Design Decisions & Trade-offs

> The "why did you choose X and not Y?" answers. For each decision: **why** I chose it,
> **what I gave up**, and **when I'd choose differently**. This is the doc that makes you
> bulletproof against follow-up probes.

---

## 1. Hybrid search — not pure vector search
**Why:** Dense vectors capture *semantics* ("how are users logged in" → `authenticate()`),
but miss *exact tokens* (searching the identifier `RefreshToken`). BM25/full-text nails
exact terms but misses paraphrase. Code is searched by concept **and** by exact symbol
name, so I run both in parallel and fuse.
**Trade-off:** Two indexes to maintain (Qdrant + a Postgres tsvector), and fusion adds a
step. More moving parts than "just embed everything."
**When I'd choose differently:** Pure vector is fine for prose/FAQ corpora where exact-token
matching doesn't matter. For code, hybrid is worth it.

## 2. Qdrant — not Pinecone / Chroma / pgvector / Weaviate
**Why:** Open-source and self-hostable (the project is self-hostable by design), a clean
HTTP API, HNSW + payload filtering, and a generous free cloud tier. One collection per repo
maps naturally to my isolation model.
**Trade-off:** Another service to run (vs `pgvector`, which would keep everything in
Postgres). Pinecone would be less ops but is proprietary + paid.
**When I'd choose differently:** For a small corpus or to minimize infra, **`pgvector`**
in the Postgres I already have is compelling (one fewer service) — I'd switch if vector
volume were modest. Pinecone/Weaviate if I wanted managed scale without self-hosting.

## 3. Reciprocal Rank Fusion — not weighted score fusion or a learned reranker-as-fusion
**Why:** Dense cosine and `ts_rank_cd` live on **incomparable scales**; normalizing them is
fiddly and fragile. RRF fuses on **rank** (`Σ 1/(k+rank)`, k=60), so no normalization —
robust and parameter-light.
**Trade-off:** RRF ignores *score magnitude* (a chunk that's a runaway best match counts the
same as a merely-first one). A tuned weighted fusion could squeeze out more precision.
**When I'd choose differently:** With labeled relevance data, a learned fusion or
score-normalized weighting can beat RRF. Without labels, RRF is the pragmatic default.

## 4. AST-aware chunking — not fixed-size or recursive-character chunking
**Why:** tree-sitter lets me chunk on **symbol boundaries** so a chunk is a whole
function/class — a semantically complete unit. Fixed-size chunking splits functions
mid-body, which wrecks both retrieval (half a function embeds poorly) and grounding.
**Trade-off:** Language-specific (needs a grammar per language); more complex than a
character splitter; falls back to line-window for unsupported languages.
**When I'd choose differently:** For prose/markdown, recursive-character or
sentence/paragraph chunking is simpler and fine. AST only pays off for code.

## 5. Hand-rolled agent loop — not LangChain / LlamaIndex / CrewAI
**Why:** Control and understanding. I own the exact ReAct loop, tool dispatch, streaming,
and guardrails (the tool-call caps came from a real runaway-loop bug I could only fix
because I owned the loop). Frameworks add abstraction, version churn, and hidden prompts.
**Trade-off:** I re-implemented things frameworks give free (tool schemas, retries,
some orchestration). More code to maintain.
**When I'd choose differently:** For rapid prototyping, or a large team wanting a standard,
a framework (LangGraph) speeds you up. For a portfolio project where *understanding* is the
point — and for tight control over cost/guardrails — hand-rolling won.

## 6. Three data stores (Postgres + Qdrant + Redis) — not one
**Why:** Each is best-in-class for its job: Postgres = relational truth + full-text; Qdrant
= ANN vectors; Redis = ephemeral (cache, rate-limit, pub/sub). Forcing all into one store
means compromising on at least one.
**Trade-off:** More infra + more failure modes (e.g., the current Redis outage degrades live
progress). Operationally heavier than a single DB.
**When I'd choose differently:** To minimize ops I'd collapse to **Postgres + `pgvector`**
(drop Qdrant) and skip Redis for a single-node deploy (in-process rate limiting). I kept the
split because it's the production-grade shape and degrades gracefully.

## 7. Async FastAPI + SQLAlchemy 2.0 — not Flask / Django
**Why:** The workload is I/O-bound (DB + vector + LLM calls). Async handles many concurrent
requests without thread-per-request overhead; native WebSocket/SSE support; Pydantic typing;
auto OpenAPI docs.
**Trade-off:** Async is easy to get subtly wrong (session lifecycles in streaming — I hit
exactly that bug), and the ecosystem is younger than Django's batteries-included world.
**When I'd choose differently:** Django if I needed an admin, ORM migrations, and auth
out-of-the-box for a CRUD-heavy app. For an LLM-streaming API, async FastAPI is the fit.

## 8. WebSocket for chat, SSE for progress — not one transport, not polling
**Why:** Chat is **bidirectional/interactive** (send, stream tokens, stop) → WebSocket.
Ingest/agents/audit are **server→client-only** → SSE (simpler, plain HTTP, auto-reconnect).
Polling wastes requests and adds latency.
**Trade-off:** Two streaming mechanisms to maintain. WS needs a query-param token (browsers
can't set WS headers); SSE needed a custom fetch reader for the auth header.
**When I'd choose differently:** If I only ever streamed one-way, SSE everywhere is simpler.
WS-everywhere is overkill for progress bars.

## 9. Celery **and** an inline subprocess — not just one
**Why:** Celery is the right tool for background ingestion at scale. But the free-tier cloud
deploy has **no worker dyno**, so I added an inline subprocess path (its own engine + event
loop) that runs the identical pipeline. One codebase, two execution modes.
**Trade-off:** Two code paths to keep in sync; the inline path can't scale like a worker pool.
**When I'd choose differently:** FastAPI `BackgroundTasks` would be simpler but shares the web
process (bad for CPU-heavy ingest). Celery-only is cleaner if you always have a worker.

## 10. Pluggable providers behind Protocols — not hardcoding OpenAI
**Why:** An `LLMProvider`/`EmbeddingProvider` Protocol + factory lets me swap
Ollama ⇄ OpenAI ⇄ Groq and local ⇄ Jina with one env var (even per-conversation), and mock
them in tests. Avoids vendor lock-in.
**Trade-off:** An abstraction layer to design and maintain; I must normalize provider quirks
(e.g., streamed tool-call fragment formats differ).
**When I'd choose differently:** If I were certain I'd only ever use one provider, the
indirection is unnecessary. For a self-hostable, provider-agnostic tool, it's essential.

## 11. Cross-encoder reranking — applied to top-N, not always/never
**Why:** After fusion, a cross-encoder that scores (query, chunk) *jointly* is far more
precise than the initial retrieval. But it's slow and uncacheable, so I run it only on a
small candidate pool.
**Trade-off:** Latency (~100–500ms) and CPU. It's the biggest single cost in retrieval.
**When I'd choose differently:** Skip it for latency-critical or high-QPS paths; keep it for
quality-critical answers. It's a toggle, not a religion.

## 12. Free-tier managed split — not a single PaaS or full self-host
**Why:** Zero-cost public deployment for a portfolio, each concern on a best-fit free tier
(Render/Vercel/Neon/Upstash/Qdrant/Groq/Jina). Demonstrates real cloud/12-factor skills.
**Trade-off:** Cold starts (~30–60s), tight limits (Groq 6000 TPM), no Docker socket (sandbox
off), and more accounts to wire. Split across vendors = more failure surface.
**When I'd choose differently:** A single paid PaaS (Render/Fly) for no cold starts and one
dashboard; or Kubernetes (the included Helm chart) for a real production tenant.

## 13. JWT access + rotating refresh tokens — not server-side sessions
**Why:** Stateless access tokens scale horizontally with no session store lookup; opaque
refresh tokens with **single-use rotation** give revocation + theft detection.
**Trade-off:** Can't instantly revoke an access token before it expires (mitigated by short
TTL); rotation logic is more code than a session cookie.
**When I'd choose differently:** Server-side sessions for a single-server app that wants
instant revocation and simpler logic.

## 14. tree-sitter — not regex or a full Language Server (LSP)
**Why:** tree-sitter gives real ASTs across 30+ languages via prebuilt grammars — accurate
symbol extraction without running a language server per language.
**Trade-off:** Grammar coverage varies; it parses structure but not full semantics (no type
resolution / call graphs like an LSP would give).
**When I'd choose differently:** An LSP if I needed precise cross-file references / call
graphs (e.g., a true call-graph feature). Regex if I only needed crude symbol names.

## 15. One Qdrant collection per repo — not one shared collection with a filter
**Why:** Isolation (delete/re-ingest a repo = drop its collection), smaller per-repo HNSW
graphs (faster search), and no cross-repo leakage.
**Trade-off:** Many collections to manage; cross-repo search means querying several
collections and merging.
**When I'd choose differently:** A single collection with a `repo_id` payload filter scales
to *many small* repos better (fewer collections). I chose per-repo for clean isolation.

---

## How to use this in an interview
When asked *"why did you choose X?"*, answer in three beats: **(1) the reason**, **(2) the
trade-off you accepted**, **(3) when you'd choose differently.** That last beat is what makes
you sound senior — it shows you chose deliberately, not by default.
