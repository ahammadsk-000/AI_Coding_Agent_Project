"""repositories context: repositories, repository_files, code_symbols, code_chunks, ingest_jobs

Revision ID: 0002_repositories
Revises: 0001_initial
Create Date: 2026-05-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_repositories"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- enums ----
    repository_source = postgresql.ENUM("git", "local", "github", name="repository_source")
    repository_status = postgresql.ENUM("new", "ingesting", "ready", "failed", name="repository_status")
    ingest_status = postgresql.ENUM(
        "queued", "running", "succeeded", "failed", "canceled", name="ingest_status"
    )
    symbol_kind = postgresql.ENUM(
        "function", "method", "class", "interface", "module", "variable", "other",
        name="symbol_kind",
    )
    for e in (repository_source, repository_status, ingest_status, symbol_kind):
        e.create(op.get_bind(), checkfirst=True)

    # ---- repositories ----
    op.create_table(
        "repositories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", repository_source, nullable=False, server_default="git"),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("default_branch", sa.String(255), nullable=False, server_default="main"),
        sa.Column("status", repository_status, nullable=False, server_default="new"),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True)),
        sa.Column("stats", postgresql.JSONB()),
        sa.Column("qdrant_collection", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", "url", name="uq_repositories_owner_url"),
    )
    op.create_index("ix_repositories_owner", "repositories", ["owner_id"])

    # ---- repository_files ----
    op.create_table(
        "repository_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("language", sa.String(32)),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("repository_id", "path", name="uq_repofiles_repo_path"),
    )
    op.create_index("ix_repofiles_repo", "repository_files", ["repository_id"])
    op.create_index("ix_repofiles_lang", "repository_files", ["language"])

    # ---- code_symbols ----
    op.create_table(
        "code_symbols",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("file_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", symbol_kind, nullable=False, server_default="other"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("qualified_name", sa.String(512), nullable=False),
        sa.Column("signature", sa.Text()),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_codesymbols_file", "code_symbols", ["file_id"])
    op.create_index("ix_codesymbols_qname", "code_symbols", ["qualified_name"])

    # ---- code_chunks ----
    op.create_table(
        "code_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("code_symbols.id", ondelete="SET NULL")),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("language", sa.String(32)),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("vector_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_codechunks_repo", "code_chunks", ["repository_id"])
    op.create_index("ix_codechunks_file", "code_chunks", ["file_id"])
    op.create_index("ix_codechunks_vector", "code_chunks", ["vector_id"])

    # ---- ingest_jobs ----
    op.create_table(
        "ingest_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", ingest_status, nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column("files_seen", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("files_indexed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("chunks_indexed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_indexed", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ingestjobs_repo", "ingest_jobs", ["repository_id"])


def downgrade() -> None:
    for tbl in ("ingest_jobs", "code_chunks", "code_symbols", "repository_files", "repositories"):
        op.drop_table(tbl)
    for name in ("symbol_kind", "ingest_status", "repository_status", "repository_source"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
