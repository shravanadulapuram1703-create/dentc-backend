"""API v1 aggregator: assembles auth, users, and all generated entity routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    account,
    appointnow,
    audit,
    auth,
    balances,
    billing,
    fee_schedules,
    groups,
    icd_codes,
    imaging,
    insurance,
    ledger,
    letters,
    messaging,
    messaging_ws,
    office_assignment,
    office_setup,
    patient_intake,
    patients_extra,
    payment_plans,
    perio,
    pick_lists,
    progress_notes,
    refunds,
    restorative,
    procedure_codes,
    provider_setup,
    reports,
    scheduler,
    statements,
    support,
    transactions,
    treatment,
    users,
    users_extended,
    utilities,
)
from app.api.v1.registry import build_entity_router

api_router = APIRouter()
api_router.include_router(auth.router)
# Extended user routes BEFORE the base users router so literal paths
# (/users/setup-metadata, /users/complete, /users/me/change-password) win over /users/{user_id}.
api_router.include_router(users_extended.router)
api_router.include_router(users_extended.roles_router)
api_router.include_router(users.router)
# Security -> Groups: rights catalog + group->rights assignment + copy.
# Before generic CRUD so /user-groups/{id}/rights & /{id}/copy win over /user-groups/{item_id}.
api_router.include_router(groups.permissions_router)
api_router.include_router(groups.groups_router)
# Service endpoints registered before generic CRUD (more specific paths first).
api_router.include_router(billing.router)
api_router.include_router(treatment.router)
# Fee Schedule supplements (restore / new-version). Before generic CRUD so
# /fee-schedules/{id}/restore & /new-version win over /fee-schedules/{item_id}.
api_router.include_router(fee_schedules.router)
api_router.include_router(balances.router)
api_router.include_router(ledger.router)
# Transactions module: office financial dashboards (DASH-1..5) + unified
# cross-patient feed/search (SRCH-1/3), refunds & reversals (REF-1..4), and
# patient statement generation/delivery (STMT-1..3). Before generic CRUD so the
# literal /offices/{id}/financial-summary, /patients/{id}/refunds and
# /patients/{id}/statements sub-paths win over /{item_id}.
api_router.include_router(transactions.router)
api_router.include_router(refunds.router)
api_router.include_router(statements.router)
# Payment-plan contracts: instalment posting (PP-2), server-side amortisation
# (OPP-9/RPP-5) and the contract/coupon documents (PP-3). Before generic CRUD so
# /patient-ins-payment-plans/{id}/post & /payment-plans/... win over /{item_id}.
api_router.include_router(payment_plans.router)
api_router.include_router(audit.router)
# Reports module: practice-wide aggregation (summary/trends/AR/aging).
api_router.include_router(reports.router)
# Help Center support tickets (Jira proxy) + Utilities execution/audit.
api_router.include_router(support.router)
api_router.include_router(utilities.router)
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
# Provider Setup module (Setup -> Providers). Before generic CRUD so
# /providers/{id}/schedule|holidays|watermarks|referral-offices|user win over /providers/{item_id}.
api_router.include_router(provider_setup.router)
api_router.include_router(provider_setup.carrier_router)
# Procedure Code supplements (stats / per-code insurance-rules). Before generic
# CRUD so /procedure-codes/stats wins over /procedure-codes/{item_id} (the code).
api_router.include_router(procedure_codes.router)
# APPT-10: procedure-code category taxonomy (own prefix, no CRUD collision).
api_router.include_router(procedure_codes.category_router)
# ICD codes bulk-status. Before generic CRUD so /icd-codes/bulk-status wins.
api_router.include_router(icd_codes.router)
# Insurance supplements (eligibility verify). Before generic CRUD so
# /insurance-subscribers/{id}/verify-eligibility wins over /{item_id}.
api_router.include_router(insurance.router)
# Pick List supplements (atomic items replace + cascade delete). Before generic
# CRUD so /questionnaire-headers/{id}/options & /{id}/cascade win over /{item_id}.
api_router.include_router(pick_lists.router)
# Patients module supplemental: documents, claim detail/lifecycle/attachments,
# progress-note sign, duplicate-check (before generic CRUD for literal paths).
api_router.include_router(patients_extra.documents_router)
api_router.include_router(patients_extra.claims_router)
api_router.include_router(patients_extra.consents_router)
api_router.include_router(patients_extra.dup_router)
# Letters module: merge-field catalog + server-side render/batch (LTR-5), the
# aggregate /patients/{id}/letter-context (LTR-6) and the consent-form bucket
# listing (LTR-1). Before generic CRUD so /letters/* and the literal
# /patients/{id}/letter-context win over /{item_id}.
api_router.include_router(letters.router)
api_router.include_router(letters.patient_router)
api_router.include_router(letters.consent_forms_router)
# Add-Patient intake extras: /patients/register (composite) + /patients/{id}/opening-balance
# + /patients/{id}/account-plans (LEG-5), and /responsible-parties/{id}/patients roster (LEG-14).
# Before generic CRUD so these literal sub-paths win over /{item_id}.
api_router.include_router(patient_intake.router)
# Add/Edit Patient checkbox-integrity rules (/metadata/patient-flag-rules).
api_router.include_router(patient_intake.metadata_router)
api_router.include_router(patient_intake.rp_router)
api_router.include_router(patient_intake.appt_router)
# Progress-notes supplements: sign (PN-2) + per-note attachments (PN-3) + macro
# categories (PN-6). Before generic CRUD so literal sub-paths win over /{item_id}.
api_router.include_router(progress_notes.router)
api_router.include_router(progress_notes.macro_router)
# Perio charting supplements (bulk upsert / compare / settings-me). Before generic
# CRUD so /perio-exams/compare, /perio-exams/{id}/details and
# /perio-chart-settings/me win over the generic /{item_id} routes.
api_router.include_router(perio.router)
# Restorative charting supplements: chart-settings (REST-3), tooth-note upsert
# (REST-4), bulk conditions, aggregate /patients/{id}/chart. Before generic CRUD so
# literal sub-paths (/chart-conditions/bulk, /chart-tooth-notes/upsert) win.
api_router.include_router(restorative.router)
# Direct Messaging: REST (/messaging/conversations, /messaging/presence, …) plus
# the WebSocket gateway (/messaging/ws). Both are hand-written — messaging is not
# a generic CRUD entity, so it is not in the registry.
api_router.include_router(messaging.router)
api_router.include_router(messaging_ws.router)
# Imaging (DICOM archive): per-patient viewer tree + token-authorised binary
# serving. Before generic CRUD so /patients/{id}/imaging and the literal
# /dicom-instances/* paths win over the generic /{item_id} routes.
api_router.include_router(imaging.router)
api_router.include_router(imaging.instances_router)
api_router.include_router(imaging.assets_router)
# AppointNow (external online booking): anonymous public surface (office info /
# availability / request intake) + authenticated staff inbox (list / approve /
# decline). Hand-written — public routes resolve the tenant from office_code and
# must never 401 (AN-12), and approval is a bespoke atomic booking.
api_router.include_router(appointnow.public_router)
api_router.include_router(appointnow.staff_router)
api_router.include_router(build_entity_router())
