# Performance & Cost

> Real numbers you can quote, plus a breakdown of *where the time goes* and *how to measure
> it yourself*. Interviewers ask "how fast is it / how much does a query cost?" — vague
> answers hurt, specific ones (even ranges, honestly labeled) land.

**Honesty note:** figures below are marked **[measured]** (I timed the live deployment) or
**[estimated]** (derived from the architecture — I tell you how to measure them exactly).

---

## Measured — live deployment (Render + Vercel + Neon), 2026-07

I timed the public endpoints directly. The most important result: I **captured the cold
start** — the first request after idle timed out at 60s, the next took 31s, then it was warm.

| Metric | Result | Notes |
|---|---|---|
| **Cold start (first request after ~15min idle)** | **~30–60s** [measured] | Render free tier sleeps + Neon resumes from suspend. 1st call 60s, 2nd 31s, then warm. |
| **Warm API latency** (`/health`) | **~0.35–0.9s** [measured] | Mostly network RTT to the Render region + a trivial handler. |
| **Frontend load** (Vercel edge) | **~0.4–0.8s** [measured] | Static SPA from the CDN edge. |
| **Readiness** (`/ready`: Postgres + Redis checks) | **~0.7–1.0s** [measured] | Includes a Postgres ping (Redis currently erroring — see LIMITATIONS). |
| **Login roundtrip** (Postgres lookup + **Argon2** verify) | **~0.8–2.1s** [measured] | Argon2 is *deliberately* slow (brute-force resistance); that's a feature, not a bug. |

**The headline for an interview:** *"Warm, it's sub-second; the honest caveat is a 30–60s
cold start on the free tier because the backend sleeps — I'd fix that with a keep-warm pinger
or a paid tier."* Naming the cold start (with the real number) shows you actually measured it.

---

## Where the time goes — anatomy of one RAG chat query [estimated]

A chat answer is a pipeline; total latency ≈ the sum of these. The **LLM generation
dominates** — everything else is small.

| Stage | Typical | Why |
|---|---|---|
| Embed the query | ~50–200ms | One embedding call (local model or hosted API RTT). |
| Qdrant kNN (dense) | ~5–50ms | HNSW is ~log time; runs in parallel with the sparse search. |
| Postgres FTS (sparse) | ~10–50ms | GIN-indexed `content_tsv`; parallel with dense. |
| RRF fusion | <5ms | Pure in-memory arithmetic. |
| Cross-encoder rerank | ~100–500ms | CPU-bound, top-N only — **the biggest retrieval cost** (that's why it's optional). |
| Context packing | <10ms | Merge + token-budget in memory. |
| **LLM generation** | **~1–10s+** | **Dominates.** = (output tokens ÷ provider tokens/sec) + time-to-first-token. Groq is fast (hundreds of tok/s); local Ollama is slower. |

**Takeaways to say out loud:**
- *"Retrieval is cheap (tens of ms); the LLM is the cost — so streaming matters, because
  time-to-first-token is what the user feels."*
- *"Rerank is the one expensive retrieval step, so it's a toggle applied to a small top-N."*

---

## Cost per query [estimated]

Cost is **token-based**: `cost = (prompt_tokens + completion_tokens) × price_per_token`.
`core/cost.py` counts tokens with tiktoken and multiplies by a per-1M-token price table.

- **On the current deploy: ~$0** — Groq's free tier and local/Jina embeddings cost nothing.
- **Illustrative** (if using a paid model): a chat turn with ~1,500 tokens of RAG context +
  ~1,000 tokens of history/prompt + ~500 output ≈ **~3,000 tokens**. At, say, $0.50 / 1M
  input + $1.50 / 1M output, that's roughly **$0.002 per turn** — fractions of a cent. A
  full **multi-agent run** (planner + N researchers + synthesizer + critic) is ~5–8× that.
- The **Agents page shows an estimated-token meter** per run so cost is visible in the UI.

**The lever:** context size and model choice drive cost. That's *why* the RAG context is
token-budgeted (~1500) and the tool results are capped — cost control is designed in.

---

## How to measure it yourself (the recipe)

So you can quote exact numbers for *your* data, not my estimates:

1. **Prometheus `/metrics`** (the authoritative source) — the app records histograms:
   - `aca_search_duration_seconds` — retrieval latency (per mode).
   - `aca_llm_request_duration_seconds` — LLM call latency (per provider/model).
   - `aca_llm_tokens_total` — prompt/completion tokens (→ cost).
   - `aca_tool_calls_total`, `aca_http_request_duration_seconds` — tool + HTTP timing.
   Scrape it, or read the raw counters at `/metrics`.
2. **Grafana** — the bundled "AI Coding Agent – Overview" dashboard plots LLM rate, tokens,
   estimated cost, and latency p50/p95 (Docker/K8s deploys).
3. **Time the calls directly** — `curl -w "%{time_total}"` for HTTP; for WebSocket chat,
   measure time-to-first-token vs total in the browser devtools Network tab.
4. **The Agents page token meter** — a quick per-run token estimate without touching metrics.

> Interview gold: *"I don't just guess — I have Prometheus histograms for search and LLM
> latency and a token counter for cost, surfaced in Grafana and in the UI."*

---

## Optimization levers (ties to [LIMITATIONS.md](LIMITATIONS.md))
- **Kill the cold start** → keep-warm pinger or paid tier.
- **Cut repeat latency/cost** → semantic caching of embeddings + results in Redis.
- **Trade quality for speed** → toggle the reranker off on latency-critical paths.
- **Cut cost** → smaller model (8B), tighter context budget, per-user token caps.
- **Cut tokens** → the tool-call caps + context packing already do this by design.
