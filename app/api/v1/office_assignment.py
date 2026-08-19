"""Office Assignment routes (Setup -> Offices -> Office Assignment).

Resolves gaps #24, #25, #26, #28, #29, #30, #31 (catalog->office M:N assignment) and
#27 (office users bulk-set / copy-from / denormalized read). Every route verifies the
office belongs to the authenticated tenant.

NOTE: no ``from __future__ import annotations`` — the dynamic ``body: <Schema>``
parameter annotations must resolve to real classes for FastAPI.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import CurrentUser, DbSession, TenantId, get_current_user
from app.db.models import (
    CodeBundle,
    LetterTemplate,
    NoteMacro,
    OfficeCodeBundle,
    OfficeLetterTemplate,
    OfficeNoteMacro,
    OfficePrescriptionLibrary,
    OfficeProcedureCode,
    OfficeProductionType,
    PrescriptionLibrary,
    ProcedureCode,
    ProductionType,
    Provider,
    ProviderOffice,
)
from app.schemas.auth import UserRead
from app.schemas.common import ErrorResponse
from app.schemas.office_assignment import (
    AssignedCodeBundleRead,
    AssignedLetterTemplateRead,
    AssignedNoteMacroRead,
    AssignedPrescriptionRead,
    AssignedProcedureCodeRead,
    AssignedProductionTypeRead,
    AssignedProviderRead,
    IntIdAssignmentSet,
    OfficeUsersSet,
    StrIdAssignmentSet,
)
from app.services import office_assignment_service as svc
from app.services import office_setup_service, provider_directory_service

router = APIRouter(
    prefix="/offices",
    tags=["Office Assignment"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def _office_scope(office_id: Annotated[int, Path()], tenant_id: TenantId, db: DbSession) -> int:
    office_setup_service.get_office_in_tenant(db, office_id, tenant_id)
    return office_id


OfficeScope = Annotated[int, Depends(_office_scope)]


def _register(segment, link_model, fk_attr, target_model, target_pk, read_schema, body_schema, singular):
    @router.get(
        f"/{{office_id}}/{segment}",
        response_model=list[read_schema],
        operation_id=f"list_office_{singular}",
        summary=f"List an office's assigned {segment.replace('-', ' ')}",
    )
    def _list(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
        return svc.get_assigned(db, link_model, fk_attr, target_model, target_pk, office_id)

    @router.put(
        f"/{{office_id}}/{segment}",
        response_model=list[read_schema],
        operation_id=f"set_office_{singular}",
        summary=f"Replace an office's assigned {segment.replace('-', ' ')}",
    )
    def _set(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: body_schema):  # type: ignore[valid-type]
        return svc.set_assigned(db, link_model, fk_attr, target_model, target_pk, office_id, tenant_id, body.ids)


# segment, link, fk, target, target_pk, read_schema, body_schema, singular(op-id)
_RESOURCES = [
    ("procedure-codes", OfficeProcedureCode, "procedure_code", ProcedureCode, "code", AssignedProcedureCodeRead, StrIdAssignmentSet, "procedure_codes"),
    ("exp-codes", OfficeCodeBundle, "bundle_id", CodeBundle, "id", AssignedCodeBundleRead, IntIdAssignmentSet, "exp_codes"),
    ("production-types", OfficeProductionType, "production_type_id", ProductionType, "id", AssignedProductionTypeRead, IntIdAssignmentSet, "production_types"),
    ("providers", ProviderOffice, "provider_id", Provider, "id", AssignedProviderRead, StrIdAssignmentSet, "providers"),
    ("note-macros", OfficeNoteMacro, "note_macro_id", NoteMacro, "id", AssignedNoteMacroRead, IntIdAssignmentSet, "note_macros"),
    ("prescription-library", OfficePrescriptionLibrary, "prescription_library_id", PrescriptionLibrary, "id", AssignedPrescriptionRead, IntIdAssignmentSet, "prescription_library"),
    ("letter-templates", OfficeLetterTemplate, "letter_template_id", LetterTemplate, "id", AssignedLetterTemplateRead, IntIdAssignmentSet, "letter_templates"),
]

for _cfg in _RESOURCES:
    _register(*_cfg)


# ── PROV-1: the *effective* provider set for an office ───────────────────────
# ``GET /{office_id}/providers`` above is the assignment grid — it returns exactly
# what its PUT replaces, so it stays untouched. Every screen that only wants "who
# can I pick for this office" needs the union with the legacy ``providers.office_id``
# home scalar, because the assignment table is not backfilled everywhere yet
# (``scripts/backfill_provider_offices.py`` closes that on real data).
@router.get(
    "/{office_id}/providers/effective",
    response_model=list[AssignedProviderRead],
    operation_id="list_office_effective_providers",
    summary="Providers serving an office: assigned ∪ home office (PROV-1)",
)
def list_office_effective_providers(
    db: DbSession,
    office_id: OfficeScope,
    tenant_id: TenantId,
    include_inactive: Annotated[bool, Query()] = False,
):
    return provider_directory_service.effective_office_providers(
        db, office_id, tenant_id, include_inactive=include_inactive
    )


# ── Users (#27) — denormalized read, bulk set, copy-from ─────────────────────
@router.get("/{office_id}/users", response_model=list[UserRead], operation_id="list_office_users")
def list_office_users(db: DbSession, office_id: OfficeScope, tenant_id: TenantId):
    return svc.get_office_users(db, office_id)


@router.put("/{office_id}/users", response_model=list[UserRead], operation_id="set_office_users")
def set_office_users(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, body: OfficeUsersSet):
    return svc.set_office_users(db, office_id, body.user_ids)


@router.post("/{office_id}/users/copy-from/{source_office_id}", response_model=list[UserRead], operation_id="copy_office_users_from")
def copy_office_users_from(db: DbSession, office_id: OfficeScope, tenant_id: TenantId, source_office_id: int):
    office_setup_service.get_office_in_tenant(db, source_office_id, tenant_id)  # validate source too
    return svc.copy_users_from(db, office_id, source_office_id)
