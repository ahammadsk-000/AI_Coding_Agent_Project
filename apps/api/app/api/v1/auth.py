"""Auth endpoints: register, login, refresh, logout."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.core.dependencies import CurrentUser, DbSession
from app.domain.auth.schemas import LoginRequest, LoginResponse, RefreshRequest, TokenPair
from app.domain.auth.service import AuthService
from app.domain.users.schemas import UserCreate, UserRead
from app.domain.users.service import UserService

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: DbSession) -> UserRead:
    user = await UserService(db).register(payload)
    return UserRead.model_validate(user)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, db: DbSession) -> LoginResponse:
    user, tokens = await AuthService(db).authenticate(
        email=payload.email,
        password=payload.password,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return LoginResponse(user=UserRead.model_validate(user), tokens=tokens)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, request: Request, db: DbSession) -> TokenPair:
    _, tokens = await AuthService(db).refresh(
        raw_refresh=payload.refresh_token,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: RefreshRequest, request: Request, db: DbSession, user: CurrentUser
) -> Response:
    await AuthService(db).logout(
        raw_refresh=payload.refresh_token,
        user=user,
        ip=_client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
