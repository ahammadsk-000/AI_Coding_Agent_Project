"""AST-aware code chunker.

Strategy
--------
1. If the file has extractable symbols (function/class/method/interface), each
   symbol becomes one chunk; symbols larger than `target_tokens` are split into
   overlapping line windows that stay within the symbol boundary.
2. Lines outside any symbol (top-of-file imports, module-level code, comments)
   are grouped into line-window chunks.
3. Files with no symbol support (markdown, JSON, unknown languages) fall back to
   pure line-window chunking.

Token counting uses `tiktoken` (cl100k_base) — close enough for budgeting across
modern LLMs.
"""
from __future__ import annotations

from dataclasses import dataclass

import tiktoken

from app.infrastructure.parsers.tree_sitter import SymbolSpan

_ENCODER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    if not text:
        return 0
    return len(_ENCODER.encode(text, disallowed_special=()))


@dataclass(slots=True, frozen=True)
class Chunk:
    content: str
    start_line: int       # 1-based inclusive
    end_line: int         # 1-based inclusive
    token_count: int
    symbol_index: int | None = None   # index into the symbols list, or None


def _slice_lines(lines: list[str], start_1: int, end_1: int) -> str:
    return "\n".join(lines[start_1 - 1 : end_1])


def _window_chunks(
    lines: list[str],
    *,
    start_line: int,
    end_line: int,
    target_tokens: int,
    overlap_tokens: int,
    symbol_index: int | None = None,
) -> list[Chunk]:
    """Greedy line-window packing within [start_line, end_line]."""
    chunks: list[Chunk] = []
    i = start_line
    while i <= end_line:
        cur_lines: list[str] = []
        cur_tokens = 0
        j = i
        while j <= end_line:
            line = lines[j - 1]
            line_tokens = count_tokens(line) + 1  # +1 for newline
            if cur_tokens + line_tokens > target_tokens and cur_lines:
                break
            cur_lines.append(line)
            cur_tokens += line_tokens
            j += 1
        if not cur_lines:
            # Single line longer than target — emit it anyway
            cur_lines.append(lines[i - 1])
            cur_tokens = count_tokens(cur_lines[0])
            j = i + 1
        chunks.append(
            Chunk(
                content="\n".join(cur_lines),
                start_line=i,
                end_line=i + len(cur_lines) - 1,
                token_count=cur_tokens,
                symbol_index=symbol_index,
            )
        )
        if j > end_line:
            break
        # Compute overlap: rewind by ~overlap_tokens of lines
        overlap_lines = 0
        acc = 0
        while overlap_lines < len(cur_lines) - 1 and acc < overlap_tokens:
            acc += count_tokens(cur_lines[-(overlap_lines + 1)])
            overlap_lines += 1
        i = j - overlap_lines
        if i <= chunks[-1].start_line:
            i = chunks[-1].end_line + 1
    return chunks


def chunk_file(
    *,
    source: str,
    symbols: list[SymbolSpan],
    target_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    """Produce ordered, deduplicated chunks for one file."""
    if not source:
        return []
    lines = source.splitlines()
    total = len(lines)
    if total == 0:
        return []

    # Sort symbols by start line; remove overlaps (prefer outer / longer)
    sym_sorted = sorted(symbols, key=lambda s: (s.start_line, -s.end_line))
    pruned: list[SymbolSpan] = []
    last_end = 0
    for s in sym_sorted:
        if s.start_line <= last_end:
            continue
        pruned.append(s)
        last_end = s.end_line

    chunks: list[Chunk] = []

    if not pruned:
        return _window_chunks(
            lines,
            start_line=1,
            end_line=total,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
        )

    cursor = 1
    for idx, sym in enumerate(pruned):
        if sym.start_line > cursor:
            # gap-fill (top-of-file, between symbols)
            chunks.extend(
                _window_chunks(
                    lines,
                    start_line=cursor,
                    end_line=sym.start_line - 1,
                    target_tokens=target_tokens,
                    overlap_tokens=overlap_tokens,
                )
            )
        sym_text = _slice_lines(lines, sym.start_line, sym.end_line)
        sym_tokens = count_tokens(sym_text)
        if sym_tokens <= target_tokens * 2:  # tolerate slight overage to keep symbol whole
            chunks.append(
                Chunk(
                    content=sym_text,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    token_count=sym_tokens,
                    symbol_index=idx,
                )
            )
        else:
            chunks.extend(
                _window_chunks(
                    lines,
                    start_line=sym.start_line,
                    end_line=sym.end_line,
                    target_tokens=target_tokens,
                    overlap_tokens=overlap_tokens,
                    symbol_index=idx,
                )
            )
        cursor = sym.end_line + 1

    if cursor <= total:
        chunks.extend(
            _window_chunks(
                lines,
                start_line=cursor,
                end_line=total,
                target_tokens=target_tokens,
                overlap_tokens=overlap_tokens,
            )
        )
    return chunks
