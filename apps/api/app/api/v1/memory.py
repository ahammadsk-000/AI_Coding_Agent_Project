"""Memory endpoints — list, create, delete durable agent memories."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.domain.memory.models import MemoryScope, MemorySource
from app.domain.memory.schemas import MemoryCreate, MemoryRead
from app.domain.memory.service import MemoryService

router = APIRouter()


@router.get("", response_model=list[MemoryRead])
async def list_memories(
    user: CurrentUser,
    db: DbSession,
    scope: str | None = Query(default=None),
) -> list[MemoryRead]:
    scope_enum = MemoryScope(scope) if scope in {"user", "project", "conversation"} else None
    mems = await MemoryService(db).list_memories(user, scope_enum)
    return [MemoryRead.model_validate(m) for m in mems]


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate, user: CurrentUser, db: DbSession
) -> MemoryRead:
    mem = await MemoryService(db).remember(
        user,
        content=payload.content,
        scope=MemoryScope(payload.scope),
        repository_id=payload.repository_id,
        conversation_id=payload.conversation_id,
        source=MemorySource.explicit,
        importance=payload.importance,
    )
    return MemoryRead.model_validate(mem)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: UUID, user: CurrentUser, db: DbSession
) -> Response:
    await MemoryService(db).forget(user, memory_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
