"""Patient Medical History — the composite document, its versions and its
signature (MH-2/3/4/6/7/8/13/14/15/16).

Before this module the screen had no backend of its own: it drove the three
generic answer resources directly, one HTTP request per row. Opening it cost at
minimum nine calls plus one ``GET /definitions`` per catalog group, and saving
legacy's **NO TO ALL ALERTS** against the ~90-item catalog meant up to ninety
sequential ``POST``s through a six-connection browser pool — each its own
transaction, so closing the tab mid-save left a half-written medical history.

Everything here is built on three ideas:

* **One document.** :func:`get_document` composes alerts + both questionnaires +
  emergency contacts + signatures + the resolved catalogs; :func:`save_document`
  reconciles the whole thing in one transaction.
* **A version is what a signature signs.** :func:`sign` freezes the answers into
  ``medical_history_records`` + ``medical_history_details`` and stamps the same
  ``content_hash`` on both the version and the signature, so
  ``signature_status`` can say *stale* the moment an answer moves underneath it
  (MH-6). That status is the whole point: a signature that silently stops
  matching the record it attests to is worse than no signature.
* **Every answer change is attributable.** ``patient_medical_history_events`` is
  written on every path (MH-8), including the copy, which names the source
  chart.
"""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.crud.base import CRUDBase
from app.db.models import (
    Definition,
    DefinitionGroup,
    MedicalHistoryDetail,
    MedicalHistoryRecord,
    Patient,
    PatientAlert,
    PatientEmergencyContact,
    PatientMedicalAlert,
    PatientMedicalHistory,
    PatientMedicalHistoryEvent,
    PatientQuestionnaireResponse,
    PatientSignature,
)
from app.services import medical_history_rules as rules
from app.services.medical_history_catalog import (
    ALERT_GROUP_TYPE,
    CATALOGS,
    DEFAULT_GROUP_CODES,
    QUESTIONNAIRE_GROUP_TYPES,
    input_type_for,
)

#: Mirrors the frontend's ``MIN_TENANT_CATALOG_ITEMS`` guard. A tenant catalog
#: smaller than this is a stray test group (the three ``*_TEST`` groups that
#: shipped with the migration), not a real catalog: serving it would replace ~90
#: real alerts with one row. Below the bar we serve the built-in catalog and say
#: so in ``catalog_source``, so the client never has to carry its own copy.
MIN_TENANT_CATALOG_ITEMS = 10

SIGNATURE_TYPE_MEDICAL_HISTORY = "medical_history"

SCOPES: tuple[str, ...] = ("all", "alerts", "dental", "medical")

#: The reserved alert code the Add-Patient wizard and this screen were using to
#: smuggle the Additional Comments box into the alert list (MH-13). It now has a
#: real home on ``patient_medical_history.comments``; a legacy row carrying it is
#: read (so nothing is lost) and folded into the document's ``comments``, and it
#: is never written again.
LEGACY_COMMENTS_CODE = "ADDITIONAL_COMMENTS"


# ── helpers ──────────────────────────────────────────────────────────────────
def _patient(db: Session, tenant_id: int, patient_id: int) -> Patient:
    row = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return row


