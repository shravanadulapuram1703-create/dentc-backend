"""API v1 aggregator: assembles auth, users, and all generated entity routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import audit, auth, balances, billing, ledger, treatment, users
from app.api.v1.registry import build_entity_router

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
# Service endpoints registered before generic CRUD (more specific paths first).
api_router.include_router(billing.router)
api_router.include_router(treatment.router)
api_router.include_router(balances.router)
api_router.include_router(ledger.router)
api_router.include_router(audit.router)
api_router.include_router(build_entity_router())
