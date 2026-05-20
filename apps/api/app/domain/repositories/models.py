"""SQLAlchemy models for the repositories bounded context."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPkMixin


# ---------- enums ----------
class RepositorySource(str, enum.Enum):
    git = "git"
    local = "local"
    github = "github"


class RepositoryStatus(str, enum.Enum):
    new = "new"
    ingesting = "ingesting"
    ready = "ready"
    failed = "failed"


class IngestStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    canceled = "canceled"


class SymbolKind(str, enum.Enum):
    function = "function"
    method = "method"
    class_ = "class"
    interface = "interface"
    module = "module"
    variable = "variable"
    other = "other"


# ---------- entities ----------
class Repository(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("owner_id", "url", name="uq_repositories_owner_url"),
        Index("ix_repositories_owner", "owner_id"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[RepositorySource] = mapped_column(
        Enum(RepositorySource, name="repository_source"),
        nullable=False,
        default=RepositorySource.git,
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus, name="repository_status"),
        nullable=False,
        default=RepositoryStatus.new,
    )
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict | None] = mapped_column(JSONB)
    qdrant_collection: Mapped[str | None] = mapped_column(String(128))

    files: Mapped[list[RepositoryFile]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    ingest_jobs: Mapped[list[IngestJob]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class RepositoryFile(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "repository_files"
    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_repofiles_repo_path"),
        Index("ix_repofiles_repo", "repository_id"),
        Index("ix_repofiles_lang", "language"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str | None] = mapped_column(String(32))
    sha: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    repository: Mapped[Repository] = relationship(back_populates="files")
    symbols: Mapped[list[CodeSymbol]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[CodeChunk]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class CodeSymbol(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "code_symbols"
    __table_args__ = (
        Index("ix_codesymbols_file", "file_id"),
        Index("ix_codesymbols_qname", "qualified_name"),
    )

    file_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[SymbolKind] = mapped_column(
        Enum(SymbolKind, name="symbol_kind"), nullable=False, default=SymbolKind.other
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    qualified_name: Mapped[str] = mapped_column(String(512), nullable=False)
    signature: Mapped[str | None] = mapped_column(Text)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)

    file: Mapped[RepositoryFile] = relationship(back_populates="symbols")
    chunks: Mapped[list[CodeChunk]] = relationship(back_populates="symbol")


class CodeChunk(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "code_chunks"
    __table_args__ = (
        Index("ix_codechunks_repo", "repository_id"),
        Index("ix_codechunks_file", "file_id"),
        Index("ix_codechunks_vector", "vector_id"),
    )

    repository_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repository_files.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("code_symbols.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(32))
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector_id: Mapped[str | None] = mapped_column(String(64))  # qdrant point id

    file: Mapped[RepositoryFile] = relationship(back_populates="chunks")
    symbol: Mapped[CodeSymbol | None] = relationship(back_populates="chunks")


class IngestJob(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "ingest_jobs"
    __table_args__ = (Index("ix_ingestjobs_repo", "repository_id"),)

    repository_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus, name="ingest_status"), nullable=False, default=IngestStatus.queued
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    files_seen: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    files_indexed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    chunks_indexed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    bytes_indexed: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(64))

    repository: Mapped[Repository] = relationship(back_populates="ingest_jobs")
