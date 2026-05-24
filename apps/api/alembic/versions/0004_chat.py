"""Phase 4: conversations + messages tables.

Schema
------
- `conversations`: a chat session belonging to a user. Optionally scoped to one
  or more repositories (the RAG context boundary).
- `messages`: one user / assistant / tool turn inside a conversation. The
  `role` enum follows the OpenAI chat-completions convention. `tool_calls` and
  `tool_call_id` carry function-call metadata so we can replay agent decisions.
- `citations` are stored denormalized inside the message row's JSONB (one row
  per message, each holds a list of `{file_path, start_line, end_line, ...}`
  references) — there's no separate citation table.

Revision ID: 0004_chat
Revises: 0003_search
Create Date: 2026-05-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_chat"
down_revision: str | None = "0003_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- enums ----
    message_role = postgresql.ENUM(
        "system", "user", "assistant", "tool",
        name="message_role", create_type=False,
    )
    bind = op.get_bind()
    message_role.create(bind, checkfirst=True)

    # ---- conversations ----
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False, server_default="New chat"),
        sa.Column("repository_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("llm_provider", sa.String(32), nullable=False),
        sa.Column("llm_model", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_conversations_owner", "conversations", ["owner_id"])

    # ---- messages ----
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
        sa.Column("tool_call_id", sa.String(128), nullable=True),
        sa.Column("citations", postgresql.JSONB(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_conversation", "messages", ["conversation_id"])
    op.create_index("ix_messages_conv_created", "messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_messages_conv_created", table_name="messages")
    op.drop_index("ix_messages_conversation", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_owner", table_name="conversations")
    op.drop_table("conversations")
    op.execute(sa.text("DROP TYPE IF EXISTS message_role"))
