# Deploying the AI Coding Agent online (free tier)

This guide puts the platform on the public internet for **$0/month**, using the
same split your other projects use:

| Layer | Service | Free tier |
|-------|---------|-----------|
| Frontend (React SPA) | **Vercel** | yes, always-on CDN |
| Backend API (FastAPI) | **Render** | yes (web service sleeps after 15 min idle) |
| Postgres | **Neon** | yes (serverless) |
| Redis | **Upstash** | yes (rate limiting + ingest progress pub/sub) |
| Vector store | **Qdrant Cloud** | yes (1 GB cluster) |
| Chat LLM | **Groq** | yes (OpenAI-compatible, fast) |
| Embeddings | **OpenAI** | pay-per-use, ~free at this volume |

Auto-deploy is wired: push to `main` → Render rebuilds the API and Vercel
rebuilds the frontend.

---

## What works and what doesn't on this tier

✅ **Works:** auth/RBAC, repository ingestion (clone → tree-sitter → chunk →
embed → Qdrant), hybrid search (dense + BM25 + RRF), chat / RAG agent with
streaming + tools, memory, GitHub PR create/review, metrics.

⚠️ **Disabled / degraded (free-tier constraints):**

| Feature | Status | Why |
|---------|--------|-----|
| **Sandbox** (run shell commands) | **off** | Needs a host Docker socket; managed PaaS doesn't provide one. Set `SANDBOX_ENABLED=false`. |
| **Cross-encoder reranker** | off | Needs `torch` (too big for 512 MB). Search still runs dense + BM25 + RRF; reranking is skipped automatically. |
| **Celery worker** | replaced | Ingestion runs **inline in a subprocess** (`INGEST_INLINE=true`) instead of a separate always-on worker. |
| **Local embeddings** | replaced | `BAAI/bge-small` needs torch. Uses **OpenAI** embeddings instead (real semantic search). |
| Large repos / long ingests | limited | 512 MB RAM + cold-starts. Ingest **small/medium repos**; keep the repo page open so the SSE stream keeps the dyno awake. |

> To keep the sandbox and local models, you need a Docker-capable VM instead of
> this free split — see the "Full-fidelity" note at the bottom.

---

## Architecture of the deployed app

```
   Browser
     │  https + wss
     ▼
  Vercel (static React SPA)  ──API/WS calls──►  Render (FastAPI)
                                                   │   │   │   │
                          ┌────────────────────────┘   │   │   └──────────┐
                          ▼                             ▼   ▼              ▼
                       Neon (Postgres)        Upstash (Redis)   Qdrant Cloud
                                                  │
                          Chat → Groq        ◄────┘ ingest progress (pub/sub)
                          Embeddings → OpenAI
```

Ingestion: the API spawns `python -m app.ingest_cli <repo> <job>` as a one-shot
subprocess (its own engine + loop), which clones, parses, embeds via OpenAI,
upserts to Qdrant, and publishes progress to Upstash; the browser streams that
progress over SSE.

---

## Step 0 — Prerequisites