def _now() -> datetime:
    return datetime.utcnow()


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def header(db: Session, tenant_id: int, patient_id: int, *, create: bool = False
           ) -> PatientMedicalHistory | None:
    row = db.execute(
        select(PatientMedicalHistory).where(
            PatientMedicalHistory.patient_id == patient_id,
            PatientMedicalHistory.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if row is None and create:
        row = PatientMedicalHistory(tenant_id=tenant_id, patient_id=patient_id)
        db.add(row)
        db.flush()
    return row


def _event(
    db: Session,
    *,
    tenant_id: int,
    patient_id: int,
    entity_type: str,
    action: str,
    entity_id: int | None = None,
    code: str | None = None,
    label: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    source_patient_id: int | None = None,
    user_id: int | None = None,
) -> None:
    db.add(
        PatientMedicalHistoryEvent(
            tenant_id=tenant_id,
            patient_id=patient_id,
            entity_type=entity_type,
            entity_id=entity_id,
            code=code,
            label=label,
            action=action,
            old_value=old_value,
            new_value=new_value,
            source_patient_id=source_patient_id,
            changed_by=user_id,
        )
    )


# ── MH-1/MH-2: catalog resolution ────────────────────────────────────────────
def _tenant_definitions(db: Session, tenant_id: int, group_type: str) -> list[Definition]:
    group_codes = [
        g.group_code
        for g in db.execute(
            select(DefinitionGroup).where(
                DefinitionGroup.tenant_id == tenant_id,
                DefinitionGroup.group_type == group_type,
            )
        ).scalars()
    ]
    if not group_codes:
        return []
    rows = list(
        db.execute(
            select(Definition).where(
                Definition.tenant_id == tenant_id,
                Definition.group_code.in_(group_codes),
                Definition.is_active.is_(True),
            )
        ).scalars()
    )
    rows.sort(key=lambda d: (d.sort_order if d.sort_order is not None else 10_000, d.id))
    return rows


def _catalog_for(db: Session, tenant_id: int, group_type: str) -> tuple[list[dict[str, Any]], str]:
    """Return ``(items, source)`` where source is ``tenant`` or ``builtin``."""
    rows = _tenant_definitions(db, tenant_id, group_type)
    if len(rows) >= MIN_TENANT_CATALOG_ITEMS:
        return (
            [
                {
                    "code": d.key1,
                    "label": d.description,
                    "section": d.section,
                    "input_kind": d.key2,
                    "input_type": d.input_type or input_type_for(d.key2),
                    "sort_order": d.sort_order,
                    "is_flash_alert": bool(d.is_flash_alert),
                    "blocks_charges": bool(d.blocks_charges),
                    "definition_id": d.id,
                    "group_code": d.group_code,
                }
                for d in rows
            ],
            "tenant",
        )
    return (
        [
            {
                "code": item["code"],
                "label": item["label"],
                "section": item["section"],
                "input_kind": item["input_kind"],
                "input_type": input_type_for(item["input_kind"]),
                "sort_order": index,
                "is_flash_alert": False,
                "blocks_charges": False,
                "definition_id": None,
                "group_code": DEFAULT_GROUP_CODES[group_type],
            }
            for index, item in enumerate(CATALOGS[group_type])
        ],
        "builtin",
    )


def resolve_catalogs(db: Session, tenant_id: int) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    catalogs: dict[str, list[dict[str, Any]]] = {}
    sources: dict[str, str] = {}
    for key, group_type in (
        ("alerts", ALERT_GROUP_TYPE),
        ("dental", QUESTIONNAIRE_GROUP_TYPES["dental"]),
        ("medical", QUESTIONNAIRE_GROUP_TYPES["medical"]),
    ):
        items, source = _catalog_for(db, tenant_id, group_type)
        catalogs[key] = items
        sources[key] = source
    return catalogs, sources


def _alert_flags(db: Session, tenant_id: int) -> dict[str, dict[str, Any]]:
    """MH-14: ``alert_code`` -> the Setup catalog's flags for that item."""
    catalog, _ = _catalog_for(db, tenant_id, ALERT_GROUP_TYPE)
    return {
        item["code"]: {
            "is_flash_alert": item["is_flash_alert"],
            "blocks_charges": item["blocks_charges"],
            "label": item["label"],
            "section": item["section"],
        }
        for item in catalog
    }


# ── reads ────────────────────────────────────────────────────────────────────
def _alerts(db: Session, tenant_id: int, patient_id: int) -> list[PatientMedicalAlert]:
    rows = list(
        db.execute(
            select(PatientMedicalAlert).where(
                PatientMedicalAlert.tenant_id == tenant_id,
                PatientMedicalAlert.patient_id == patient_id,
                PatientMedicalAlert.is_active.is_(True),
            )
        ).scalars()
    )
    rows.sort(key=lambda r: r.id)
    return rows


def _responses(
    db: Session, tenant_id: int, patient_id: int, questionnaire_type: str
) -> list[PatientQuestionnaireResponse]:
    rows = list(
        db.execute(
            select(PatientQuestionnaireResponse).where(
                PatientQuestionnaireResponse.tenant_id == tenant_id,
                PatientQuestionnaireResponse.patient_id == patient_id,
                PatientQuestionnaireResponse.questionnaire_type == questionnaire_type,
                PatientQuestionnaireResponse.is_active.is_(True),
            )
        ).scalars()
    )
    rows.sort(key=lambda r: r.id)
    return rows


def _signatures(db: Session, patient_id: int, *, active_only: bool = False) -> list[PatientSignature]:
    stmt = select(PatientSignature).where(PatientSignature.patient_id == patient_id)
    if active_only:
        stmt = stmt.where(PatientSignature.is_active.is_(True))
    rows = list(db.execute(stmt).scalars())
    rows.sort(key=lambda r: r.id, reverse=True)
    return rows


def compute_content_hash(
    alerts: Iterable[PatientMedicalAlert],
    dental: Iterable[PatientQuestionnaireResponse],
    medical: Iterable[PatientQuestionnaireResponse],
    comments: str | None,
) -> str:
    """SHA-256 over the canonicalised answers.

    Sorted by code and built from the *values* only, so an unrelated re-save that
    changes no answer does not invalidate a standing signature — the point is to
    detect a changed medical history, not a changed row id.
    """
    payload = {
        "alerts": sorted(
            [a.alert_code, (a.response or ""), (a.comments or "")] for a in alerts
        ),
        "dental": sorted([q.question_code, (q.answer or "")] for q in dental),
        "medical": sorted([q.question_code, (q.answer or "")] for q in medical),
        "comments": comments or "",
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _actor_names(db: Session, ids: set[int]) -> dict[int, str]:
    from app.services.user_admin_service import resolve_user_names

    return resolve_user_names(db, {i for i in ids if i is not None})


def _alert_out(row: PatientMedicalAlert, flags: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    meta = flags.get(row.alert_code, {})
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "alert_code": row.alert_code,
        "alert_label": row.alert_label or meta.get("label"),
        "section": meta.get("section"),
        "response": row.response,
        "comments": row.comments,
        "answered_at": row.answered_at,
        "is_active": row.is_active,
        # MH-14: the Setup catalog's flags, denormalised so a scheduler popover or
        # a charge gate can act on the patient's answer without re-reading
        # /definitions per row.
        "is_flash_alert": bool(meta.get("is_flash_alert")),
        "blocks_charges": bool(meta.get("blocks_charges")),
        "created_by": row.created_by,
        "created_by_name": names.get(row.created_by) if row.created_by else None,
        "updated_by": row.updated_by,
        "updated_by_name": names.get(row.updated_by) if row.updated_by else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _response_out(row: PatientQuestionnaireResponse, names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "questionnaire_type": row.questionnaire_type,
        "question_code": row.question_code,
        "question_text": row.question_text,
        "answer": row.answer,
        "answered_at": row.answered_at,
        "is_active": row.is_active,
        "created_by": row.created_by,
        "created_by_name": names.get(row.created_by) if row.created_by else None,
        "updated_by": row.updated_by,
        "updated_by_name": names.get(row.updated_by) if row.updated_by else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _signature_out(row: PatientSignature, names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "signature_type": row.signature_type,
        "signature_data": row.signature_data,
        "signature_len": row.signature_len,
        "device_source": row.device_source,
        "is_user_sig": row.is_user_sig,
        "signed_at": row.signed_at or row.created_at,
        "signed_by_user_id": row.signed_by_user_id,
        "signed_by_name": names.get(row.signed_by_user_id) if row.signed_by_user_id else None,
        "content_hash": row.content_hash,
        "is_active": row.is_active,
        "superseded_by_id": row.superseded_by_id,
        "voided_at": row.voided_at,
        "voided_by": row.voided_by,
        "created_by": row.created_by,
        "created_by_name": names.get(row.created_by) if row.created_by else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _version_out(row: MedicalHistoryRecord, names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "patient_id": row.patient_id,
        "scope": row.scope,
        "content_hash": row.content_hash,
        "item_count": row.item_count,
        "comments": row.comments,
        "signature_id": row.signature_id,
        "completed_at": row.completed_at,
        "completed_by": row.completed_by,
        "completed_by_name": names.get(row.completed_by) if row.completed_by else None,
        "source_patient_id": row.source_patient_id,
        "copied_at": row.copied_at,
        "is_archived": row.is_archived,
        "created_at": row.created_at,
    }


def _versions(db: Session, tenant_id: int, patient_id: int, limit: int | None = 20
              ) -> list[MedicalHistoryRecord]:
    stmt = select(MedicalHistoryRecord).where(MedicalHistoryRecord.patient_id == patient_id)
    rows = [
        r
        for r in db.execute(stmt).scalars()
        if r.tenant_id is None or r.tenant_id == tenant_id
    ]
    rows.sort(key=lambda r: r.id, reverse=True)
    return rows[:limit] if limit else rows


def get_document(db: Session, tenant_id: int, patient_id: int) -> dict[str, Any]:
    """MH-2: the whole screen in one call."""
    patient = _patient(db, tenant_id, patient_id)
    head = header(db, tenant_id, patient_id)
    alerts = _alerts(db, tenant_id, patient_id)
    dental = _responses(db, tenant_id, patient_id, "dental")
    medical = _responses(db, tenant_id, patient_id, "medical")
    catalogs, catalog_sources = resolve_catalogs(db, tenant_id)
    flags = {item["code"]: item for item in catalogs["alerts"]}

    # MH-13: a legacy comments row keeps working - it is read out of the alert
    # list and surfaced as the document's comments when the header has none.
    legacy_comment = next((a for a in alerts if a.alert_code == LEGACY_COMMENTS_CODE), None)
    comments = (head.comments if head else None) or (legacy_comment.comments if legacy_comment else None)
    visible_alerts = [a for a in alerts if a.alert_code != LEGACY_COMMENTS_CODE]

    contacts = list(
        db.execute(
            select(PatientEmergencyContact).where(
                PatientEmergencyContact.tenant_id == tenant_id,
                PatientEmergencyContact.patient_id == patient_id,
                PatientEmergencyContact.is_active.is_(True),
            )
        ).scalars()
    )
    signatures = _signatures(db, patient_id)
    versions = _versions(db, tenant_id, patient_id)

    actor_ids: set[int] = set()
    for row in (*visible_alerts, *dental, *medical):
        actor_ids.update({row.created_by, row.updated_by})
    for sig in signatures:
        actor_ids.update({sig.created_by, sig.signed_by_user_id})
    for ver in versions:
        actor_ids.add(ver.completed_by)
    if head:
        actor_ids.update(
            {head.alerts_completed_by, head.dental_completed_by, head.medical_completed_by,
             head.copied_by}
        )
    names = _actor_names(db, {i for i in actor_ids if i})

    current_hash = compute_content_hash(visible_alerts, dental, medical, comments)
    standing = next(
        (
            s
            for s in signatures
            if s.is_active
            and (s.signature_type or SIGNATURE_TYPE_MEDICAL_HISTORY) == SIGNATURE_TYPE_MEDICAL_HISTORY
        ),
        None,
    )
    if standing is None:
        signature_status = "unsigned"
    elif standing.content_hash and standing.content_hash == current_hash:
        signature_status = "signed"
    else:
        # Either the answers moved under the signature, or the signature is a
        # migrated row that predates content hashing. Both mean "do not treat
        # this as attesting to what is on screen" - MH-6.
        signature_status = "stale" if standing.content_hash else "unverifiable"

    return {
        "patient_id": patient_id,
        "patient": {
            "id": patient.id,
            "chart_no": patient.chart_no,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "dob": patient.dob,
            "gender": patient.gender,
            "home_office_id": patient.home_office_id,
        },
        "comments": comments,
        "alerts": [_alert_out(a, flags, names) for a in visible_alerts],
        "dental_responses": [_response_out(q, names) for q in dental],
        "medical_responses": [_response_out(q, names) for q in medical],
        "emergency_contacts": [
            {
                "id": c.id,
                "patient_id": c.patient_id,
                "name": c.name,
                "relationship": c.relationship,
                "phone": c.phone,
                "email": c.email,
                "is_primary": c.is_primary,
                "is_active": c.is_active,
            }
            for c in contacts
        ],
        "signatures": [_signature_out(s, names) for s in signatures],
        "current_signature": _signature_out(standing, names) if standing else None,
        "signature_status": signature_status,
        "content_hash": current_hash,
        "versions": [_version_out(v, names) for v in versions],
        "catalogs": catalogs,
        "catalog_sources": catalog_sources,
        "completion": {
            "alerts": {
                "last_completed_at": head.alerts_completed_at if head else None,
                "last_completed_by": head.alerts_completed_by if head else None,
                "last_completed_by_name": names.get(head.alerts_completed_by) if head and head.alerts_completed_by else None,
            },
            "dental": {
                "last_completed_at": head.dental_completed_at if head else None,
                "last_completed_by": head.dental_completed_by if head else None,
                "last_completed_by_name": names.get(head.dental_completed_by) if head and head.dental_completed_by else None,
            },
            "medical": {
                "last_completed_at": head.medical_completed_at if head else None,
                "last_completed_by": head.medical_completed_by if head else None,
                "last_completed_by_name": names.get(head.medical_completed_by) if head and head.medical_completed_by else None,
            },
        },
        "copied_from_patient_id": head.copied_from_patient_id if head else None,
        "copied_at": head.copied_at if head else None,
        "copied_by_name": names.get(head.copied_by) if head and head.copied_by else None,
    }


# ── MH-14: propagate a Yes answer into the banner-alert table ────────────────
def sync_flash_alerts(db: Session, tenant_id: int, patient_id: int, *, user_id: int | None = None) -> int:
    """Keep ``patient_alerts`` in step with the patient's answered medical alerts.

    Only rows this function created are ever touched (``source_medical_alert_id``
    is the link) - a hand-typed banner alert is never deactivated by a
    questionnaire edit. Returns the number of banner rows written.
    """
    flags = _alert_flags(db, tenant_id)
    answered = {
        a.id: a
        for a in _alerts(db, tenant_id, patient_id)
        if (a.response or "").lower() == "yes"
        and (flags.get(a.alert_code, {}).get("is_flash_alert") or flags.get(a.alert_code, {}).get("blocks_charges"))
    }
    existing = {
        row.source_medical_alert_id: row
        for row in db.execute(
            select(PatientAlert).where(
                PatientAlert.patient_id == patient_id,
                PatientAlert.source_medical_alert_id.isnot(None),
            )
        ).scalars()
    }
    written = 0
    for alert_id, alert in answered.items():
        meta = flags.get(alert.alert_code, {})
        label = alert.alert_label or meta.get("label") or alert.alert_code
        row = existing.get(alert_id)
        if row is None:
            db.add(
                PatientAlert(
                    patient_id=patient_id,
                    alert=label,
                    is_flash_alert=bool(meta.get("is_flash_alert")),
                    blocks_charges=bool(meta.get("blocks_charges")),
                    source_medical_alert_id=alert_id,
                    is_active=True,
                    created_by=user_id,
                )
            )
            written += 1
        else:
            row.alert = label
            row.is_flash_alert = bool(meta.get("is_flash_alert"))
            row.blocks_charges = bool(meta.get("blocks_charges"))
            row.is_active = True
            written += 1
    for alert_id, row in existing.items():
        if alert_id not in answered and row.is_active:
            row.is_active = False
    db.flush()
    return written


# ── MH-3: the composite write ────────────────────────────────────────────────
def _apply_alerts(
    db: Session,
    *,
    tenant_id: int,
    patient_id: int,
    items: list[dict[str, Any]],
    stored: dict[str, PatientMedicalAlert],
    user_id: int | None,
    now: datetime,
) -> set[str]:
    changed: set[str] = set()
    for item in items:
        code = _clean(item.get("alert_code"))
        if not code:
            continue
        response = _clean(item.get("response"))
        comments = _clean(item.get("comments"))
        row = stored.get(code)
        if response is None and comments is None:
            # Reset to Not Answered - the row is removed, which is what makes
            # "absent" and "unknown" different facts (MH-5).
            if row is not None:
                _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type="alert",
                       action="delete", entity_id=row.id, code=code, label=row.alert_label,
                       old_value=row.response, new_value=None, user_id=user_id)
                db.delete(row)
                stored.pop(code, None)
                changed.add(code)
            continue
        if row is None:
            row = PatientMedicalAlert(
                tenant_id=tenant_id,
                patient_id=patient_id,
                alert_code=code,
                alert_label=_clean(item.get("alert_label")),
                response=response,
                comments=comments,
                answered_at=now,
                is_active=True,
                created_by=user_id,
            )
            db.add(row)
            db.flush()
            stored[code] = row
            changed.add(code)
            _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type="alert",
                   action="create", entity_id=row.id, code=code, label=row.alert_label,
                   old_value=None, new_value=response, user_id=user_id)
            continue
        before_response, before_comments = row.response, row.comments
        label = _clean(item.get("alert_label"))
        if label:
            row.alert_label = label
        row.response = response
        row.comments = comments
        row.is_active = True
        if before_response != response or before_comments != comments:
            row.answered_at = now
            row.updated_by = user_id
            changed.add(code)
            _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type="alert",
                   action="update", entity_id=row.id, code=code, label=row.alert_label,
                   old_value=before_response, new_value=response, user_id=user_id)
    return changed


def _apply_responses(
    db: Session,
    *,
    tenant_id: int,
    patient_id: int,
    questionnaire_type: str,
    items: list[dict[str, Any]],
    stored: dict[str, PatientQuestionnaireResponse],
    user_id: int | None,
    now: datetime,
) -> set[str]:
    changed: set[str] = set()
    for item in items:
        code = _clean(item.get("question_code"))
        if not code:
            continue
        answer = _clean(item.get("answer"))
        row = stored.get(code)
        if answer is None:
            if row is not None:
                _event(db, tenant_id=tenant_id, patient_id=patient_id,
                       entity_type=questionnaire_type, action="delete", entity_id=row.id,
                       code=code, label=row.question_text, old_value=row.answer,
                       new_value=None, user_id=user_id)
                db.delete(row)
                stored.pop(code, None)
                changed.add(code)
            continue
        if row is None:
            row = PatientQuestionnaireResponse(
                tenant_id=tenant_id,
                patient_id=patient_id,
                questionnaire_type=questionnaire_type,
                question_code=code,
                question_text=_clean(item.get("question_text")),
                answer=answer,
                answered_at=now,
                is_active=True,
                created_by=user_id,
            )
            db.add(row)
            db.flush()
            stored[code] = row
            changed.add(code)
            _event(db, tenant_id=tenant_id, patient_id=patient_id,
                   entity_type=questionnaire_type, action="create", entity_id=row.id,
                   code=code, label=row.question_text, old_value=None, new_value=answer,
                   user_id=user_id)
            continue
        before = row.answer
        text = _clean(item.get("question_text"))
        if text:
            row.question_text = text
        row.answer = answer
        row.is_active = True
        if before != answer:
            row.answered_at = now
            row.updated_by = user_id
            changed.add(code)
            _event(db, tenant_id=tenant_id, patient_id=patient_id,
                   entity_type=questionnaire_type, action="update", entity_id=row.id,
                   code=code, label=row.question_text, old_value=before, new_value=answer,
                   user_id=user_id)
    return changed


def _apply_emergency_contacts(
    db: Session,
    *,
    tenant_id: int,
    patient_id: int,
    items: list[dict[str, Any]],
    user_id: int | None,
) -> None:
    """MH-11: ``patient_emergency_contacts`` is the authoritative store, so the
    questionnaire's Emergency Contact block writes *here* and the three questions
    are absent from the seeded ``MEDQUEST`` catalog. Writing both is what let the
    two drift."""
    stored = {
        row.id: row
        for row in db.execute(
            select(PatientEmergencyContact).where(
                PatientEmergencyContact.tenant_id == tenant_id,
                PatientEmergencyContact.patient_id == patient_id,
            )
        ).scalars()
    }
    for item in items:
        contact_id = item.get("id")
        name = _clean(item.get("name"))
        row = stored.get(contact_id) if contact_id else None
        if row is None and not name:
            continue
        if row is None:
            row = PatientEmergencyContact(
                tenant_id=tenant_id, patient_id=patient_id, name=name or "",
                is_active=True, created_by=user_id,
            )
            db.add(row)
        elif name:
            row.name = name
        for field in ("relationship", "phone", "email"):
            if field in item:
                setattr(row, field, _clean(item.get(field)))
        if "is_primary" in item:
            row.is_primary = bool(item.get("is_primary"))
        if item.get("is_active") is False:
            row.is_active = False
    db.flush()


def save_document(
    db: Session,
    tenant_id: int,
    patient_id: int,
    payload: dict[str, Any],
    *,
    user_id: int | None = None,
) -> dict[str, Any]:
    """MH-3: reconcile the whole document in one transaction.

    Only the codes present in the payload are touched, so a partial save is safe;
    a code sent with a null response/answer is a reset to Not Answered and its
    row is deleted. ``replace_*`` opts into a true full-section replace, where
    every stored code the payload omits is cleared.
    """
    _patient(db, tenant_id, patient_id)
    now = _now()

    stored_alerts = {a.alert_code: a for a in _alerts(db, tenant_id, patient_id)}
    stored_dental = {q.question_code: q for q in _responses(db, tenant_id, patient_id, "dental")}
    stored_medical = {q.question_code: q for q in _responses(db, tenant_id, patient_id, "medical")}

    alerts_in = list(payload.get("alerts") or [])
    dental_in = list(payload.get("dental_responses") or [])
    medical_in = list(payload.get("medical_responses") or [])

    if payload.get("replace_alerts"):
        sent = {_clean(i.get("alert_code")) for i in alerts_in}
        alerts_in += [
            {"alert_code": code, "response": None, "comments": None}
            for code in stored_alerts
            if code not in sent and code != LEGACY_COMMENTS_CODE
        ]
    if payload.get("replace_dental"):
        sent = {_clean(i.get("question_code")) for i in dental_in}
        dental_in += [{"question_code": c, "answer": None} for c in stored_dental if c not in sent]
    if payload.get("replace_medical"):
        sent = {_clean(i.get("question_code")) for i in medical_in}
        medical_in += [{"question_code": c, "answer": None} for c in stored_medical if c not in sent]

    # MH-12: judge the *merge* of payload and stored answers, before writing.
    flags = _alert_flags(db, tenant_id)
    merged: dict[str, str | None] = {code: row.response for code, row in stored_alerts.items()}
    for item in alerts_in:
        code = _clean(item.get("alert_code"))
        if code:
            merged[code] = _clean(item.get("response"))
    would_change = {
        code
        for code in (
            _clean(i.get("alert_code")) for i in alerts_in
        )
        if code and merged.get(code) != (stored_alerts[code].response if code in stored_alerts else None)
    }
    sections = {code: meta.get("section") for code, meta in flags.items()}
    contradictions = rules.check_alert_contradictions(
        merged, sections, changed_codes=would_change,
        allow=bool(payload.get("allow_contradictions")),
    )

    changed_alerts = _apply_alerts(
        db, tenant_id=tenant_id, patient_id=patient_id, items=alerts_in,
        stored=stored_alerts, user_id=user_id, now=now,
    )
    changed_dental = _apply_responses(
        db, tenant_id=tenant_id, patient_id=patient_id, questionnaire_type="dental",
        items=dental_in, stored=stored_dental, user_id=user_id, now=now,
    )
    changed_medical = _apply_responses(
        db, tenant_id=tenant_id, patient_id=patient_id, questionnaire_type="medical",
        items=medical_in, stored=stored_medical, user_id=user_id, now=now,
    )
    if payload.get("emergency_contacts") is not None:
        _apply_emergency_contacts(
            db, tenant_id=tenant_id, patient_id=patient_id,
            items=list(payload["emergency_contacts"]), user_id=user_id,
        )

    head = header(db, tenant_id, patient_id, create=True)
    if "comments" in payload:
        new_comments = _clean(payload.get("comments"))
        if (head.comments or None) != new_comments:
            _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type="comments",
                   action="update", old_value=head.comments, new_value=new_comments,
                   user_id=user_id)
            head.comments = new_comments
        # MH-13: retire the magic alert row once the real field carries the value.
        legacy = stored_alerts.pop(LEGACY_COMMENTS_CODE, None)
        if legacy is not None:
            db.delete(legacy)

    # MH-16: a completion is asserted by the caller ("the patient reviewed and
    # confirmed this"), never inferred from a row edit.
    for scope in payload.get("mark_completed") or []:
        if scope not in ("alerts", "dental", "medical"):
            raise ValidationError(
                f"Unknown completion scope '{scope}'.",
                code="invalid_completion_scope",
                details={"allowed": ["alerts", "dental", "medical"]},
            )
        setattr(head, f"{scope}_completed_at", now)
        setattr(head, f"{scope}_completed_by", user_id)
        _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type=scope,
               action="complete", new_value=now.isoformat(), user_id=user_id)

    if contradictions:
        _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type="alert",
               action="update", code="contradiction_override",
               new_value=json.dumps(contradictions, default=str), user_id=user_id)

    head.updated_by = user_id
    db.flush()
    sync_flash_alerts(db, tenant_id, patient_id, user_id=user_id)
    db.commit()

    document = get_document(db, tenant_id, patient_id)
    document["changed"] = {
        "alerts": sorted(changed_alerts),
        "dental": sorted(changed_dental),
        "medical": sorted(changed_medical),
    }
    document["contradictions"] = contradictions
    return document


