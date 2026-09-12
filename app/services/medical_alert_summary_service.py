"""Per-patient medical-alert summary (MA-1/MA-2/MA-6/MA-7).

Two tables hold alert-like data and, before this module, nothing on the server
read them together: ``patient_medical_alerts`` (the Medical History tab's
tri-state answers — a YES row *is* the alert) and ``patient_alerts`` (free-text
banner alerts). The scheduler feed derived ``has_alert`` from the second alone,
so a patient with three YES answers and no free-text alert was reported as
having no alert, and every consumer fanned out two list calls per patient to
find out otherwise (80 requests for a 40-patient day view).

:func:`summarize` is the one place the question is answered, batched over a set
of patients in four statements regardless of how many, and it is what the
scheduler feed, the patient context, the summary endpoints and the prescription
allergy check all read — so they cannot disagree.

Sync semantics between the two tables (MA-6), stated once:

* A YES answer is **not** mirrored into ``patient_alerts`` as such — the summary
  reads both tables, so mirroring would only create duplicates. The only rows
  ``sync_flash_alerts`` writes there are answers whose catalog item (or
  per-answer override) is flagged ``is_flash_alert`` / ``blocks_charges``,
  linked by ``source_medical_alert_id``.
* YES -> NO / unknown / cleared / soft-deleted: the linked banner row (if any)
  is deactivated and ``deactivated_on`` stamped; a hand-typed row is never
  touched. Re-answering YES reactivates the same row.
* Copy Medical History (MH-4) and ``POST /patients/register`` run the same sync
  after writing the answers.
* A linked banner row is skipped by the summary when its source answer is
  already listed, so nothing is ever counted twice.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PatientAlert, PatientMedicalAlert, PatientMedicalHistory
from app.services.medical_history_catalog import ALERT_SECTION_ORDER
from app.services.medical_history_service import (
    LEGACY_COMMENTS_CODE,
    alert_flags,
    effective_alert_meta,
)

#: Section reported for free-text ``patient_alerts`` rows (matches the frontend).
PATIENT_ALERT_SECTION = "Account Alert"
#: Section reported when neither the row nor the catalog names one.
UNKNOWN_SECTION = "Other"

_ALLERGY = re.compile(r"allerg", re.I)


def is_allergy_section(section: str | None) -> bool:
    return bool(section and _ALLERGY.search(section))


def _section_rank(section: str) -> int:
    try:
        return ALERT_SECTION_ORDER.index(section)
    except ValueError:
        return len(ALERT_SECTION_ORDER) + (0 if section == PATIENT_ALERT_SECTION else 1)


def _sort_key(item: dict[str, Any], order: dict[str, int]) -> tuple:
    return (
        _section_rank(item["section"]),
        order.get(item["code"], 10_000_000) if item["code"] else 10_000_000,
        (item["label"] or "").lower(),
    )


def summary_text(alerts: list[dict[str, Any]]) -> str | None:
    """``"Allergic To: Aspirin, Penicillin; Check, if applicable: Diabetes"``."""
    if not alerts:
        return None
    groups: list[tuple[str, list[str]]] = []
    for item in alerts:
        if groups and groups[-1][0] == item["section"]:
            groups[-1][1].append(item["label"])
        else:
            groups.append((item["section"], [item["label"]]))
    return "; ".join(f"{section}: {', '.join(labels)}" for section, labels in groups)


def empty_summary(patient_id: int) -> dict[str, Any]:
    return {
        "patient_id": patient_id,
        "alerts": [],
        "alert_count": 0,
        "allergy_count": 0,
        "comments": "",
        "history_on_file": False,
        "summary_text": None,
    }


def summarize(db: Session, tenant_id: int, patient_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """``{patient_id: summary}`` for every requested patient, in four statements."""
    ids = {int(p) for p in patient_ids if p is not None}
    if not ids:
        return {}
    flags = alert_flags(db, tenant_id)
    order = {code: meta.get("order", 10_000_000) for code, meta in flags.items()}

    history_rows = list(
        db.execute(
            select(PatientMedicalAlert).where(
                PatientMedicalAlert.tenant_id == tenant_id,
                PatientMedicalAlert.patient_id.in_(ids),
                PatientMedicalAlert.is_active.is_(True),
            )
        ).scalars()
    )
    banner_rows = list(
        db.execute(
            select(PatientAlert).where(
                PatientAlert.patient_id.in_(ids), PatientAlert.is_active.is_(True)
            )
        ).scalars()
    )
    headers = {
        h.patient_id: h
        for h in db.execute(
            select(PatientMedicalHistory).where(
                PatientMedicalHistory.tenant_id == tenant_id,
                PatientMedicalHistory.patient_id.in_(ids),
            )
        ).scalars()
    }

    out = {pid: empty_summary(pid) for pid in ids}
    legacy_comments: dict[int, str] = {}
    listed_history_ids: set[int] = set()

    for row in history_rows:
        summary = out[row.patient_id]
        if row.alert_code == LEGACY_COMMENTS_CODE:
            if row.comments:
                legacy_comments[row.patient_id] = row.comments.strip()
            continue
        summary["history_on_file"] = True
        if (row.response or "").strip().lower() != "yes":
            continue
        meta = effective_alert_meta(row, flags)
        listed_history_ids.add(row.id)
        summary["alerts"].append({
            "id": row.id,
            "source": "medical_history",
            "code": row.alert_code,
            "label": meta["label"],
            "section": meta["section"] or UNKNOWN_SECTION,
            "comments": (row.comments or "").strip(),
            "is_flash_alert": meta["is_flash_alert"],
            "blocks_charges": meta["blocks_charges"],
            "answered_at": row.answered_at or row.updated_at or row.created_at,
        })

    for row in banner_rows:
        # MA-6: a banner row raised *from* an answer is the same alert — never twice.
        source_id = row.source_medical_alert_id
        if source_id is not None and source_id in listed_history_ids:
            continue
        out[row.patient_id]["alerts"].append({
            "id": row.id,
            "source": "patient_alert",
            "code": "",
            "label": (row.alert or "").strip() or "Patient alert",
            "section": PATIENT_ALERT_SECTION,
            "comments": "",
            "is_flash_alert": bool(row.is_flash_alert),
            "blocks_charges": bool(row.blocks_charges),
            "answered_at": row.created_at,
        })

    for pid, summary in out.items():
        head = headers.get(pid)
        summary["comments"] = (
            (head.comments or "").strip() if head and head.comments
            else legacy_comments.get(pid, "")
        )
        summary["alerts"].sort(key=lambda item: _sort_key(item, order))
        summary["alert_count"] = len(summary["alerts"])
        summary["allergy_count"] = sum(
            1 for a in summary["alerts"] if is_allergy_section(a["section"])
        )
        summary["summary_text"] = summary_text(summary["alerts"])
    return out


def summarize_one(db: Session, tenant_id: int, patient_id: int) -> dict[str, Any]:
    return summarize(db, tenant_id, [patient_id]).get(patient_id) or empty_summary(patient_id)


__all__ = [
    "PATIENT_ALERT_SECTION",
    "UNKNOWN_SECTION",
    "empty_summary",
    "is_allergy_section",
    "summarize",
    "summarize_one",
    "summary_text",
]
