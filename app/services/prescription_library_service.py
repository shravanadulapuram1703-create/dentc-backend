"""Prescriptions Setup — the rules the generic CRUD engine cannot express.

Backs §4 (RX-1/2/4) of ``docs/pick-list/pick_list_setup_backend_devreport.md``.

* **RX-4 duplicate guard** — ``prescription_library`` had no uniqueness at all, so
  every migration re-run appended the whole Denticon library again (85 drugs x 5
  runs = 425 rows; the Rx Drug Name picker listed each drug five times). The
  migration collapses the copies and adds ``(tenant_id, legacy_id)`` uniqueness,
  which stops the *importer* recurring it. This module stops the *API* recurring
  it: an active row with the same **drug name + dispense + sig** (trimmed,
  whitespace-collapsed, case-insensitive) is a 409 ``duplicate_prescription``
  unless the caller sends ``allow_duplicate``. Deliberately the INS-PT-19 shape
  and deliberately **not a DB constraint**: the seed legitimately lists
  *Chlorhexidine Gluconate 0.12% Oral Rinse* twice with different dispense/sig,
  and an admin may want a second "Amoxicillin" row on purpose — the API refuses
  the *accidental* duplicate, never the duplicate. A same-name row with a
  different configuration is reported (``same_name_matches``) and never blocks,
  and a match against an *inactive* row is reported (``inactive_matches``) so
  the dialog can offer to reactivate instead.

  On PATCH the guard fires on a **move** — the (name, dispense, sig) identity
  actually changing — not on stored state, so a pre-existing duplicate stays
  editable (the PLAN guard's rule, same reasoning).

* **RX-2 sig cap** — the legacy editor enforces 240 characters and the column is
  ``String(500)``; the schema factory does not propagate column lengths, so the
  API enforced nothing at all and a 501-char sig was a 500. ``SIG_MAX_LENGTH``
  is the one number, enforced as a 422 ``sig_too_long`` on both writes (only
  when the payload carries ``sig``, so re-flagging a migrated row cannot fail on
  a field it did not touch) and published at ``GET /prescription-library/limits``
  so the frontend counter and the server agree by construction. The column is
  left at 500: no live value exceeds 177, and a narrower column would turn an
  over-long legacy value into a migration failure rather than a validation one.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.crud.base import CRUDBase
from app.db.models import PrescriptionLibrary

# RX-2: the legacy "Allowed 240 Characters" rule, now server-side.
SIG_MAX_LENGTH = 240
DRUG_NAME_MAX_LENGTH = 255
DISPENSE_MAX_LENGTH = 255

#: The identity a duplicate is judged on — same tuple as the legacy picker label
#: (``drug_name`` suffixed with ``dispense · sig`` when a name repeats).
DUPLICATE_KEY_FIELDS = ("drug_name", "dispense", "sig")
OVERRIDE_FIELD = "allow_duplicate"

_WS = re.compile(r"\s+")


def normalise_key(value: str | None) -> str:
    """Trim, collapse internal whitespace, lower-case. ``None`` and ``""`` are the
    same thing here — a blank dispense is a blank dispense however it was typed.
    ``lower()`` rather than ``casefold()`` so the Python key and the SQL
    ``lower()`` prefilter agree on every character."""
    if value is None:
        return ""
    return _WS.sub(" ", str(value).strip()).lower()


def _name_prefilter(name_key: str):  # noqa: ANN001
    """SQL clause that can never *miss* a row :func:`normalise_key` would match:
    each whitespace run in the key becomes ``%``, so a stored double space still
    hits, and the exact compare is finished in Python on the (tiny) candidate
    set. Portable across Postgres and the SQLite test engine."""
    escaped = name_key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = "%".join(escaped.split(" "))
    return func.lower(func.trim(PrescriptionLibrary.drug_name)).like(pattern, escape="\\")


def match_payload(rows: list[PrescriptionLibrary]) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "drug_name": r.drug_name,
            "dispense": r.dispense,
            "sig": r.sig,
            "refills": r.refills,
            "is_as_written": r.is_as_written,
            "is_active": r.is_active,
            "legacy_id": r.legacy_id,
        }
        for r in rows
    ]


def find_matches(
    db: Session,
    tenant_id: int | None,
    *,
    drug_name: str | None,
    dispense: str | None,
    sig: str | None,
    exclude_id: int | None = None,
) -> dict[str, list[PrescriptionLibrary]]:
    """Every library row that shares the drug name, split into the three buckets
    the guard and the availability probe both report.

    ``active`` / ``inactive``: identical (name, dispense, sig).
    ``same_name``: same name, different dispense or sig — the Chlorhexidine
    case; informational only.
    """
    name_key = normalise_key(drug_name)
    if not name_key:
        return {"active": [], "inactive": [], "same_name": []}
    stmt = select(PrescriptionLibrary).where(_name_prefilter(name_key))
    if tenant_id is not None:
        stmt = stmt.where(PrescriptionLibrary.tenant_id == tenant_id)
    if exclude_id is not None:
        stmt = stmt.where(PrescriptionLibrary.id != exclude_id)
    candidates = db.execute(stmt.order_by(PrescriptionLibrary.id)).scalars().all()

    disp_key, sig_key = normalise_key(dispense), normalise_key(sig)
    out: dict[str, list[PrescriptionLibrary]] = {"active": [], "inactive": [], "same_name": []}
    for row in candidates:
        if normalise_key(row.drug_name) != name_key:
            continue  # the LIKE prefilter over-matches on purpose
        identical = (
            normalise_key(row.dispense) == disp_key and normalise_key(row.sig) == sig_key
        )
        if not identical:
            out["same_name"].append(row)
        elif row.is_active:
            out["active"].append(row)
        else:
            out["inactive"].append(row)
    return out


def availability(
    db: Session,
    tenant_id: int | None,
    *,
    drug_name: str,
    dispense: str | None = None,
    sig: str | None = None,
    exclude_id: int | None = None,
) -> dict[str, Any]:
    """RX-4 probe: ``taken`` is exactly what the save path will 409 on."""
    found = find_matches(
        db, tenant_id, drug_name=drug_name, dispense=dispense, sig=sig, exclude_id=exclude_id
    )
    return {
        "drug_name": drug_name,
        "dispense": dispense,
        "sig": sig,
        "taken": bool(found["active"]),
        "matches": match_payload(found["active"]),
        "inactive_matches": match_payload(found["inactive"]),
        "same_name_matches": match_payload(found["same_name"]),
        "override_field": OVERRIDE_FIELD,
    }


def limits() -> dict[str, Any]:
    """RX-2: what the API enforces, so the editor's counter cannot drift."""
    return {
        "sig_max_length": SIG_MAX_LENGTH,
        "drug_name_max_length": DRUG_NAME_MAX_LENGTH,
        "dispense_max_length": DISPENSE_MAX_LENGTH,
        "duplicate_key_fields": list(DUPLICATE_KEY_FIELDS),
        "override_field": OVERRIDE_FIELD,
    }