# ── MH-4: server-side Copy Medical History ───────────────────────────────────
def copy_from(
    db: Session,
    tenant_id: int,
    patient_id: int,
    source_patient_id: int,
    *,
    scope: str = "all",
    user_id: int | None = None,
    allow_contradictions: bool = False,
) -> dict[str, Any]:
    """Copy a source chart's answers onto this one, atomically and attributably.

    Doing this on the client meant ~90 reads followed by ~90 writes, it was not
    atomic, and nothing recorded where the answers came from. Every copied row
    lands in the change log naming the source chart, a version row carries
    ``source_patient_id``/``copied_at``, and the header records the provenance.
    """
    if scope not in SCOPES:
        raise ValidationError(
            f"Unknown copy scope '{scope}'.", code="invalid_copy_scope",
            details={"allowed": list(SCOPES)},
        )
    if source_patient_id == patient_id:
        raise ValidationError(
            "A medical history cannot be copied onto the same patient.",
            code="copy_source_is_target",
        )
    _patient(db, tenant_id, patient_id)
    source = _patient(db, tenant_id, source_patient_id)
    now = _now()

    want_alerts = scope in ("all", "alerts")
    want_dental = scope in ("all", "dental")
    want_medical = scope in ("all", "medical")

    payload: dict[str, Any] = {"allow_contradictions": allow_contradictions}
    if want_alerts:
        payload["alerts"] = [
            {
                "alert_code": a.alert_code,
                "alert_label": a.alert_label,
                "response": a.response,
                "comments": a.comments,
            }
            for a in _alerts(db, tenant_id, source_patient_id)
            if a.alert_code != LEGACY_COMMENTS_CODE
        ]
        payload["replace_alerts"] = True
        source_head = header(db, tenant_id, source_patient_id)
        payload["comments"] = source_head.comments if source_head else None
    if want_dental:
        payload["dental_responses"] = [
            {"question_code": q.question_code, "question_text": q.question_text, "answer": q.answer}
            for q in _responses(db, tenant_id, source_patient_id, "dental")
        ]
        payload["replace_dental"] = True
    if want_medical:
        payload["medical_responses"] = [
            {"question_code": q.question_code, "question_text": q.question_text, "answer": q.answer}
            for q in _responses(db, tenant_id, source_patient_id, "medical")
        ]
        payload["replace_medical"] = True

    document = save_document(db, tenant_id, patient_id, payload, user_id=user_id)

    head = header(db, tenant_id, patient_id, create=True)
    head.copied_from_patient_id = source_patient_id
    head.copied_at = now
    head.copied_by = user_id
    version = _freeze_version(
        db, tenant_id=tenant_id, patient_id=patient_id, scope=scope, comments=document["comments"],
        content_hash=document["content_hash"], user_id=user_id, signature_id=None,
        source_patient_id=source_patient_id, copied_at=now, completed_at=None,
    )
    _event(
        db, tenant_id=tenant_id, patient_id=patient_id, entity_type="copy", action="copy",
        entity_id=version.id, code=scope,
        label=f"Copied from {source.last_name or ''}, {source.first_name or ''} (#{source.id})".strip(),
        source_patient_id=source_patient_id, user_id=user_id,
        new_value=json.dumps(
            {
                "alerts": len(document["alerts"]),
                "dental": len(document["dental_responses"]),
                "medical": len(document["medical_responses"]),
            }
        ),
    )
    db.commit()

    out = get_document(db, tenant_id, patient_id)
    out["copied_from_patient_id"] = source_patient_id
    out["version_id"] = version.id
    return out


