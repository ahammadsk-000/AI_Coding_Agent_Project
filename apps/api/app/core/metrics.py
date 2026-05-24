"""Prometheus metrics for the platform (Phase 8).

All custom metrics live here so they're defined exactly once (the default
prometheus_client registry rejects duplicate registration on reload). Modules
import the metric objects and call `.labels(...).inc()/observe()`.

Naming follows Prometheus conventions: `aca_<area>_<thing>_<unit>`.
Counters end in `_total`; histograms in `_seconds`.
"""
from __future__ import annotations

from prometheus_client import Counter, Histogram

# ---------- HTTP ----------
http_requests_total = Counter(
    "aca_http_requests_total",
    "HTTP requests handled by the API.",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "aca_http_request_duration_seconds",
    "HTTP request latency.",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# ---------- LLM ----------
llm_requests_total = Counter(
    "aca_llm_requests_total",
    "LLM chat calls.",
    ["provider", "model", "status"],   # status: ok | error
)
llm_request_duration_seconds = Histogram(
    "aca_llm_request_duration_seconds",
    "LLM call wall-clock latency.",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
)
llm_tokens_total = Counter(
    "aca_llm_tokens_total",
    "Tokens processed by the LLM.",
    ["provider", "model", "kind"],     # kind: prompt | completion
)
llm_cost_usd_total = Counter(
    "aca_llm_cost_usd_total",
    "Estimated LLM spend in USD (0 for local models).",
    ["provider", "model"],
)

# ---------- Tools / agent ----------
tool_calls_total = Counter(
    "aca_tool_calls_total",
    "Agent tool invocations.",
    ["tool", "status"],                # status: ok | error
)

# ---------- Chat ----------
chat_messages_total = Counter(
    "aca_chat_messages_total",
    "Chat messages persisted.",
    ["role"],                          # user | assistant | tool
)

# ---------- Search ----------
search_requests_total = Counter(
    "aca_search_requests_total",
    "Search queries served.",
    ["mode", "reranked"],              # mode: hybrid|dense|lexical, reranked: true|false
)
search_duration_seconds = Histogram(
    "aca_search_duration_seconds",
    "Search latency.",
    ["mode"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

# ---------- Ingestion ----------
ingest_jobs_total = Counter(
    "aca_ingest_jobs_total",
    "Repository ingest jobs by terminal status.",
    ["status"],                        # succeeded | failed
)
ingest_files_indexed_total = Counter(
    "aca_ingest_files_indexed_total",
    "Files indexed across all ingests.",
)
ingest_chunks_indexed_total = Counter(
    "aca_ingest_chunks_indexed_total",
    "Chunks embedded across all ingests.",
)

# ---------- Memory ----------
memory_writes_total = Counter(
    "aca_memory_writes_total",
    "Memories stored.",
    ["scope", "source"],
)
memory_recalls_total = Counter(
    "aca_memory_recalls_total",
    "Memory recall queries that returned at least one hit.",
)
