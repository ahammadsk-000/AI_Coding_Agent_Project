"""Token counting + cost estimation (Phase 8).

Token counting uses tiktoken's cl100k_base — accurate for OpenAI models and a
good-enough approximation for Llama-family tokenizers (typically within ~10%).

Cost is estimated from a static price table (USD per 1M tokens). Local Ollama
models are free, so they map to 0. Update PRICES as needed; unknown models
default to free.
"""
from __future__ import annotations

import tiktoken

_ENCODER = tiktoken.get_encoding("cl100k_base")

# USD per 1,000,000 tokens, (prompt, completion). Local models are free.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODER.encode(text, disallowed_special=()))


def count_message_tokens(messages: list[dict]) -> int:
    """Rough prompt-token count for a list of {role, content} dicts.

    Adds a small per-message overhead to approximate chat-format framing.
    """
    total = 0
    for m in messages:
        total += count_tokens(str(m.get("content", "")))
        total += 4  # role + delimiters framing overhead
    return total


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Estimate spend for one call. Local/unknown models → 0.0."""
    price = PRICES.get(model)
    if price is None:
        # try a prefix match (e.g. "gpt-4o-mini-2024-07-18")
        for name, p in PRICES.items():
            if model.startswith(name):
                price = p
                break
    if price is None:
        return 0.0
    in_rate, out_rate = price
    return (prompt_tokens / 1_000_000) * in_rate + (completion_tokens / 1_000_000) * out_rate
