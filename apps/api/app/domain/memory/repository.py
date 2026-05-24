"""Data access for memory."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.memory.models import Memory, MemoryScope


class MemoryRepo:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, mem: Memory) -> Memory:
        self.session.add(mem)
        await self.session.flush()
        await self.session.refresh(mem)
        return mem

    async def get(self, memory_id: UUID) -> Memory | None:
        return (
            await self.session.execute(select(Memory).where(Memory.id == memory_id))
        ).scalar_one_or_none()

    async def get_for_owner(self, memory_id: UUID, owner_id: UUID) -> Memory | None:
        stmt = select(Memory).where(
            Memory.id == memory_id, Memory.owner_id == owner_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: UUID, scope: MemoryScope | None = None
    ) -> list[Memory]:
        stmt = select(Memory).where(Memory.owner_id == owner_id)
        if scope is not None:
            stmt = stmt.where(Memory.scope == scope)
        stmt = stmt.order_by(desc(Memory.created_at))
        return list((await self.session.execute(stmt)).scalars())

    async def get_many(self, ids: list[UUID]) -> list[Memory]:
        if not ids:
            return []
        stmt = select(Memory).where(Memory.id.in_(ids))
        return list((await self.session.execute(stmt)).scalars())

    async def delete(self, mem: Memory) -> None:
        await self.session.delete(mem)
        await self.session.flush()

    async def mark_accessed(self, ids: list[UUID]) -> None:
        if not ids:
            return
        mems = await self.get_many(ids)
        now = datetime.utcnow()
        for m in mems:
            m.access_count += 1
            m.last_accessed_at = now
        await self.session.flush()

    async def find_duplicate(self, owner_id: UUID, content: str) -> Memory | None:
        """Exact-text dedupe so 'remember X' twice doesn't create two rows."""
        stmt = select(Memory).where(
            Memory.owner_id == owner_id, Memory.content == content
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
