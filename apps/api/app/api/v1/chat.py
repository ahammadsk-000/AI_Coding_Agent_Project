"""Chat endpoints — REST for CRUD, WebSocket for streaming an agent reply.

WebSocket auth uses `?access_token=...` because browsers cannot set custom
headers on WebSocket connections.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Query, Response, WebSocket, WebSocketDisconnect, status

from app.core.dependencies import CurrentUser, DbSession, get_db
from app.core.exceptions import (
    InvalidTokenError,
    NotFoundError,
    UnauthorizedError,
)
from app.core.security import decode_access_token
from app.domain.chat.repository import MessageRepo
from app.domain.chat.schemas import (
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
    WsError,
)
from app.domain.chat.service import ChatService
from app.domain.users.repository import UserRepository

router = APIRouter()


# ---------- REST ----------

@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate, user: CurrentUser, db: DbSession
) -> ConversationRead:
    conv = await ChatService(db).create_conversation(user, payload)
    return ConversationRead(
        id=conv.id,
        owner_id=conv.owner_id,
        title=conv.title,
        repository_ids=[UUID(r) for r in conv.repository_ids],
        llm_provider=conv.llm_provider,
        llm_model=conv.llm_model,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    user: CurrentUser, db: DbSession
) -> list[ConversationRead]:
    rows = await ChatService(db).list_conversations(user)
    return [
        ConversationRead(
            id=c.id,
            owner_id=c.owner_id,
            title=c.title,
            repository_ids=[UUID(r) for r in c.repository_ids],
            llm_provider=c.llm_provider,
            llm_model=c.llm_model,
            created_at=c.created_at,
            updated_at=c.updated_at,
            message_count=mc,
            last_message_preview=(preview[:200] if preview else None),
        )
        for c, mc, preview in rows
    ]


@router.get("/{conv_id}", response_model=ConversationDetail)
async def get_conversation(
    conv_id: UUID, user: CurrentUser, db: DbSession
) -> ConversationDetail:
    service = ChatService(db)
    conv = await service.get_conversation(user, conv_id)
    msgs = await service.get_messages(user, conv_id)
    return ConversationDetail(
        conversation=ConversationRead(
            id=conv.id,
            owner_id=conv.owner_id,
            title=conv.title,
            repository_ids=[UUID(r) for r in conv.repository_ids],
            llm_provider=conv.llm_provider,
            llm_model=conv.llm_model,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=len(msgs),
        ),
        messages=[MessageRead.model_validate(m) for m in msgs],
    )


@router.patch("/{conv_id}", response_model=ConversationRead)
async def rename_conversation(
    conv_id: UUID, payload: ConversationUpdate, user: CurrentUser, db: DbSession
) -> ConversationRead:
    conv = await ChatService(db).rename_conversation(user, conv_id, payload.title)
    return ConversationRead(
        id=conv.id,
        owner_id=conv.owner_id,
        title=conv.title,
        repository_ids=[UUID(r) for r in conv.repository_ids],
        llm_provider=conv.llm_provider,
        llm_model=conv.llm_model,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/{conv_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conv_id: UUID, user: CurrentUser, db: DbSession
) -> Response:
    await ChatService(db).delete_conversation(user, conv_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- WebSocket ----------

async def _ws_authenticate(ws: WebSocket, token: str | None, db) -> object:
    """Resolve a User from the access_token query string. Closes the WS on failure."""
    if not token:
        await ws.close(code=4401, reason="missing access_token")
        return None
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        await ws.close(code=4401, reason="invalid token")
        return None
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        await ws.close(code=4401, reason="bad token subject")
        return None
    user = await UserRepository(db).get(user_id)
    if user is None or not user.is_active:
        await ws.close(code=4401, reason="user not found")
        return None
    return user


@router.websocket("/{conv_id}/ws")
async def conversation_ws(
    websocket: WebSocket,
    conv_id: UUID,
    access_token: str = Query(default=""),
) -> None:
    """Stream the assistant's reply for a single user message.

    Protocol:
      Client connects, then sends ONE JSON message: {"content": "user text"}.
      Server streams events: token / tool_call_start / tool_call_result /
      citations / done | error, then closes.
    """
    await websocket.accept()
    # WebSocket dependencies don't run via Depends, so we build the DB session
    # manually with the same async-context pattern as the HTTP path.
    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        user = await _ws_authenticate(websocket, access_token, db)
        if user is None:
            return

        # First message from client must be the user's prompt.
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            return
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            await _send(websocket, WsError(message="first frame must be JSON"))
            await websocket.close(code=1003)
            return
        content = str(req.get("content", "")).strip()
        if not content:
            await _send(websocket, WsError(message="content is required"))
            await websocket.close(code=1003)
            return

        service = ChatService(db)
        try:
            async for event in service.send_message_streaming(user, conv_id, content):
                await _send(websocket, event)
        except NotFoundError as exc:
            await _send(websocket, WsError(message=str(exc)))
        except UnauthorizedError as exc:
            await _send(websocket, WsError(message=str(exc)))
        except Exception as exc:
            await _send(websocket, WsError(message=f"{type(exc).__name__}: {exc}"))
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
    finally:
        # Close the DB session
        try:
            await db_gen.aclose()
        except Exception:
            pass


async def _send(ws: WebSocket, payload) -> None:
    """Serialize a Pydantic WS event to JSON and send."""
    if hasattr(payload, "model_dump_json"):
        await ws.send_text(payload.model_dump_json())
    else:
        await ws.send_text(json.dumps(payload))
