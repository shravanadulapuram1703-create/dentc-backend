"""API v1 aggregator: assembles auth, users, and all generated entity routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    account,
    audit,
    auth,
    balances,
    billing,
    ledger,
    office_assignment,
    office_setup,
    scheduler,
    treatment,
    users,
    users_extended,
)
from app.api.v1.registry import build_entity_router

api_router = APIRouter()
api_router.include_router(auth.router)
# Extended user routes BEFORE the base users router so literal paths
# (/users/setup-metadata, /users/complete, /users/me/change-password) win over /users/{user_id}.
api_router.include_router(users_extended.router)
api_router.include_router(users_extended.roles_router)
api_router.include_router(users.router)
# Service endpoints registered before generic CRUD (more specific paths first).
api_router.include_router(billing.router)
api_router.include_router(treatment.router)
api_router.include_router(balances.router)
api_router.include_router(ledger.router)
api_router.include_router(audit.router)
# Scheduler module: denormalized feed + status transition + patient context.
# Before generic CRUD so /appointments/scheduler & /patients/{id}/context win.
api_router.include_router(scheduler.appt_router)
api_router.include_router(scheduler.patient_ctx_router)
# Account Information module (Setup -> Account Info), nested under /tenants/{id}.
api_router.include_router(account.router)
# Office Setup module (Setup -> Offices). Before generic CRUD so /offices/metadata
# and /offices/{office_id}/* win over the generic /offices/{item_id} route.
api_router.include_router(office_setup.router)
# Office Assignment (Setup -> Offices -> Office Assignment), nested /offices/{id}/*.
api_router.include_router(office_assignment.router)
api_router.include_router(build_entity_router())