# ── MH-6: versions + signature ───────────────────────────────────────────────
def _freeze_version(
    db: Session,
    *,
    tenant_id: int,
    patient_id: int,
    scope: str,
    comments: str | None,
    content_hash: str,
    user_id: int | None,
    signature_id: int | None,
    source_patient_id: int | None = None,
    copied_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> MedicalHistoryRecord:
    """Write the version header + its frozen answers (``medical_history_details``)."""
    alerts = [a for a in _alerts(db, tenant_id, patient_id) if a.alert_code != LEGACY_COMMENTS_CODE]
    dental = _responses(db, tenant_id, patient_id, "dental")
    medical = _responses(db, tenant_id, patient_id, "medical")
    flags = _alert_flags(db, tenant_id)

    record = MedicalHistoryRecord(
        tenant_id=tenant_id,
        patient_id=patient_id,
        signature_id=signature_id,
        scope=scope,
        content_hash=content_hash,
        comments=comments,
        item_count=len(alerts) + len(dental) + len(medical),
        completed_at=completed_at,
        completed_by=user_id if completed_at else None,
        source_patient_id=source_patient_id,
        copied_at=copied_at,
        is_archived=False,
        created_by=user_id,
    )
    db.add(record)
    db.flush()

    for alert in alerts:
        db.add(
            MedicalHistoryDetail(
                history_id=record.id,
                question_code=alert.alert_code,
                question_text=alert.alert_label or flags.get(alert.alert_code, {}).get("label"),
                answer_code=alert.response,
                answer_text=alert.response,
                notes=alert.comments,
                answer_type="alert",
                section=flags.get(alert.alert_code, {}).get("section"),
            )
        )
    for kind, rows in (("dental", dental), ("medical", medical)):
        for row in rows:
            db.add(
                MedicalHistoryDetail(
                    history_id=record.id,
                    question_code=row.question_code,
                    question_text=row.question_text,
                    answer_text=row.answer,
                    answer_type=kind,
                )
            )
    db.flush()
    return record


def sign(
    db: Session,
    tenant_id: int,
    patient_id: int,
    payload: dict[str, Any],
    *,
    user_id: int | None = None,
) -> dict[str, Any]:
    """MH-6: capture a signature *over a frozen version* of this history."""
    _patient(db, tenant_id, patient_id)
    signature_data = _clean(payload.get("signature_data"))
    if not signature_data:
        raise ValidationError(
            "signature_data is required to sign a medical history.",
            code="signature_data_required",
        )
    scope = payload.get("scope") or "all"
    if scope not in SCOPES:
        raise ValidationError(
            f"Unknown signature scope '{scope}'.", code="invalid_signature_scope",
            details={"allowed": list(SCOPES)},
        )
    signature_type = _clean(payload.get("signature_type")) or SIGNATURE_TYPE_MEDICAL_HISTORY
    now = _now()

    head = header(db, tenant_id, patient_id, create=True)
    alerts = [a for a in _alerts(db, tenant_id, patient_id) if a.alert_code != LEGACY_COMMENTS_CODE]
    dental = _responses(db, tenant_id, patient_id, "dental")
    medical = _responses(db, tenant_id, patient_id, "medical")
    content_hash = compute_content_hash(alerts, dental, medical, head.comments)

    signature = PatientSignature(
        patient_id=patient_id,
        signature_data=signature_data,
        signature_len=len(signature_data),
        device_source=_clean(payload.get("device_source")),
        is_user_sig=bool(payload.get("is_user_sig")),
        signature_type=signature_type,
        signed_at=now,
        signed_by_user_id=payload.get("signed_by_user_id") or user_id,
        content_hash=content_hash,
        is_active=True,
        created_by=user_id,
    )
    db.add(signature)
    db.flush()

    # MH-7: the previous standing signature of this type is superseded, not left
    # to a client-side "newest row wins" guess.
    for previous in _signatures(db, patient_id, active_only=True):
        if previous.id == signature.id:
            continue
        if (previous.signature_type or SIGNATURE_TYPE_MEDICAL_HISTORY) != signature_type:
            continue
        previous.is_active = False
        previous.superseded_by_id = signature.id
        previous.updated_by = user_id

    version = _freeze_version(
        db, tenant_id=tenant_id, patient_id=patient_id, scope=scope, comments=head.comments,
        content_hash=content_hash, user_id=user_id, signature_id=signature.id,
        completed_at=now,
    )
    head.last_signature_id = signature.id
    head.last_version_id = version.id
    for field in ("alerts", "dental", "medical"):
        if scope in ("all", field):
            setattr(head, f"{field}_completed_at", now)
            setattr(head, f"{field}_completed_by", user_id)
    head.updated_by = user_id

    _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type="signature",
           action="sign", entity_id=signature.id, code=signature_type,
           new_value=content_hash, user_id=user_id)
    db.commit()

    out = get_document(db, tenant_id, patient_id)
    out["version_id"] = version.id
    out["signature_id"] = signature.id
    return out


