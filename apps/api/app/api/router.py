"""Top-level API router. Composes versioned sub-routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth as v1_auth
from app.api.v1 import chat as v1_chat
from app.api.v1 import github as v1_github
from app.api.v1 import health as v1_health
from app.api.v1 import memory as v1_memory
from app.api.v1 import repositories as v1_repos
from app.api.v1 import sandbox as v1_sandbox
from app.api.v1 import search as v1_search
from app.api.v1 import users as v1_users

api_router = APIRouter()

# Health/readiness are unversioned, returned at root in main.py.
# All product endpoints live under /api/v1.
api_router.include_router(v1_health.router, prefix="/api/v1", tags=["health"])
api_router.include_router(v1_auth.router, prefix="/api/v1/auth", tags=["auth"])
api_router.include_router(v1_users.router, prefix="/api/v1/users", tags=["users"])
api_router.include_router(v1_repos.router, prefix="/api/v1/repositories", tags=["repositories"])
api_router.include_router(v1_search.search_router, prefix="/api/v1/search", tags=["search"])
api_router.include_router(v1_search.context_router, prefix="/api/v1/context", tags=["context"])
api_router.include_router(v1_chat.router, prefix="/api/v1/conversations", tags=["chat"])
api_router.include_router(v1_memory.router, prefix="/api/v1/memories", tags=["memory"])
api_router.include_router(v1_sandbox.router, prefix="/api/v1/sandbox", tags=["sandbox"])
api_router.include_router(v1_github.router, prefix="/api/v1/github", tags=["github"])
