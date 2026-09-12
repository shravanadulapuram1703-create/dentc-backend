"""Prescriptions — the drug<->medical-alert check and the acknowledgement audit
(MA-5, clinical safety).

``POST /prescriptions`` accepted any drug regardless of the patient's active
alerts, and nothing recorded that the prescriber saw them: the frontend's
banner + ``window.confirm`` was the only guard, and it was not persisted. Now:

* :func:`check_alerts` matches the drug against the patient's active alerts
  (the same summary the scheduler and the banner read) two ways —
  ``prescription_library.allergy_keys`` against the alert codes/labels, and the
  alert's own label against the drug name (``"Penicillin"`` in
  ``"Penicillin VK 500mg"``) for alerts in an allergy section.
* :class:`PrescriptionCRUD.create` refuses a match with **409**
  ``prescription_alert_conflict`` unless ``alerts_acknowledged`` is set — the
  override is deliberate, never silent — and persists *which* alerts were on
  file (``acknowledged_alert_ids`` + a full ``acknowledged_alerts`` snapshot)
  and the matches it found (``alert_warnings``), stamped ``_at`` / ``_by``.

Deliberately a warning-and-override model rather than a hard block: the
matcher is lexical (it has no drug ontology), so it can over-match — a 409 the
prescriber can acknowledge is the right failure mode; a refusal they cannot
get past would be prescribed around on paper.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.crud.base import CRUDBase
from app.db.models import Patient, Prescription, PrescriptionLibrary
from app.services import medical_alert_summary_service as summary_svc
from app.services.medical_history_catalog import to_code

#: A label shorter than this is never matched by substring against the drug
#: name — "Nuts" or "Eggs" would hit too much.
MIN_LABEL_MATCH_CHARS = 4
#: Alert labels that are a *negation* or a catch-all, never a substance.
_NON_SUBSTANCE_PREFIXES = ("no_", "other_", "see_", "prior_", "environmental_")


def _library_row(db: Session, tenant_id: int | None, library_rx_id: int | None,
                 drug_name: str | None) -> PrescriptionLibrary | None:
    if library_rx_id is not None:
        row = db.get(PrescriptionLibrary, library_rx_id)
        if row is not None and (tenant_id is None or row.tenant_id == tenant_id):
            return row
    if drug_name and tenant_id is not None:
        rows = list(
            db.execute(
                select(PrescriptionLibrary).where(
                    PrescriptionLibrary.tenant_id == tenant_id,
                    PrescriptionLibrary.is_active.is_(True),
                    PrescriptionLibrary.drug_name.ilike(drug_name.strip()),
                )
            ).scalars()
        )
        # Prefer a row that carries keys; otherwise any name match is fine.
        rows.sort(key=lambda r: (not bool(r.allergy_keys), r.id))
        return rows[0] if rows else None
    return None


def _allergy_keys(row: PrescriptionLibrary | None) -> list[str]:
    if row is None or not row.allergy_keys:
        return []
    keys = []
    for raw in row.allergy_keys:
        slug = to_code(str(raw))
        if slug and slug not in keys:
            keys.append(slug)
    return keys


def _label_tokens(alert: dict[str, Any]) -> list[str]:
    """Slugs from the alert worth looking for inside the drug name."""
    code = alert.get("code") or to_code(alert.get("label") or "")
    if not code or code.startswith(_NON_SUBSTANCE_PREFIXES):
        return []
    tokens = [code]
    # "Sulfa Drugs" -> "sulfa" (matches Sulfamethoxazole); first word only, and
    # only when it is long enough to be a substance name rather than a filler.
    first = code.split("_", 1)[0]
    if "_" in code and len(first) >= 5 and first not in ("local", "other", "prior"):
        tokens.append(first)
    return [t for t in tokens if len(t) >= MIN_LABEL_MATCH_CHARS]


def match_warnings(drug_name: str | None, allergy_keys: list[str],
                   alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure matcher: the alerts this drug conflicts with, and why."""
    drug_slug = to_code(drug_name or "")
    warnings: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    def add(alert: dict[str, Any], matched_on: str, key: str) -> None:
        ident = (alert["source"], alert["id"])
        if ident in seen:
            return
        seen.add(ident)
        warnings.append({
            "alert_id": alert["id"],
            "source": alert["source"],
            "code": alert.get("code") or "",
            "label": alert["label"],
            "section": alert["section"],
            "matched_on": matched_on,
            "key": key,
        })

    for alert in alerts:
        code = alert.get("code") or ""
        label_slug = to_code(alert.get("label") or "")
        # 1) library allergy keys vs the alert's code / label (free-text alerts
        #    match on the label text, which is all they have).
        for key in allergy_keys:
            if key == code or key == label_slug or (
                len(key) >= MIN_LABEL_MATCH_CHARS and (key in code or key in label_slug)
            ):
                add(alert, "allergy_key", key)
                break
        # 2) the alert's own label inside the drug name — allergy sections only,
        #    so "Diabetes" never flags "Metformin" by accident of wording.
        if drug_slug and summary_svc.is_allergy_section(alert.get("section")):
            for token in _label_tokens(alert):
                if token in drug_slug:
                    add(alert, "drug_name", token)
                    break
    return warnings