def _check_lengths(payload: dict[str, Any]) -> None:
    """Only the fields the payload carries are judged (a PATCH of ``is_active``
    on a migrated row must not fail on a sig it did not touch)."""
    for field, cap in (
        ("sig", SIG_MAX_LENGTH),
        ("drug_name", DRUG_NAME_MAX_LENGTH),
        ("dispense", DISPENSE_MAX_LENGTH),
    ):
        value = payload.get(field)
        if value is not None and len(value) > cap:
            raise ValidationError(
                f"{field} may be at most {cap} characters",
                code=f"{field}_too_long",
                details={"field": field, "max_length": cap, "length": len(value)},
            )


def _strip_strings(payload: dict[str, Any]) -> dict[str, Any]:
    """Store what the user meant, not their trailing spaces. A blank ``drug_name``
    is a 422 here rather than a NOT NULL error from the database."""
    for field in DUPLICATE_KEY_FIELDS:
        if field in payload and isinstance(payload[field], str):
            payload[field] = payload[field].strip()
    if "drug_name" in payload and not payload["drug_name"]:
        raise ValidationError(
            "drug_name must not be blank",
            code="drug_name_required",
            details={"field": "drug_name"},
        )
    return payload


class PrescriptionLibraryCRUD(CRUDBase):
    """RX-2 + RX-4 on every write path (``crud_class`` for ``/prescription-library``)."""

    def _guard(
        self,
        db: Session,
        *,
        tenant_id: int | None,
        drug_name: str | None,
        dispense: str | None,
        sig: str | None,
        exclude_id: int | None,
        allow_duplicate: bool,
    ) -> None:
        if allow_duplicate:
            return
        found = find_matches(
            db, tenant_id, drug_name=drug_name, dispense=dispense, sig=sig, exclude_id=exclude_id
        )
        if not found["active"]:
            return
        raise ConflictError(
            "An active prescription with this drug name, dispense and sig already exists",
            code="duplicate_prescription",
            details={
                "drug_name": drug_name,
                "dispense": dispense,
                "sig": sig,
                "matches": match_payload(found["active"]),
                "inactive_matches": match_payload(found["inactive"]),
                "same_name_matches": match_payload(found["same_name"]),
                # The dialog's third option. Legacy allows the duplicate, so the
                # API has to as well — it just refuses to make one by accident.
                "override_field": OVERRIDE_FIELD,
            },
        )

    def create(
        self, db: Session, data: dict[str, Any], *,
        tenant_id: int | None = None, created_by: int | None = None,
    ) -> PrescriptionLibrary:
        payload = _strip_strings(dict(data))
        allow = bool(payload.pop(OVERRIDE_FIELD, False))
        _check_lengths(payload)
        # A row created inactive cannot collide with anything the picker offers.
        if payload.get("is_active", True):
            self._guard(
                db, tenant_id=tenant_id,
                drug_name=payload.get("drug_name"),
                dispense=payload.get("dispense"),
                sig=payload.get("sig"),
                exclude_id=None, allow_duplicate=allow,
            )
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(
        self, db: Session, obj_id: Any, data: dict[str, Any], *,
        tenant_id: int | None = None, updated_by: int | None = None,
    ) -> PrescriptionLibrary:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        payload = _strip_strings(dict(data))
        allow = bool(payload.pop(OVERRIDE_FIELD, False))
        _check_lengths(payload)
        # Judge the merge of payload + stored row: a PATCH carrying only ``sig``
        # is still checked against the row's own name and dispense.
        merged = {
            f: payload.get(f, getattr(existing, f)) for f in DUPLICATE_KEY_FIELDS
        }
        moved = any(
            normalise_key(merged[f]) != normalise_key(getattr(existing, f))
            for f in DUPLICATE_KEY_FIELDS
        )
        # Re-activating a row is a move too: an inactive twin of a live row was
        # allowed to exist, and flipping it back on is what recreates the dupe.
        reactivated = bool(payload.get("is_active")) and not existing.is_active
        will_be_active = payload.get("is_active", existing.is_active)
        if will_be_active and (moved or reactivated):
            self._guard(
                db, tenant_id=tenant_id,
                drug_name=merged["drug_name"],
                dispense=merged["dispense"],
                sig=merged["sig"],
                exclude_id=existing.id, allow_duplicate=allow,
            )
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)
