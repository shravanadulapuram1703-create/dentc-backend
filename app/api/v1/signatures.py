"""Signature-capture supplements (SIG-4/8 + the published rules).

Mounted before the generic ``/patient-signatures`` and ``/patient-consents``
CRUD routers so the literal sub-paths win over ``/{item_id}``.

* ``GET /patient-signatures/{id}/sig-string`` and
  ``GET /patient-consents/{id}/sig-string`` — the **only** way a SigString leaves
  the server (SIG-4). Admin-only, and every read is an ``sig_string_exported``
  audit event: the SigString is the biometric record, so reading it is itself
  an auditable act.
* ``GET /signature-audit-events`` — the SIG-8 trail, filterable by entity /
  patient / event / actor.
* ``GET /metadata/signature-capture`` — vocabularies + limits the API enforces.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.deps import (
    CurrentUser,
    DbSession,
    PageParams,
    TenantId,
    get_current_user,
    require_roles,
)
from app.core.exceptions import NotFoundError
from app.crud.base import CRUDBase
from app.db.models import PatientConsent, SignatureAuditEvent
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.schemas.signature import (
    ClaimSignaturesRead,
    ProviderSignatureRead,
    ProviderSignatureUpdate,
    SignatureAuditEventRead,
    SignatureCaptureRules,
    SignatureVectorRead,
)
from app.services import signature_service as svc

_errs = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}
_admin = Depends(require_roles("admin"))

signature_router = APIRouter(
    prefix="/patient-signatures", tags=["Patients"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)
consent_router = APIRouter(
    prefix="/patient-consents", tags=["Patients"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)
audit_router = APIRouter(
    prefix="/signature-audit-events", tags=["Audit"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)
metadata_router = APIRouter(
    tags=["Patients"], dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErrorResponse}},
)
# SIG-14: the provider-level signature store.
provider_router = APIRouter(
    prefix="/providers", tags=["Organization"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)
# SIG-16 pre-flight: what prints on a claim's three signature lines.
claims_router = APIRouter(
    prefix="/insurance-claims", tags=["Billing"],
    dependencies=[Depends(get_current_user)], responses=_errs,
)

_signature_crud = svc.PatientSignatureCRUD(svc.PatientSignature, soft_delete_field="is_active")
_audit_crud = CRUDBase(
    SignatureAuditEvent,
    sortable_fields=("occurred_at", "created_at", "id"),
    default_sort="occurred_at",
    soft_delete_field=None,
)


@signature_router.get(
    "/{signature_id}/sig-string",
    response_model=SignatureVectorRead,
    operation_id="get_patient_signature_sig_string",
    summary="The clear Topaz SigString for one signature (admin, audited — SIG-4)",
    dependencies=[_admin],
)
def get_signature_sig_string(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    signature_id: Annotated[int, Path(description="signature identifier")],
):
    row = _signature_crud.get(db, signature_id, tenant_id=tenant_id)
    out = svc.signature_vector(row, entity_type=svc.ENTITY_PATIENT_SIGNATURE)
    svc.record_event(
        db, tenant_id=tenant_id, entity_type=svc.ENTITY_PATIENT_SIGNATURE, entity_id=row.id,
        event=svc.EVENT_EXPORTED, actor_id=current.id, patient_id=row.patient_id, source=row,
        signature_type=row.signature_type, content_hash=row.content_hash,
    )
    db.commit()
    return out


@consent_router.get(
    "/{consent_id}/sig-string",
    response_model=SignatureVectorRead,
    operation_id="get_patient_consent_sig_string",
    summary="The clear Topaz SigString captured on a consent (admin, audited — SIG-4)",
    dependencies=[_admin],
)
def get_consent_sig_string(
    db: DbSession, tenant_id: TenantId, current: CurrentUser,
    consent_id: Annotated[int, Path(description="consent identifier")],
):
    row = db.get(PatientConsent, consent_id)
    if row is None or row.tenant_id != tenant_id or row.is_deleted:
        raise NotFoundError(f"Consent '{consent_id}' was not found")
    out = svc.signature_vector(row, entity_type=svc.ENTITY_PATIENT_CONSENT)
    svc.record_event(
        db, tenant_id=tenant_id, entity_type=svc.ENTITY_PATIENT_CONSENT, entity_id=row.id,
        event=svc.EVENT_EXPORTED, actor_id=current.id, patient_id=row.patient_id, source=row,
        signature_type="consent", content_hash=row.content_hash,
    )
    db.commit()
    return out


@audit_router.get(
    "",
    response_model=PaginatedResponse[SignatureAuditEventRead],
    operation_id="list_signature_audit_events",
    summary="Signature lifecycle audit trail — who signed on which pad from which workstation (SIG-8)",
)
def list_signature_audit_events(
    db: DbSession,
    tenant_id: TenantId,
    page: PageParams,
    entity_type: Annotated[str | None, Query(description="patient_signature | patient_consent | user")] = None,
    entity_id: Annotated[int | None, Query()] = None,
    patient_id: Annotated[int | None, Query()] = None,
    event: Annotated[str | None, Query(description="captured | superseded | voided | declined | replaced | cleared | sig_string_exported")] = None,
    actor_id: Annotated[int | None, Query()] = None,
):
    items, total = _audit_crud.list(
        db, tenant_id=tenant_id, page=page.page, size=page.size, sort=page.sort, order=page.order,
        filters={"entity_type": entity_type, "entity_id": entity_id, "patient_id": patient_id,
                 "event": event, "actor_id": actor_id},
    )
    return PaginatedResponse.build(items, total, page.page, page.size)


@metadata_router.get(
    "/metadata/signature-capture",
    response_model=SignatureCaptureRules,
    operation_id="get_signature_capture_rules",
    summary="Signature-capture vocabularies and limits the API enforces (SIG-2/5)",
)
def signature_capture_rules():
    return svc.published_rules()


# ── SIG-14: provider signature store ─────────────────────────────────────────
_ProviderPath = Annotated[str, Path(description="provider identifier")]


def _provider_signature_read(row, *, provider_id: str, source: str | None,  # noqa: ANN001
                             include_sig_string: bool) -> ProviderSignatureRead:
    if row is None:
        return ProviderSignatureRead(provider_id=provider_id, source=None)
    from app.db.models import User

    out = svc.signature_store_out(row, include_sig_string=include_sig_string)
    return ProviderSignatureRead(
        provider_id=provider_id, source=source,
        user_id=row.id if isinstance(row, User) else None, **out,
    )


@provider_router.get(
    "/{provider_id}/signature",
    response_model=ProviderSignatureRead,
    operation_id="get_provider_signature",
    summary="A provider's signature on file — the provider store, else the linked user's (SIG-14)",
)
def get_provider_signature(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, provider_id: _ProviderPath,
    resolve: Annotated[bool, Query(description="Fall back to the provider's linked user account")] = True,
    include_sig_string: Annotated[bool, Query(description="SIG-4: also return the clear SigString (admin, audited)")] = False,
):
    provider = svc._require_provider(db, tenant_id, provider_id)
    if resolve:
        row, source = svc.resolve_provider_signature(db, tenant_id, provider)
    else:
        row = svc.get_provider_signature(db, tenant_id, provider_id)
        source = "provider" if row is not None and (row.signature_data or row.sig_string) else None
        row = row if source else None
    if row is None:
        raise NotFoundError("No signature on file for this provider")
    if include_sig_string:
        if current.role not in ("admin", "super_admin"):
            from app.core.exceptions import ForbiddenError

            raise ForbiddenError("Reading a SigString requires an admin role")
        svc.record_event(
            db, tenant_id=tenant_id, entity_type=svc.ENTITY_PROVIDER if source == "provider" else svc.ENTITY_USER,
            entity_id=row.id, event=svc.EVENT_EXPORTED, actor_id=current.id, source=row,
            signature_type="provider" if source == "provider" else "user", reason=f"provider {provider_id}",
        )
        db.commit()
    return _provider_signature_read(row, provider_id=provider_id, source=source,
                                    include_sig_string=include_sig_string)


@provider_router.put(
    "/{provider_id}/signature",
    response_model=ProviderSignatureRead,
    operation_id="set_provider_signature",
    summary="Save a provider's signature (Topaz block accepted; replaces the whole block)",
)
def set_provider_signature(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, provider_id: _ProviderPath,
    body: ProviderSignatureUpdate,
):
    row = svc.set_provider_signature(db, tenant_id, provider_id, body.model_dump(exclude_unset=True),
                                     actor_id=current.id)
    return _provider_signature_read(row, provider_id=provider_id, source="provider",
                                    include_sig_string=False)


@provider_router.delete(
    "/{provider_id}/signature",
    status_code=204,
    operation_id="clear_provider_signature",
    summary="Clear a provider's stored signature (audited as `cleared`)",
)
def clear_provider_signature(
    db: DbSession, tenant_id: TenantId, current: CurrentUser, provider_id: _ProviderPath,
):
    if not svc.clear_provider_signature(db, tenant_id, provider_id, actor_id=current.id):
        raise NotFoundError("No signature on file for this provider")
    return None


# ── SIG-16: claim signature pre-flight ───────────────────────────────────────
@claims_router.get(
    "/{claim_id}/signatures",
    response_model=ClaimSignaturesRead,
    operation_id="get_claim_signatures",
    summary="What prints on ADA Items 36 / 37 / 53 for this claim — pinned, on-file, or provider (SIG-16)",
)
def get_claim_signatures(
    db: DbSession, tenant_id: TenantId,
    claim_id: Annotated[str, Path(description="claim identifier")],
    include_image: Annotated[bool, Query(description="Embed the signature image data URLs")] = False,
):
    from app.services import claim_form_service

    claim, patient = claim_form_service._get_claim(db, claim_id, tenant_id)
    treating_id = claim.treating_provider_id
    if not treating_id:
        from sqlalchemy import select

        from app.db.models import PatientProcedure

        procs = db.execute(
            select(PatientProcedure).where(PatientProcedure.claim_id == claim.id)
        ).scalars().all()
        treating_id = claim_form_service.pick_treating_provider(db, procs) or patient.preferred_provider_id
    slots = svc.resolve_claim_signatures(db, tenant_id, claim, treating_provider_id=treating_id,
                                         include_images=include_image)
    return {"claim_id": claim.id, "patient_id": patient.id, "treating_provider_id": treating_id, **slots}
