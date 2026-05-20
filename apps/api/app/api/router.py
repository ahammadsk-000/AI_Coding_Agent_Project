"""Top-level API router. Composes versioned sub-routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth as v1_auth
from app.api.v1 import health as v1_health
from app.api.v1 import users as v1_users

api_router = APIRouter()

# Health/readiness are unversioned, returned at root in main.py.
# All product endpoints live under /api/v1.
api_router.include_router(v1_health.router, prefix="/api/v1", tags=["health"])
api_router.include_router(v1_auth.router, prefix="/api/v1/auth", tags=["auth"])
api_router.include_router(v1_users.router, prefix="/api/v1/users", tags=["users"])