- The repo pushed to GitHub (done).
- Accounts (all free to create): [Neon](https://neon.tech),
  [Upstash](https://upstash.com), [Qdrant Cloud](https://cloud.qdrant.io),
  [Groq](https://console.groq.com), [OpenAI](https://platform.openai.com),
  [Render](https://render.com), [Vercel](https://vercel.com).

The deployment configs are already in the repo:
- [`render.yaml`](../render.yaml) — backend blueprint
- [`apps/web/vercel.json`](../apps/web/vercel.json) — frontend config
- [`apps/api/requirements-deploy.txt`](../apps/api/requirements-deploy.txt) — slim deps

---

## Step 1 — Postgres on Neon

1. Create a project → copy the **connection string**.
2. Convert it for this app: change the scheme to `postgresql+asyncpg://` and keep
   `?sslmode=require` (drop any `channel_binding=require`):

   ```
   postgresql+asyncpg://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require
   ```

   This becomes your **`DATABASE_URL`**. (Alembic auto-derives the sync URL.)

---

## Step 2 — Redis on Upstash

1. Create a Redis database (pick a region near your Render region).
2. Copy the **`rediss://`** URL (TLS). This is your **`REDIS_URL`**:

   ```
   rediss://default:PASSWORD@xxxx.upstash.io:6379
   ```

   Used for rate limiting and ingest progress pub/sub.

   > ⚠️ **Paste the URL only — not the `redis-cli` command.** Upstash's Connect
   > tab shows `redis-cli --tls -u rediss://default:PASS@host:6379`. Copy just the
   > part after `-u ` (the `rediss://…` URL), and make sure the password is
   > revealed, not `********`. Pasting the whole `redis-cli …` line fails with
   > `redis_url: Input should be a valid URL`.

> Upstash free tier caps daily commands. Fine for a demo; if you hit limits,
> raise the rate-limit env vars or upgrade.

---

## Step 3 — Vector store on Qdrant Cloud

1. Create a free 1 GB cluster → copy the **cluster URL** and an **API key**.

   ```
   QDRANT_URL=https://xxxxxxxx.cloud.qdrant.io:6333
   QDRANT_API_KEY=<key>
   ```

---

## Step 4 — Chat LLM key (Groq)

1. At [console.groq.com](https://console.groq.com) → create an **API key**.
2. This becomes **`OPENAI_API_KEY`** (the app talks to Groq through its
   OpenAI-compatible endpoint; `render.yaml` already sets the base URL + model
   `llama-3.3-70b-versatile`).

---

## Step 5 — Embeddings key (OpenAI)

Groq has no embeddings endpoint, so embeddings use OpenAI directly.

1. At [platform.openai.com](https://platform.openai.com) → create an **API key**.
2. This becomes **`EMBEDDING_API_KEY`**. Model `text-embedding-3-small` is the
   default — a few cents per repo at most.

> Truly want $0 with no OpenAI account? Set `EMBEDDING_BASE_URL` to any free
> OpenAI-compatible embeddings endpoint, or accept lexical-only search. Real
> semantic search needs a real embedding model.

---

## Step 6 — Backend on Render

1. Render dashboard → **New ► Blueprint** → connect this GitHub repo. Render
   reads [`render.yaml`](../render.yaml) and creates the `ai-coding-agent-api`
   web service.
2. When prompted, fill the **`sync: false`** secrets:

   | Env var | Value |
   |---------|-------|
   | `OPENAI_API_KEY` | your **Groq** key (Step 4) |
   | `EMBEDDING_API_KEY` | your **OpenAI** key (Step 5) |
   | `DATABASE_URL` | Neon URL (Step 1) |
   | `REDIS_URL` | Upstash URL (Step 2) |
   | `QDRANT_URL` | Qdrant URL (Step 3) |
   | `QDRANT_API_KEY` | Qdrant key (Step 3) |
   | `API_CORS_ORIGINS` | your Vercel URL — fill after Step 7, e.g. `https://your-app.vercel.app` |
   | `GITHUB_TOKEN` | optional PAT for PR features (leave blank to skip) |

3. Deploy. The start command runs `alembic upgrade head` then uvicorn. When live,
   note the URL: `https://ai-coding-agent-api.onrender.com`.
4. Verify: open `https://<your-api>.onrender.com/health` → `{"status":"ok"}`, and
   `/docs` for the API.

---

## Step 7 — Frontend on Vercel

1. Vercel → **Add New ► Project** → import the repo.
2. Set **Root Directory** to `apps/web` (Vercel picks up
   [`vercel.json`](../apps/web/vercel.json): framework Vite, `pnpm build`, output `dist`).
3. Add one **Environment Variable**:

   | Env var | Value |
   |---------|-------|
   | `VITE_API_BASE_URL` | `https://<your-api>.onrender.com` |

   (The WebSocket URL for chat/sandbox is derived automatically — `https`→`wss` —
   so you don't set a separate WS variable.)

4. Deploy → note the URL, e.g. `https://your-app.vercel.app`.

---

## Step 8 — Connect CORS and redeploy

1. Back in Render, set **`API_CORS_ORIGINS`** to your exact Vercel URL
   (`https://your-app.vercel.app`, no trailing slash) → save (Render redeploys).
2. Open the Vercel URL, log in with the seeded admin
   (`admin@local.test` / `changeme123!`), and **change the password immediately**
   (then you can set `SEED_ADMIN=false` on Render).

---

## Step 9 — Smoke test

1. Register/login works (proves API + Postgres + JWT + CORS).
2. Add a **small** public repo and ingest it — watch live progress (proves the
   inline subprocess + Qdrant + OpenAI embeddings + SSE).
3. Search it (proves hybrid retrieval).
4. Chat about it (proves Groq + RAG + WebSocket streaming + tools).
5. Memory: "remember X" → appears on the Memory page.

> First request after 15 min idle wakes the Render dyno (~30–60 s). Subsequent
> requests are fast.

---

## Day-to-day

Push to `main` → Render + Vercel auto-redeploy (~2–3 min). Keep
`requirements-deploy.txt` pins in sync with `pyproject.toml` when you add backend
deps.

---

## Environment variable reference (backend)

| Var | Set by | Purpose |
|-----|--------|---------|
| `APP_ENV`, `LOG_FORMAT` | `render.yaml` | production / JSON logs |
| `INGEST_INLINE=true` | `render.yaml` | ingest in-process, no Celery worker |
| `SANDBOX_ENABLED=false` | `render.yaml` | disable Docker sandbox |
| `INGEST_WORKSPACE_DIR=/tmp/aca-workspace` | `render.yaml` | writable clone dir on Render |
| `JWT_SECRET` | Render (generated) | token signing |
| `LLM_PROVIDER=openai`, `OPENAI_BASE_URL`, `OPENAI_DEFAULT_MODEL` | `render.yaml` | chat via Groq |
| `OPENAI_API_KEY` | you | Groq key |
| `EMBEDDING_PROVIDER=openai`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL` | `render.yaml` | embeddings via OpenAI |
| `EMBEDDING_API_KEY` | you | OpenAI key |
| `DATABASE_URL`, `REDIS_URL`, `QDRANT_URL`, `QDRANT_API_KEY` | you | data stores |
| `API_CORS_ORIGINS` | you | allow the Vercel origin |
| `GITHUB_TOKEN` | you (optional) | PR create/review |

---

## Full-fidelity alternative (keep the sandbox + local models)

If you later want **zero functionality lost** — including the sandbox — deploy
the existing `docker compose` stack on a small Docker-capable VM (Hetzner /
DigitalOcean / Lightsail, ~$6–14/mo for 2–4 GB RAM), put Caddy or nginx in front
for HTTPS, and point a domain at it. That runs every service (sandbox, Celery,
local embeddings, Qdrant) exactly as on your laptop. The free split above is the
$0 option that trades the sandbox + local models for cost.
