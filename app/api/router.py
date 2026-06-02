"""API v1 aggregator: assembles auth, users, and all generated entity routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import account, audit, auth, balances, billing, ledger, office_setup, treatment, users
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
# Account Information module (Setup -> Account Info), nested under /tenants/{id}.
api_router.include_router(account.router)
# Office Setup module (Setup -> Offices). Before generic CRUD so /offices/metadata
# and /offices/{office_id}/* win over the generic /offices/{item_id} route.
api_router.include_router(office_setup.router)
api_router.include_router(build_entity_router())