def void_signature(
    db: Session,
    tenant_id: int,
    signature_id: int,
    *,
    user_id: int | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """MH-7: clear a signature without deleting the record of it."""
    signature = db.get(PatientSignature, signature_id)
    if signature is None:
        raise NotFoundError(f"PatientSignature '{signature_id}' was not found")
    patient = _patient(db, tenant_id, signature.patient_id)
    if not signature.is_active:
        raise ValidationError(
            "This signature has already been voided or superseded.",
            code="signature_already_inactive",
        )
    signature.is_active = False
    signature.voided_at = _now()
    signature.voided_by = user_id
    signature.updated_by = user_id
    head = header(db, tenant_id, patient.id)
    if head is not None and head.last_signature_id == signature.id:
        head.last_signature_id = None
    _event(db, tenant_id=tenant_id, patient_id=patient.id, entity_type="signature",
           action="void", entity_id=signature.id, code=signature.signature_type,
           old_value=signature.content_hash, new_value=_clean(reason), user_id=user_id)
    db.commit()
    names = _actor_names(db, {signature.created_by, signature.signed_by_user_id, user_id})
    return _signature_out(signature, names)


def list_versions(db: Session, tenant_id: int, patient_id: int) -> list[dict[str, Any]]:
    _patient(db, tenant_id, patient_id)
    rows = _versions(db, tenant_id, patient_id, limit=None)
    names = _actor_names(db, {r.completed_by for r in rows if r.completed_by})
    return [_version_out(r, names) for r in rows]


def get_version(db: Session, tenant_id: int, patient_id: int, version_id: int) -> dict[str, Any]:
    _patient(db, tenant_id, patient_id)
    record = db.get(MedicalHistoryRecord, version_id)
    if record is None or record.patient_id != patient_id:
        raise NotFoundError(f"MedicalHistoryRecord '{version_id}' was not found")
    if record.tenant_id is not None and record.tenant_id != tenant_id:
        raise NotFoundError(f"MedicalHistoryRecord '{version_id}' was not found")
    details = list(
        db.execute(
            select(MedicalHistoryDetail).where(MedicalHistoryDetail.history_id == record.id)
        ).scalars()
    )
    names = _actor_names(db, {record.completed_by, record.created_by})
    out = _version_out(record, names)
    out["answers"] = [
        {
            "answer_type": d.answer_type,
            "question_code": d.question_code,
            "question_text": d.question_text,
            "answer_code": d.answer_code,
            "answer_text": d.answer_text,
            "notes": d.notes,
            "section": d.section,
        }
        for d in details
    ]
    signature = db.get(PatientSignature, record.signature_id) if record.signature_id else None
    out["signature"] = _signature_out(signature, names) if signature else None
    return out


def list_changes(
    db: Session,
    tenant_id: int,
    patient_id: int,
    *,
    entity_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """MH-8: the append-only, field-level change log for one patient."""
    _patient(db, tenant_id, patient_id)
    stmt = select(PatientMedicalHistoryEvent).where(
        PatientMedicalHistoryEvent.tenant_id == tenant_id,
        PatientMedicalHistoryEvent.patient_id == patient_id,
    )
    if entity_type:
        stmt = stmt.where(PatientMedicalHistoryEvent.entity_type == entity_type)
    rows = list(db.execute(stmt).scalars())
    rows.sort(key=lambda r: r.id, reverse=True)
    rows = rows[:limit]
    names = _actor_names(db, {r.changed_by for r in rows if r.changed_by})
    return [
        {
            "id": r.id,
            "patient_id": r.patient_id,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "code": r.code,
            "label": r.label,
            "action": r.action,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "source_patient_id": r.source_patient_id,
            "changed_by": r.changed_by,
            "changed_by_name": names.get(r.changed_by) if r.changed_by else None,
            "changed_at": r.created_at,
        }
        for r in rows
    ]


# ── MH-15: server-rendered form ──────────────────────────────────────────────
def _pdf_canvas():  # noqa: ANN202
    try:
        from reportlab.lib.pagesizes import LETTER  # noqa: PLC0415
        from reportlab.pdfgen import canvas  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ValidationError(
            "PDF rendering requires the 'reportlab' package (pip install -r requirements.txt)."
        ) from exc
    return canvas, LETTER


def render_pdf(db: Session, tenant_id: int, patient_id: int) -> bytes:
    """The legacy printer icon, server-side — and the natural place to state the
    signature's standing, since a printed medical history that does not say the
    signature is stale is a misleading clinical document."""
    doc = get_document(db, tenant_id, patient_id)
    canvas, LETTER = _pdf_canvas()
    buf = io.BytesIO()
    width, height = LETTER
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    pdf.setTitle(f"Medical History - patient {patient_id}")
    y = height - 56

    def line(text: str, *, size: int = 10, bold: bool = False, indent: int = 54) -> None:
        nonlocal y
        if y < 60:
            pdf.showPage()
            y = height - 56
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        pdf.drawString(indent, y, text[:110])
        y -= size + 4

    patient = doc["patient"]
    name = ", ".join(x for x in (patient["last_name"], patient["first_name"]) if x)
    line("Patient Medical History", size=16, bold=True)
    line(f"{name}   Chart #{patient['chart_no'] or patient['id']}   DOB {patient['dob'] or '-'}")
    status = doc["signature_status"]
    signed_at = (doc["current_signature"] or {}).get("signed_at")
    line(f"Signature: {status}" + (f"  (signed {signed_at})" if signed_at else ""), bold=True)
    y -= 6

    line("Medical Alerts", size=12, bold=True)
    answered = [a for a in doc["alerts"] if a["response"]]
    if not answered:
        line("No alerts answered.", indent=70)
    for alert in answered:
        flag = " [FLASH]" if alert["is_flash_alert"] else ""
        note = f" - {alert['comments']}" if alert["comments"] else ""
        line(f"{alert['alert_label'] or alert['alert_code']}: {alert['response'].upper()}{flag}{note}",
             indent=70)
    if doc["comments"]:
        line(f"Additional comments: {doc['comments']}", indent=70)
    y -= 6

    for title, key in (("Dental Questionnaire", "dental_responses"),
                       ("Medical Questionnaire", "medical_responses")):
        line(title, size=12, bold=True)
        rows = [r for r in doc[key] if r["answer"]]
        if not rows:
            line("Not completed.", indent=70)
        for row in rows:
            line(f"{row['question_text'] or row['question_code']}: {row['answer']}", indent=70)
        y -= 6

    if doc["emergency_contacts"]:
        line("Emergency Contacts", size=12, bold=True)
        for contact in doc["emergency_contacts"]:
            line(
                f"{contact['name']} ({contact['relationship'] or '-'}) {contact['phone'] or ''}",
                indent=70,
            )

    pdf.showPage()
    pdf.save()
    return buf.getvalue()


# ── the generic resources, kept honest ───────────────────────────────────────
class PatientMedicalAlertCRUD(CRUDBase[PatientMedicalAlert]):
    """The MH-12 contradiction rules and the MH-14 flash-alert propagation have
    to hold on the *generic* resource too, or a client can route around the
    composite write and store the contradiction one row at a time. Same
    reasoning as ``PatientCRUD`` and the patient checkbox rules.
    """

    def _guard(self, db: Session, tenant_id: int | None, patient_id: int,
               code: str | None, response: str | None, *, exclude_id: int | None = None,
               allow: bool = False) -> None:
        if tenant_id is None or not code:
            return
        flags = _alert_flags(db, tenant_id)
        merged: dict[str, str | None] = {}
        for row in _alerts(db, tenant_id, patient_id):
            if exclude_id is not None and row.id == exclude_id:
                continue
            merged[row.alert_code] = row.response
        merged[code] = response
        sections = {c: meta.get("section") for c, meta in flags.items()}
        rules.check_alert_contradictions(
            merged, sections, changed_codes={code}, allow=allow
        )

    def create(self, db: Session, data: dict[str, Any], *, tenant_id: int | None = None,
               created_by: int | None = None) -> PatientMedicalAlert:
        payload = dict(data)
        allow = bool(payload.pop("allow_contradictions", False))
        patient_id = payload.get("patient_id")
        self._guard(db, tenant_id, patient_id, _clean(payload.get("alert_code")),
                    _clean(payload.get("response")), allow=allow)
        payload.setdefault("answered_at", _now())
        obj = super().create(db, payload, tenant_id=tenant_id, created_by=created_by)
        if tenant_id is not None:
            _event(db, tenant_id=tenant_id, patient_id=obj.patient_id, entity_type="alert",
                   action="create", entity_id=obj.id, code=obj.alert_code,
                   label=obj.alert_label, new_value=obj.response, user_id=created_by)
            sync_flash_alerts(db, tenant_id, obj.patient_id, user_id=created_by)
            db.commit()
        return obj

    def update(self, db: Session, obj_id: Any, data: dict[str, Any], *,
               tenant_id: int | None = None, updated_by: int | None = None
               ) -> PatientMedicalAlert:
        payload = dict(data)
        allow = bool(payload.pop("allow_contradictions", False))
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        before = existing.response
        code = _clean(payload.get("alert_code")) or existing.alert_code
        response = _clean(payload["response"]) if "response" in payload else existing.response
        self._guard(db, tenant_id, existing.patient_id, code, response,
                    exclude_id=existing.id, allow=allow)
        if "response" in payload and before != response:
            payload.setdefault("answered_at", _now())
        obj = super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)
        if tenant_id is not None:
            if before != obj.response:
                _event(db, tenant_id=tenant_id, patient_id=obj.patient_id, entity_type="alert",
                       action="update", entity_id=obj.id, code=obj.alert_code,
                       label=obj.alert_label, old_value=before, new_value=obj.response,
                       user_id=updated_by)
            sync_flash_alerts(db, tenant_id, obj.patient_id, user_id=updated_by)
            db.commit()
        return obj

    def delete(self, db: Session, obj_id: Any, *, tenant_id: int | None = None) -> None:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        patient_id, code, response = existing.patient_id, existing.alert_code, existing.response
        super().delete(db, obj_id, tenant_id=tenant_id)
        if tenant_id is not None:
            _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type="alert",
                   action="delete", entity_id=obj_id, code=code, old_value=response)
            sync_flash_alerts(db, tenant_id, patient_id)
            db.commit()


