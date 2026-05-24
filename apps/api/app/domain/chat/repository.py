"""Data access for chat."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.chat.models import Conversation, Message, MessageRole


class ConversationRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, conv: Conversation) -> Conversation:
        self.session.add(conv)
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def get(self, conv_id: UUID) -> Conversation | None:
        return (
            await self.session.execute(select(Conversation).where(Conversation.id == conv_id))
        ).scalar_one_or_none()

    async def get_for_owner(self, conv_id: UUID, owner_id: UUID) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conv_id, Conversation.owner_id == owner_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_owner(self, owner_id: UUID) -> list[tuple[Conversation, int, str | None]]:
        """Return conversations with their message count + last user/assistant preview."""
        # Subquery: last assistant or user message per conversation (newest by created_at).
        last_msg_subq = (
            select(
                Message.conversation_id,
                Message.content,
                func.row_number()
                .over(
                    partition_by=Message.conversation_id,
                    order_by=desc(Message.created_at),
                )
                .label("rn"),
            )
            .where(Message.role.in_([MessageRole.user, MessageRole.assistant]))
            .subquery()
        )
        last_msg = (
            select(last_msg_subq.c.conversation_id, last_msg_subq.c.content)
            .where(last_msg_subq.c.rn == 1)
            .subquery()
        )

        msg_count = (
            select(Message.conversation_id, func.count(Message.id).label("c"))
            .group_by(Message.conversation_id)
            .subquery()
        )

        stmt = (
            select(Conversation, func.coalesce(msg_count.c.c, 0), last_msg.c.content)
            .outerjoin(msg_count, msg_count.c.conversation_id == Conversation.id)
            .outerjoin(last_msg, last_msg.c.conversation_id == Conversation.id)
            .where(Conversation.owner_id == owner_id)
            .order_by(desc(Conversation.updated_at))
        )
        rows = (await self.session.execute(stmt)).all()
        return [(row[0], int(row[1]), row[2]) for row in rows]

    async def delete(self, conv: Conversation) -> None:
        await self.session.delete(conv)
        await self.session.flush()

    async def touch(self, conv: Conversation) -> None:
        """Mark a conversation as recently active (bumps updated_at)."""
        from datetime import datetime

        conv.updated_at = datetime.utcnow()
        await self.session.flush()


class MessageRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, msg: Message) -> Message:
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def list_for_conversation(self, conv_id: UUID) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conv_id)
            .order_by(Message.created_at)
        )
        return list((await self.session.execute(stmt)).scalars())

    async def to_openai_history(self, conv_id: UUID) -> list[dict[str, Any]]:
        """Render message rows as OpenAI chat-completions style dicts."""
        msgs = await self.list_for_conversation(conv_id)
        out: list[dict[str, Any]] = []
        for m in msgs:
            d: dict[str, Any] = {"role": m.role.value, "content": m.content}
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            out.append(d)
        return out
