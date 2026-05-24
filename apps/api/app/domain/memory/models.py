"""SQLAlchemy model for agent memory."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin, UUIDPkMixin


class MemoryScope(str, enum.Enum):
    user = "user"
    project = "project"
    conversation = "conversation"


class MemorySource(str, enum.Enum):
    explicit = "explicit"     # user said "remember X"
    extracted = "extracted"   # auto-derived from a conversation


class Memory(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_owner", "owner_id"),
        Index("ix_memories_owner_scope", "owner_id", "scope"),
        Index("ix_memories_repo", "repository_id"),
    )

    owner_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[MemoryScope] = mapped_column(
        Enum(MemoryScope, name="memory_scope"), nullable=False, default=MemoryScope.user
    )
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[MemorySource] = mapped_column(
        Enum(MemorySource, name="memory_source"), nullable=False, default=MemorySource.explicit
    )
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
