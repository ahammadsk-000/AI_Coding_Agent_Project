"""Token-aware context packing.

Given a set of ranked search hits, produce a prompt-ready packing that:
- Groups chunks by file (callers usually want full-file context locality).
- Within a file, sorts chunks by start_line (so they read top-to-bottom).
- Respects a hard `max_tokens` budget across all chunks, plus a small per-chunk
  framing overhead to account for the file path header the consumer will add.

We deduplicate by chunk_id and merge adjacent/overlapping line ranges within a
file (a chunk that spans lines 10-30 supersedes one that spans 15-25).
"""
from __future__ import annotations

from collections import defaultdict

from app.domain.search.schemas import ContextFile, SearchHit

# Tokens reserved per chunk for the "// file.py:10-30" framing the consumer
# is expected to inject when assembling the final prompt.
PER_CHUNK_OVERHEAD = 8


def pack_context(
    hits: list[SearchHit], *, max_tokens: int
) -> tuple[list[ContextFile], int, bool]:
    """Pack `hits` into per-file groupings, honoring `max_tokens`.

    Returns:
        files: list of ContextFile in fused-score order of the best chunk in each file.
        total_tokens: actual tokens included (excludes the framing overhead).
        truncated: True if at least one hit was dropped to fit the budget.
    """
    # Best (= first) hit per file determines file ordering.
    file_order: list[tuple[str, str]] = []  # (file_id, repository_id) pairs, ordered
    by_file: dict[str, list[SearchHit]] = defaultdict(list)
    seen_files: set[str] = set()
    for hit in hits:
        fid = str(hit.file_id)
        if fid not in seen_files:
            seen_files.add(fid)
            file_order.append((fid, str(hit.repository_id)))
        by_file[fid].append(hit)

    # Dedupe & merge ranges within each file.
    for fid in by_file:
        by_file[fid] = _merge_overlapping(by_file[fid])
        by_file[fid].sort(key=lambda h: h.start_line)

    # Greedy: walk files in order, then chunks in line order. Drop chunks that
    # would exceed the budget. Don't keep accepting chunks from later files
    # once we've hit the cap — that produces more useful context locality.
    total = 0
    truncated = False
    out_files: list[ContextFile] = []
    for fid, rid in file_order:
        chunks = by_file[fid]
        kept: list[SearchHit] = []
        for chunk in chunks:
            cost = chunk.token_count + PER_CHUNK_OVERHEAD
            if total + cost > max_tokens:
                truncated = True
                continue
            kept.append(chunk)
            total += chunk.token_count
        if kept:
            head = kept[0]
            out_files.append(
                ContextFile(
                    repository_id=head.repository_id,
                    file_id=head.file_id,
                    file_path=head.file_path,
                    language=head.language,
                    chunks=kept,
                )
            )

    return out_files, total, truncated


def _merge_overlapping(hits: list[SearchHit]) -> list[SearchHit]:
    """Merge chunks whose line ranges overlap. Keeps the highest-score chunk's content."""
    if not hits:
        return []
    # Sort by start_line, then desc by score so the higher-scoring chunk wins ties.
    in_order = sorted(hits, key=lambda h: (h.start_line, -h.score))
    merged: list[SearchHit] = [in_order[0]]
    for hit in in_order[1:]:
        last = merged[-1]
        # overlap or adjacency (allow a 1-line gap to count as adjacent)
        if hit.start_line <= last.end_line + 1:
            # Same chunk_id appearing twice (very rare): keep the earlier one.
            if hit.chunk_id == last.chunk_id:
                continue
            # Choose the higher-scoring chunk's content; expand the range.
            keeper = last if last.score >= hit.score else hit
            merged[-1] = SearchHit(
                chunk_id=keeper.chunk_id,
                repository_id=keeper.repository_id,
                file_id=keeper.file_id,
                file_path=keeper.file_path,
                language=keeper.language,
                start_line=min(last.start_line, hit.start_line),
                end_line=max(last.end_line, hit.end_line),
                token_count=max(last.token_count, hit.token_count),
                score=max(last.score, hit.score),
                dense_score=keeper.dense_score,
                lexical_score=keeper.lexical_score,
                rerank_score=keeper.rerank_score,
                content=keeper.content,
            )
        else:
            merged.append(hit)
    return merged