def check_alerts(db: Session, tenant_id: int, patient_id: int, *, drug_name: str | None,
                 library_rx_id: int | None = None) -> dict[str, Any]:
    """The MA-5 check as a read: what ``POST /prescriptions`` will do."""
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    summary = summary_svc.summarize_one(db, tenant_id, patient_id)
    library = _library_row(db, tenant_id, library_rx_id, drug_name)
    warnings = match_warnings(drug_name, _allergy_keys(library), summary["alerts"])
    return {
        "patient_id": patient_id,
        "drug_name": drug_name or "",
        "library_rx_id": library.id if library else library_rx_id,
        "warnings": warnings,
        "alerts": summary["alerts"],
        "history_on_file": summary["history_on_file"],
        "blocking": bool(warnings),
        "override_field": "alerts_acknowledged",
    }


def _snapshot(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for a in alerts:
        item = dict(a)
        at = item.get("answered_at")
        if isinstance(at, datetime):
            item["answered_at"] = at.isoformat()
        out.append(item)
    return out


class PrescriptionCRUD(CRUDBase[Prescription]):
    """Generic CRUD + the MA-5 gate on create. ``prescriptions`` has no
    ``tenant_id``; the patient is the tenancy anchor, so a foreign patient is a
    404 before anything is matched."""

    def create(self, db: Session, data: dict[str, Any], *, tenant_id: int | None = None,
               created_by: int | None = None) -> Prescription:
        payload = dict(data)
        acknowledged = bool(payload.pop("alerts_acknowledged", False))
        ack_ids = payload.pop("acknowledged_alert_ids", None)
        patient_id = payload.get("patient_id")
        warnings: list[dict[str, Any]] = []
        if tenant_id is not None and patient_id is not None:
            check = check_alerts(
                db, tenant_id, int(patient_id),
                drug_name=payload.get("drug_name"), library_rx_id=payload.get("library_rx_id"),
            )
            warnings = check["warnings"]
            if warnings and not acknowledged:
                raise ConflictError(
                    "This drug matches an active medical alert for the patient. Review the "
                    "alerts and resubmit with alerts_acknowledged=true to prescribe anyway.",
                    code="prescription_alert_conflict",
                    details={
                        "warnings": warnings,
                        "alerts": _snapshot(check["alerts"]),
                        "override_field": "alerts_acknowledged",
                    },
                )
            active = check["alerts"]
            history_ids = [a["id"] for a in active if a["source"] == "medical_history"]
            payload["alerts_acknowledged"] = acknowledged
            payload["alert_warnings"] = warnings or None
            if acknowledged:
                payload["acknowledged_alert_ids"] = (
                    list(ack_ids) if ack_ids is not None else history_ids
                )
                payload["acknowledged_alerts"] = _snapshot(active)
                payload["alerts_acknowledged_at"] = datetime.utcnow()
                payload["alerts_acknowledged_by"] = created_by
        obj = super().create(db, payload, tenant_id=tenant_id, created_by=created_by)
        obj.warnings = warnings  # transient echo on the 201 (PrescriptionRead.warnings)
        return obj


__all__ = ["PrescriptionCRUD", "check_alerts", "match_warnings"]