class PatientQuestionnaireResponseCRUD(CRUDBase[PatientQuestionnaireResponse]):
    """MH-8: a per-row edit is logged the same way the composite write logs it,
    so the change log is complete whichever path the client took."""

    def create(self, db: Session, data: dict[str, Any], *, tenant_id: int | None = None,
               created_by: int | None = None) -> PatientQuestionnaireResponse:
        payload = dict(data)
        payload.setdefault("answered_at", _now())
        obj = super().create(db, payload, tenant_id=tenant_id, created_by=created_by)
        if tenant_id is not None:
            _event(db, tenant_id=tenant_id, patient_id=obj.patient_id,
                   entity_type=obj.questionnaire_type, action="create", entity_id=obj.id,
                   code=obj.question_code, label=obj.question_text, new_value=obj.answer,
                   user_id=created_by)
            db.commit()
        return obj

    def update(self, db: Session, obj_id: Any, data: dict[str, Any], *,
               tenant_id: int | None = None, updated_by: int | None = None
               ) -> PatientQuestionnaireResponse:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        before = existing.answer
        payload = dict(data)
        if "answer" in payload and _clean(payload["answer"]) != before:
            payload.setdefault("answered_at", _now())
        obj = super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)
        if tenant_id is not None and before != obj.answer:
            _event(db, tenant_id=tenant_id, patient_id=obj.patient_id,
                   entity_type=obj.questionnaire_type, action="update", entity_id=obj.id,
                   code=obj.question_code, label=obj.question_text, old_value=before,
                   new_value=obj.answer, user_id=updated_by)
            db.commit()
        return obj

    def delete(self, db: Session, obj_id: Any, *, tenant_id: int | None = None) -> None:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        patient_id = existing.patient_id
        kind, code, answer = existing.questionnaire_type, existing.question_code, existing.answer
        super().delete(db, obj_id, tenant_id=tenant_id)
        if tenant_id is not None:
            _event(db, tenant_id=tenant_id, patient_id=patient_id, entity_type=kind,
                   action="delete", entity_id=obj_id, code=code, old_value=answer)
            db.commit()


