"""Phase 3: Full-text search index on code_chunks.

Adds a generated `content_tsv` tsvector column populated from `content`, plus a
GIN index to make BM25-style ranked search via ts_rank/ts_rank_cd fast.

We use a STORED generated column so writes don't need an explicit UPDATE trigger
and reads don't recompute the vector. English text-search config is used as a
default — it tokenizes code reasonably well thanks to the configurable
parser/dictionary chain, and adding language-aware configs is a future ADR.

Revision ID: 0003_search
Revises: 0002_repositories
Create Date: 2026-05-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_search"
down_revision: str | None = "0002_repositories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Generated column. Postgres 12+ supports STORED generated columns.
    op.execute(
        sa.text(
            """
            ALTER TABLE code_chunks
            ADD COLUMN IF NOT EXISTS content_tsv tsvector
                GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
            """
        )
    )
    op.create_index(
        "ix_codechunks_content_tsv",
        "code_chunks",
        ["content_tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_codechunks_content_tsv", table_name="code_chunks")
    op.execute(sa.text("ALTER TABLE code_chunks DROP COLUMN IF EXISTS content_tsv"))
