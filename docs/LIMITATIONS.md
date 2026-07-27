# Limitations & Future Work

> The "what's the weakest part / what would you improve?" answers. **Naming your own
> limitations reads as senior** — it shows you understand the system's edges, not just its
> happy path. Each item: the limitation, why it exists, and how I'd fix it.

---

## Known limitations (honest self-critique)

### Evaluation
- **No labeled/golden eval set.** My RAG-eval harness is **LLM-as-judge** only (faithfulness,
  answer-relevance, context-precision). That catches regressions but inherits judge bias and
  has no ground-truth recall metric.
  → *Fix:* build a small human-labeled question→relevant-chunks set, add **context recall**,
  and correlate the judge against human scores in CI.

### Retrieval
- **Single-pass retrieval.** One query → one hybrid search. No query expansion, multi-query,
  HyDE, or parent-child (small-to-big) retrieval, so a poorly-phrased question retrieves poorly.
  → *Fix:* add multi-query (LLM rewrites the query into N variants) and parent-child retrieval.
- **tree-sitter symbol extraction can yield nothing in production** for some repos, so the
  code map falls back to the file tree (chunking still works via line-window). A grammar/runtime
  quirk on the host.
  → *Fix:* pin/verify the tree-sitter grammar build in the deploy image; add a startup self-check.

### Cost / performance (free-tier)
- **Cold starts (~30–60s).** Render free tier sleeps after ~15 min idle; Neon resumes from
  suspend. First request is slow. *(Measured — see [PERFORMANCE.md](PERFORMANCE.md).)*
  → *Fix:* a keep-warm pinger, or a paid tier that doesn't sleep.
- **Groq 6000 TPM free limit** forced tool-call and token caps; heavy agent runs can still hit it.
  → *Fix:* Groq dev tier, or route to another provider; add per-user token budgets.
- **No semantic caching.** Repeated/similar queries re-embed and re-search every time.
  → *Fix:* cache query embeddings + results in Redis, keyed by normalized query + repo version.

### Ingestion
- **Full re-ingest only.** Re-indexing a repo re-processes everything; no incremental
  "only changed files since last commit."
  → *Fix:* diff against the last indexed commit SHA and re-ingest only changed files.
- **Bounded clone** (shallow, size-capped) — very large repos are truncated.
  → *Fix:* streaming/partial ingestion + sparse checkout of relevant paths.

### Reliability / infra
- **Redis is currently down** on the live deploy (Upstash connection error) — degrades live
  ingest progress (falls back to polling) and rate limiting (fails open). *(Config/URL issue,
  not code — needs a `rediss://` URL refresh.)*
- **Single region, no API CDN.** Latency is tied to the Render region; global users see RTT.
- **Sandbox disabled on cloud** (managed PaaS has no Docker socket) — the code-execution
  feature only works on the Docker/K8s deploys.

### Agentic
- **Reflexion is one iteration.** The critic→revise loop runs once; a harder task might need
  more (bounded) rounds.
- **No agent-level cost/step budget** beyond the tool-call caps; a complex multi-agent run
  can be token-expensive.
- **Hand-rolled orchestration** means I don't get framework features (checkpointing,
  human-in-the-loop pauses, durable execution) for free.

### Product / scope
- **Single-tenant per user.** No organizations, fine-grained RBAC, SSO/SCIM, or billing
  (that's the planned Phase 10).
- **No model training / fine-tuning** — deliberately out of scope (this is a RAG/agentic app,
  not an ML-training project).
- **Partial test coverage.** Core units + some integration tests (testcontainers), but not
  end-to-end coverage of every flow.
- **Memory is simple** — vector recall + Postgres facts, but no decay, consolidation, or
  conflict resolution between memories.

---

## Future work / roadmap (prioritized)

**High value, near-term**
1. **Labeled eval + CI gate** — a golden set + retrieval metrics (recall@k, MRR) that fail CI
   on regression. *Turns "I think it's good" into "I measure it."*
2. **Semantic caching** (Redis) for query embeddings + results — big latency + cost win.
3. **Incremental ingestion** — re-index only changed files (diff on commit SHA).
4. **Keep-warm / paid tier** — kill the cold start for a smoother demo.

**Medium-term**
5. **Advanced retrieval** — multi-query + HyDE + parent-child (small-to-big).
6. **Reintroduce LangGraph for one flow** — to compare hand-rolled vs framework and gain
   checkpointing / human-in-the-loop.
7. **OpenTelemetry tracing** — per-request spans across search → LLM → tools, beyond the
   current Prometheus counters.
8. **Per-user cost budgets + quotas** — hard token/cost ceilings.

**Longer-term**
9. **Fine-tune a reranker or embedding model** on the indexed code (the one real ML gap).
10. **MCP hardening** — more tools, OAuth instead of password auth.
11. **Phase 10 enterprise** — orgs, RBAC, SSO/SCIM, billing, plugin marketplace.

---

## How to use this in an interview
When asked *"what's the weakest part?"* or *"what would you do with more time?"*, pick **2–3
specific items** (not "more tests"): e.g., *"retrieval is single-pass — I'd add multi-query;
my eval is judge-only — I'd add a labeled set with recall; and there's no semantic caching."*
Concrete, prioritized self-critique is a strong senior signal. Then tie it back:
**"retrieval quality is the whole game, so that's where I'd invest first."**
