"""Phase 7: agent memory.

A `memories` table holds durable facts the agent should recall across
conversations. Each memory is scoped:
  - user:         applies to everything the user does
  - project:      tied to a specific repository
  - conversation: tied to one conversation (rarely surfaced cross-chat)

The fact text is embedded and stored in a shared Qdrant collection
(`aca_memories`) for semantic recall; this table is the source of truth for
the text + metadata. `importance` and `last_accessed_at` support future decay
ranking.

Revision ID: 0005_memory
Revises: 0004_chat
Create Date: 2026-05-22
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_memory"
down_revision: str | None = "0004_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    memory_scope = postgresql.ENUM(
        "user", "project", "conversation", name="memory_scope", create_type=False
    )
    memory_source = postgresql.ENUM(
        "explicit", "extracted", name="memory_source", create_type=False
    )
    bind = op.get_bind()
    memory_scope.create(bind, checkfirst=True)
    memory_source.create(bind, checkfirst=True)

    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", memory_scope, nullable=False, server_default="user"),
        sa.Column(
            "repository_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", memory_source, nullable=False, server_default="explicit"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("vector_id", sa.String(64), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memories_owner", "memories", ["owner_id"])
    op.create_index("ix_memories_owner_scope", "memories", ["owner_id", "scope"])
    op.create_index("ix_memories_repo", "memories", ["repository_id"])


def downgrade() -> None:
    op.drop_index("ix_memories_repo", table_name="memories")
    op.drop_index("ix_memories_owner_scope", table_name="memories")
    op.drop_index("ix_memories_owner", table_name="memories")
    op.drop_table("memories")
    op.execute(sa.text("DROP TYPE IF EXISTS memory_source"))
    op.execute(sa.text("DROP TYPE IF EXISTS memory_scope"))