def enrich_medical_alerts(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001
    """MH-8/MH-14: resolve the Modified-By actor and denormalise the Setup
    catalog's ``is_flash_alert``/``blocks_charges`` onto each answered row, so a
    consumer can act on the answer without a ``GET /definitions`` per row."""
    rows = list(items)
    if not rows:
        return
    flags = _alert_flags(db, tenant_id) if tenant_id is not None else {}
    names = _actor_names(db, {r.created_by for r in rows} | {r.updated_by for r in rows})
    for row in rows:
        meta = flags.get(row.alert_code, {})
        row.section = meta.get("section")
        row.is_flash_alert = bool(meta.get("is_flash_alert"))
        row.blocks_charges = bool(meta.get("blocks_charges"))
        row.created_by_name = names.get(row.created_by) if row.created_by else None
        row.updated_by_name = names.get(row.updated_by) if row.updated_by else None


def enrich_questionnaire_responses(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    """MH-8: "Modified By" on the questionnaire tabs rendered blank because only
    the id existed; resolve it in one batched lookup."""
    rows = list(items)
    if not rows:
        return
    names = _actor_names(db, {r.created_by for r in rows} | {r.updated_by for r in rows})
    for row in rows:
        row.created_by_name = names.get(row.created_by) if row.created_by else None
        row.updated_by_name = names.get(row.updated_by) if row.updated_by else None
