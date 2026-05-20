"""Unit tests for the AST-aware chunker — exercises the no-symbol fallback and
the symbol-bounded packing.
"""
from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test-secret-min-16-characters-long-xx")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@x:5432/x")
os.environ.setdefault("REDIS_URL", "redis://x:6379/0")
os.environ.setdefault("SEED_ADMIN", "false")

from app.domain.repositories.models import SymbolKind  # noqa: E402
from app.infrastructure.parsers.chunker import chunk_file  # noqa: E402
from app.infrastructure.parsers.tree_sitter import SymbolSpan  # noqa: E402


def test_empty_source_returns_no_chunks() -> None:
    assert chunk_file(source="", symbols=[], target_tokens=100, overlap_tokens=10) == []


def test_short_source_no_symbols_is_single_chunk() -> None:
    source = "print('hi')\nprint('bye')"
    chunks = chunk_file(source=source, symbols=[], target_tokens=400, overlap_tokens=32)
    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2
    assert chunks[0].content == source


def test_source_with_single_symbol_emits_symbol_chunk_and_gap_fills() -> None:
    lines = [
        "# header comment",                  # 1
        "import os",                          # 2
        "",                                   # 3
        "def hello(name):",                   # 4
        "    return f'hello {name}'",         # 5
        "",                                   # 6
        "TAIL = 1",                           # 7
    ]
    source = "\n".join(lines)
    sym = SymbolSpan(
        kind=SymbolKind.function,
        name="hello",
        qualified_name="test.py::hello",
        start_line=4,
        end_line=5,
    )
    chunks = chunk_file(source=source, symbols=[sym], target_tokens=400, overlap_tokens=32)
    # Expect: pre-symbol gap (lines 1-3), symbol (4-5), trailing gap (6-7)
    starts_ends = [(c.start_line, c.end_line) for c in chunks]
    assert (4, 5) in starts_ends
    symbol_chunk = next(c for c in chunks if (c.start_line, c.end_line) == (4, 5))
    assert "def hello" in symbol_chunk.content
    assert symbol_chunk.symbol_index == 0


def test_overlapping_symbols_are_pruned() -> None:
    source = "\n".join(["x"] * 20)
    outer = SymbolSpan(SymbolKind.class_, "Outer", "f::Outer", 1, 20)
    inner = SymbolSpan(SymbolKind.method, "inner", "f::Outer::inner", 5, 10)
    chunks = chunk_file(
        source=source, symbols=[outer, inner], target_tokens=400, overlap_tokens=32
    )
    # Outer should win, no chunk should span exactly the inner range alone
    assert any(c.start_line == 1 and c.end_line == 20 for c in chunks)
    assert not any(c.start_line == 5 and c.end_line == 10 for c in chunks)


def test_oversized_symbol_is_window_split() -> None:
    # Build a 200-line "symbol" that exceeds the target by a lot
    source = "\n".join(f"line_{i}" for i in range(200))
    sym = SymbolSpan(SymbolKind.function, "huge", "f::huge", 1, 200)
    chunks = chunk_file(source=source, symbols=[sym], target_tokens=50, overlap_tokens=8)
    assert len(chunks) > 1
    # All chunks must remain inside the symbol boundary
    for c in chunks:
        assert c.start_line >= 1 and c.end_line <= 200
