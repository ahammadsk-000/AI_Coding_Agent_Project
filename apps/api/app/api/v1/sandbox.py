"""Sandbox endpoints (Phase 5).

- POST /api/v1/sandbox/classify  → safety verdict for a command (REST)
- WS   /api/v1/sandbox/ws        → run a command in an isolated container, stream output

The WS enforces the approval gate: a command the classifier marks "approval"
only runs if the client sets `approved: true`; "blocked" never runs.
"""
from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.dependencies import CurrentUser, DbSession, get_db
from app.core.exceptions import InvalidTokenError
from app.core.security import decode_access_token
from app.domain.repositories.repository import RepositoryRepo
from app.domain.sandbox.schemas import (
    ClassifyRequest,
    ClassifyResponse,
    SandboxRunRequest,
)
from app.domain.users.repository import UserRepository
from app.infrastructure.sandbox.policy import classify
from app.infrastructure.sandbox.service import SandboxService

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
async def classify_command(
    payload: ClassifyRequest, _user: CurrentUser
) -> ClassifyResponse:
    c = classify(payload.command)
    return ClassifyResponse(verdict=c.verdict, reason=c.reason)


async def _ws_auth(ws: WebSocket, token: str | None, db):
    if not token:
        await ws.close(code=4401, reason="missing access_token")
        return None
    try:
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (InvalidTokenError, KeyError, ValueError):
        await ws.close(code=4401, reason="invalid token")
        return None
    user = await UserRepository(db).get(user_id)
    if user is None or not user.is_active:
        await ws.close(code=4401, reason="user not found")
        return None
    return user


@router.websocket("/ws")
async def sandbox_ws(websocket: WebSocket, access_token: str = Query(default="")) -> None:
    await websocket.accept()
    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        user = await _ws_auth(websocket, access_token, db)
        if user is None:
            return

        try:
            raw = await websocket.receive_text()
            req = SandboxRunRequest.model_validate_json(raw)
        except WebSocketDisconnect:
            return
        except Exception as exc:
            await _send(websocket, {"kind": "error", "text": f"bad request: {exc}"})
            await websocket.close(code=1003)
            return

        # Classify + enforce the approval gate.
        verdict = classify(req.command)
        await _send(
            websocket,
            {"kind": "classify", "verdict": verdict.verdict, "reason": verdict.reason},
        )
        if verdict.verdict == "blocked":
            await _send(websocket, {"kind": "error", "text": f"command blocked: {verdict.reason}"})
            await websocket.close()
            return
        if verdict.verdict == "approval" and not req.approved:
            await _send(
                websocket,
                {"kind": "needs_approval", "text": f"approval required: {verdict.reason}"},
            )
            await websocket.close()
            return

        # Resolve the repo path (if any) and authorize ownership.
        repo_subpath: str | None = None
        if req.repository_id is not None:
            repo = await RepositoryRepo(db).get_for_owner(req.repository_id, user.id)
            if repo is None:
                await _send(websocket, {"kind": "error", "text": "repository not found"})
                await websocket.close()
                return
            repo_subpath = str(repo.id)

        service = SandboxService()
        try:
            async for ev in service.run_stream(command=req.command, repo_subpath=repo_subpath):
                await _send(
                    websocket,
                    {"kind": ev.kind, "text": ev.text, "exit_code": ev.exit_code},
                )
        except Exception as exc:
            await _send(websocket, {"kind": "error", "text": f"{type(exc).__name__}: {exc}"})
        finally:
            try:
                await websocket.close()
            except Exception:
                pass
    finally:
        try:
            await db_gen.aclose()
        except Exception:
            pass


async def _send(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload))
