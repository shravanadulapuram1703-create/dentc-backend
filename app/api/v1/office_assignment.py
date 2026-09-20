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
from app.services import office_scope_service, office_setup_service, provider_directory_service

router = APIRouter(
    prefix="/offices",
    tags=["Office Assignment"],
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def _office_scope(
    office_id: Annotated[int, Path()], tenant_id: TenantId, db: DbSession, current: CurrentUser
) -> int:
    office_setup_service.get_office_in_tenant(db, office_id, tenant_id)
    # OFF-SCOPE-1: an office-owned setup screen may only be opened for an office
    # the caller is assigned to (privileged callers excepted).
    office_scope_service.assert_office_path_access(db, current, tenant_id, office_id)
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


# ── OFF-SCOPE-9: /effective for the five remaining catalogs ───────────────────
# ``providers`` and ``letter-templates`` already have an /effective view above.
# These pin the same "unassigned = all" semantic (office_assignment_service.get_effective)
# so a picker scoped to an office (Setup, or a patient's home office when
# AccountSettings.only_show_office_items is on) has a usable list. The FE decides
# *which* office id to pass — its home-office for only_show_office_items.
def _register_effective(segment, link_model, fk_attr, target_model, target_pk, read_schema, singular):
    @router.get(
        f"/{{office_id}}/{segment}/effective",
        response_model=list[read_schema],
        operation_id=f"list_office_effective_{singular}",
        summary=f"{segment.replace('-', ' ').title()} this office can pick: its assignment, else the full catalog (OFF-SCOPE-9)",
    )
    def _effective(  # noqa: ANN202
        db: DbSession,
        office_id: OfficeScope,
        tenant_id: TenantId,
        include_inactive: Annotated[bool, Query()] = False,
    ):
        return svc.get_effective(
            db, link_model, fk_attr, target_model, target_pk, office_id, tenant_id,
            include_inactive=include_inactive,
        )


_EFFECTIVE_RESOURCES = [
    ("procedure-codes", OfficeProcedureCode, "procedure_code", ProcedureCode, "code", AssignedProcedureCodeRead, "procedure_codes"),
    ("exp-codes", OfficeCodeBundle, "bundle_id", CodeBundle, "id", AssignedCodeBundleRead, "exp_codes"),
    ("production-types", OfficeProductionType, "production_type_id", ProductionType, "id", AssignedProductionTypeRead, "production_types"),
    ("note-macros", OfficeNoteMacro, "note_macro_id", NoteMacro, "id", AssignedNoteMacroRead, "note_macros"),
    ("prescription-library", OfficePrescriptionLibrary, "prescription_library_id", PrescriptionLibrary, "id", AssignedPrescriptionRead, "prescription_library"),
]

for _cfg in _EFFECTIVE_RESOURCES:
    _register_effective(*_cfg)


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


# ── LTR-7: the *effective* letter catalog for an office ──────────────────────
# ``GET /{office_id}/letter-templates`` is the assignment grid and returns [] for
# every office (the legacy join was never migrated). The Letters dialog needs a
# printable list, so this endpoint pins the semantic: unassigned = the whole
# tenant catalog; assigned = exactly the assigned set.
@router.get(
    "/{office_id}/letter-templates/effective",
    response_model=list[AssignedLetterTemplateRead],
    operation_id="list_office_effective_letter_templates",
    summary="Letters this office can print: its assignment, or the full catalog when unassigned (LTR-7)",
)
def list_office_effective_letter_templates(
    db: DbSession,
    office_id: OfficeScope,
    tenant_id: TenantId,
    include_inactive: Annotated[bool, Query()] = False,
):
    return svc.get_effective_letter_templates(
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
