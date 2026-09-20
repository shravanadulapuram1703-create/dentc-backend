"""Load the fee-schedule bindings the Denticon migration dropped (pricing R1).

Why this exists
---------------
The resolver in ``app/services/pricing_service.py`` can only price a charge from
pointers that exist. On the migrated tenant almost none of them did, and not
because the source lacked them — because the migration steps never read the
columns:

===========================  ==========================  =====================
Source column                Destination                 State before this
===========================  ==========================  =====================
``Office.FEEID``             ``offices.default_ucr_fee_schedule_id``  NULL on all 15
``Office.PATIENTFEEID``      ``offices.default_fee_schedule_id``      NULL on all 15
``PATIENT.FEESCHEDULE``      ``patients.fee_schedule_id``             34 of 83,861
``Carrier.FEEID``            a carrier-keyed assignment               0 rows
``FeeScheD.AMBCODE``         ``fee_schedule_entries.amb_code``         NULL on all
``FeeScheH.FEETYPE``         ``fee_schedules.fee_type``                mis-mapped
``InsPlans.PRINTOFFICEUCR``  ``insurance_plans.fees_to_print``         default only
``PatInsPlans.INSTYPE``      ``patient_insurance.insurance_type``      1 secondary
``PatInsPlans.INDDEDREM``    ``patient_insurance.deductible_remaining`` 3 non-zero
===========================  ==========================  =====================

Those gaps are why the only tier that priced anything was a pair of duplicated
"practice-wide" assignment rows, and why ``scripts/backfill_office_fee_schedules.py``
had to *infer* an office linkage statistically. That script tests an office-keyed
hypothesis the data disproves — it matched 96–100 % on ``ucr_fee`` but only 10–22 %
on the contracted fee, because the contracted fee is patient- and payer-keyed, not
office-keyed. Do not run its fee side; this script reads the answer instead of
guessing it.

Evidence for the mapping (joined offline over 50,348 charges from 2025)
----------------------------------------------------------------------
* the posted fee equals the schedule named on the charge's own
  ``LEDGERINSD.FEEID`` on **99.66 %** of them;
* ``ucr_fee`` equals the **office's** ``Office.FEEID`` list on **96.3 %** — the one
  fee column that really is office-determined;
* the patient's own ``FEESCHEDULE`` explains **85.2 %** directly, and the rest are
  priced by carrier lists 110–122 that never appear on any patient, which is what
  makes the payer assignment outrank the patient's list.

What it will not do
-------------------
* It never writes ``insurance_plans.is_prepaid``. The legacy ``ISPREPAID`` is an
  8-value code (9 on 15,364 plans, 0 on 8,440, 2 on 7,459, then 8/4/1/3/5) that
  ``s07`` pushed through a boolean parser, and nobody has decoded it yet. The raw
  value is stored in ``legacy_prepaid_code`` and the schedule's ``pricing_model``
  decides the arithmetic regardless.
* It never deletes the legacy targetless assignment rows. They are the only tier
  pricing anything until offices and patients have pointers, so removing them
  belongs to R3 — after this script has run and been reviewed.
* The ``patient_insurance`` repair is split behind its own flags, because
  restoring ``INDDEDREM`` changes what every future estimate charges the patient
  (a stored ``0`` means "no deductible applied"; NULL falls back to the plan's
  deductible, which is 50.00 on 9,215 plans), and re-pointing a slot can change
  *which* plan is primary — i.e. which coverage rules price the patient.

Usage
-----
    python -m scripts.backfill_pricing_hierarchy                      # report only
    python -m scripts.backfill_pricing_hierarchy --only schedules --only offices
    python -m scripts.backfill_pricing_hierarchy --apply
    python -m scripts.backfill_pricing_hierarchy --apply --overwrite
    python -m scripts.backfill_pricing_hierarchy --apply --only slots \
        --apply-deductibles --apply-primary-changes

Source files come from ``DATA_SOURCE_PATH`` (the same ``.env`` the migration uses).
Every pass is idempotent and tenant-scoped: legacy ids are resolved per tenant, so
one practice's ``FEEID 109`` can never touch another's.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# A Windows console is cp1252, where printing a box-drawing character or an
# em-dash raises UnicodeEncodeError. This script's whole output is a long report,
# so a stray non-ASCII character must not kill a run half way through it.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - non-tty or old stream
        pass

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services import fee_vocab  # noqa: E402

SECTIONS = ("schedules", "offices", "patients", "carriers", "entries", "plans", "slots")
_CHUNK = 1000


# ── source access (mirrors migration.utils.reader without importing it) ──────


def _source_root() -> Path:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    except ImportError:  # pragma: no cover
        pass
    raw = os.environ.get("DATA_SOURCE_PATH") or getattr(settings, "DATA_SOURCE_PATH", "")
    if not raw:
        raise SystemExit(
            "DATA_SOURCE_PATH is not set — point it at the Denticon export folder."
        )
    root = Path(raw)
    if not root.exists():
        raise SystemExit(f"DATA_SOURCE_PATH does not exist: {root}")
    return root


def _read(path: Path):
    """Yield each export row as a dict (cp1252, quoted CSV or TSV)."""
    if not path.exists():
        return
    with open(path, encoding="cp1252", errors="replace", newline="") as fh:
        first = fh.readline()
        if not first:
            return
        delimiter = "\t" if first.count("\t") > first.count(",") else ","

        def _lines():
            yield first
            yield from fh

        reader = csv.reader(_lines(), delimiter=delimiter, quotechar='"')
        try:
            headers = [h.strip().lstrip("﻿") for h in next(reader)]
        except StopIteration:
            return
        for row in reader:
            if not row or not row[0].strip():
                continue
            while len(row) < len(headers):
                row.append("")
            yield dict(zip(headers, row, strict=False))


def _read_many(root: Path, *names: str):
    """Read a single file or every ``N.txt`` inside a folder of the same name."""
    for name in names:
        path = root / name
        if path.is_dir():
            for part in sorted(path.glob("*.txt")):
                yield from _read(part)
        elif path.exists():
            yield from _read(path)


def _s(value: object) -> str:
    return str(value or "").strip()


def _money(value: object) -> Decimal | None:
    raw = _s(value)
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "").replace("$", ""))
    except InvalidOperation:
        return None


def _is_set(value: object) -> bool:
    """A legacy pointer that actually points somewhere (``0``/blank do not)."""
    raw = _s(value)
    return bool(raw) and raw != "0"


# ── id maps, always per tenant ───────────────────────────────────────────────


class Maps:
    """Legacy id to primary key, keyed ``(tenant_id, legacy_id)`` throughout.

    Denticon ids are unique per practice group, not globally, and this revision
    made ``fee_schedules.legacy_id`` unique *per tenant* for that reason. Resolving
    without the tenant is how one practice's backfill reaches another's rows.
    """

    def __init__(self, db: Session) -> None:
        self.tenant_by_pgid: dict[str, int] = {
            _s(r.legacy_id): r.id
            for r in db.execute(text("SELECT id, legacy_id FROM tenants WHERE legacy_id IS NOT NULL"))
        }
        self.schedule: dict[tuple[int, str], int] = {
            (r.tenant_id, _s(r.legacy_id)): r.id
            for r in db.execute(
                text("SELECT id, tenant_id, legacy_id FROM fee_schedules WHERE legacy_id IS NOT NULL")
            )
        }
        self.office: dict[tuple[int, str], int] = {
            (r.tenant_id, _s(r.legacy_id)): r.id
            for r in db.execute(
                text("SELECT id, tenant_id, legacy_id FROM offices WHERE legacy_id IS NOT NULL")
            )
        }
        self.carrier: dict[tuple[int, str], int] = {
            (r.tenant_id, _s(r.legacy_id)): r.id
            for r in db.execute(
                text(
                    "SELECT id, tenant_id, legacy_id FROM insurance_carriers "
                    "WHERE legacy_id IS NOT NULL"
                )
            )
        }
        self.default_tenant = min(self.tenant_by_pgid.values()) if self.tenant_by_pgid else None

    def tenant(self, pgid: object) -> int | None:
        return self.tenant_by_pgid.get(_s(pgid), self.default_tenant)

    def schedule_id(self, pgid: object, feeid: object) -> int | None:
        tenant = self.tenant(pgid)
        if tenant is None or not _is_set(feeid):
            return None
        return self.schedule.get((tenant, _s(feeid)))


def _chunked(rows: list, size: int = _CHUNK):
    for start in range(0, len(rows), size):
        yield rows[start:start + size]


def _apply(db: Session, sql: str, rows: list[dict], *, apply: bool) -> int:
    """Row-wise write, for the small sections (tens of rows).

    Do not use this for the patient or plan passes: psycopg2 turns an
    ``executemany`` into one statement per row, and at 79,077 patients that is
    79,077 round trips, i.e. minutes of wall clock with a write transaction held
    open. :func:`_apply_arrays` exists for those.
    """
    if not rows or not apply:
        return len(rows)
    for chunk in _chunked(rows):
        db.execute(text(sql), chunk)
    return len(rows)


def _apply_arrays(
    db: Session, sql: str, columns: dict[str, list], *, apply: bool, chunk: int = 5000
) -> int:
    """One statement per chunk, passing each column as a Postgres array.

    The statement joins ``unnest(...)`` against the target table, so 79,077 updates
    become ~16 round trips. psycopg2 adapts a Python list to an array natively, and
    every array is cast explicitly in the SQL so a column that happens to be all
    NULL in a chunk still resolves to a type.
    """
    count = len(next(iter(columns.values()))) if columns else 0
    if not count or not apply:
        return count
    for start in range(0, count, chunk):
        db.execute(text(sql), {k: v[start:start + chunk] for k, v in columns.items()})
    return count


# ── 1. schedules: kind, pricing model, and blank-vs-zero fees ────────────────


def section_schedules(db: Session, root: Path, maps: Maps, *, apply: bool) -> dict:
    """Set ``fee_type`` / ``pricing_model`` from the export, and un-zero blank fees.

    ``FEETYPE`` is an assignment *mode* (0 unbound, 2 assign-to-plan, 3
    assign-to-carrier) and carries **no** UCR information — ``s09``'s
    ``{"1": "ucr", ...}`` map is why 12 of 13 schedules ended up labelled ``ucr``.
    A list is a UCR list because an office points at it with ``Office.FEEID``, so
    that is what decides it here.
    """
    feetype: dict[tuple[int, str], str] = {}
    for row in _read(root / "FeeScheH.txt"):
        tenant = maps.tenant(row.get("PGID"))
        if tenant is not None and _s(row.get("FEEID")):
            feetype[(tenant, _s(row.get("FEEID")))] = _s(row.get("FEETYPE"))

    # Every schedule some office uses as its UCR list.
    ucr_legacy: set[tuple[int, str]] = set()
    for row in _read(root / "Office.txt"):
        tenant = maps.tenant(row.get("PGID"))
        if tenant is not None and _is_set(row.get("FEEID")):
            ucr_legacy.add((tenant, _s(row.get("FEEID"))))

    # A copay list is one whose amounts live in the insurance column. Measured,
    # not assumed: on legacy 147/148 every PATAMT is blank and INSAMT carries the
    # figure, while the two SAMPLE assign-to-plan lists carry real patient fees and
    # must stay percentage.
    shape = {
        (r.id): (r.with_ins, r.with_pat)
        for r in db.execute(
            text(
                "SELECT fs.id, "
                "count(*) FILTER (WHERE e.insurance_fee IS NOT NULL AND e.insurance_fee <> 0) AS with_ins, "
                "count(*) FILTER (WHERE e.patient_fee IS NOT NULL AND e.patient_fee <> 0) AS with_pat "
                "FROM fee_schedules fs LEFT JOIN fee_schedule_entries e ON e.fee_schedule_id = fs.id "
                "GROUP BY fs.id"
            )
        )
    }

    updates: list[dict] = []
    report: dict[str, int] = defaultdict(int)
    changes: list[str] = []
    for row in db.execute(
        text("SELECT id, tenant_id, legacy_id, name, fee_type, pricing_model FROM fee_schedules ORDER BY id")
    ):
        key = (row.tenant_id, _s(row.legacy_id))
        if key in ucr_legacy:
            new_type = "ucr"
        elif row.legacy_id and key in feetype:
            new_type = fee_vocab.LEGACY_FEETYPE_MAP.get(feetype[key], fee_vocab.DEFAULT_FEE_TYPE)
        else:
            # API-created row: fold whatever the un-validated field holds.
            new_type = fee_vocab.canonical_fee_type(row.fee_type)

        with_ins, with_pat = shape.get(row.id, (0, 0))
        new_model = (
            "copay"
            if with_ins > with_pat and new_type in fee_vocab.COPAY_CAPABLE_FEE_TYPES
            else "percentage"
        )
        if new_type != row.fee_type or new_model != row.pricing_model:
            updates.append({"id": row.id, "fee_type": new_type, "pricing_model": new_model})
            report[f"{row.fee_type} -> {new_type}"] += 1
            if new_model != row.pricing_model:
                changes.append(
                    f"    schedule {row.id} '{row.name}': pricing_model "
                    f"{row.pricing_model} -> {new_model} ({with_ins} plan-pays vs {with_pat} patient fees)"
                )

    _apply(
        db,
        "UPDATE fee_schedules SET fee_type = :fee_type, pricing_model = :pricing_model WHERE id = :id",
        updates,
        apply=apply,
    )

    # Blank ``PATAMT`` became 0.00 in the import, and a 0.00 entry used to win the
    # resolver walk and post a $0 charge. Restore the distinction between "this
    # list does not price the code" (NULL) and "it is free" (``is_no_charge``).
    blanks: list[dict] = []
    for row in _read(root / "FeeScheD.txt"):
        if _s(row.get("PATAMT")):
            continue
        schedule_id = maps.schedule_id(row.get("PGID"), row.get("FEEID"))
        code = _s(row.get("CODE")) or _s(row.get("ADACODE"))
        if schedule_id and code:
            blanks.append({"fee_schedule_id": schedule_id, "procedure_code": code})
    blanked = 0
    if blanks:
        if apply:
            blanked = _apply_arrays(
                db,
                "UPDATE fee_schedule_entries AS t SET patient_fee = NULL "
                "FROM unnest(CAST(:sids AS integer[]), CAST(:codes AS text[])) AS d(sid, code) "
                "WHERE t.fee_schedule_id = d.sid AND t.procedure_code = d.code "
                "AND t.patient_fee = 0",
                {
                    "sids": [b["fee_schedule_id"] for b in blanks],
                    "codes": [b["procedure_code"] for b in blanks],
                },
                apply=True,
            )
        else:
            # Count what --apply would actually touch: blank at source *and* still
            # 0.00 here. Counting every zero row would overstate it.
            zero_now = {
                (r.fee_schedule_id, r.procedure_code)
                for r in db.execute(
                    text(
                        "SELECT fee_schedule_id, procedure_code FROM fee_schedule_entries "
                        "WHERE patient_fee = 0"
                    )
                )
            }
            blanked = sum(
                1 for b in blanks
                if (b["fee_schedule_id"], b["procedure_code"]) in zero_now
            )

    return {
        "fee_type / pricing_model rows updated": len(updates),
        "transitions": dict(report),
        "pricing_model changes": changes,
        "blank source fees un-zeroed (0.00 -> NULL)": blanked,
        "source rows with a blank PATAMT": len(blanks),
    }


# ── 2. offices: the UCR list and the default patient list ────────────────────


def section_offices(db: Session, root: Path, maps: Maps, *, apply: bool, overwrite: bool) -> dict:
    """``Office.FEEID`` is the UCR list; ``Office.PATIENTFEEID`` the patient default.

    When ``PATIENTFEEID`` is ``0`` the office has no separate self-pay list and
    Denticon falls back to ``FEEID``, so one list legitimately serves both roles
    (it does for 12 of 15 offices). Nothing is cloned to satisfy a type rule.
    """
    updates: list[dict] = []
    unresolved: list[str] = []
    managed_care: list[str] = []
    detail: list[str] = []
    names = {
        r.id: r.name
        for r in db.execute(text("SELECT id, name FROM fee_schedules"))
    }
    current = {
        r.id: (r.default_fee_schedule_id, r.default_ucr_fee_schedule_id)
        for r in db.execute(
            text("SELECT id, default_fee_schedule_id, default_ucr_fee_schedule_id FROM offices")
        )
    }

    for row in _read(root / "Office.txt"):
        tenant = maps.tenant(row.get("PGID"))
        office_id = maps.office.get((tenant, _s(row.get("OID")))) if tenant else None
        if not office_id:
            continue
        ucr = maps.schedule_id(row.get("PGID"), row.get("FEEID"))
        patient_list = maps.schedule_id(row.get("PGID"), row.get("PATIENTFEEID")) or ucr
        if _is_set(row.get("FEEID")) and not ucr:
            unresolved.append(f"office {office_id}: FEEID {_s(row.get('FEEID'))} matches no schedule")
        if _is_set(row.get("MANCAREFEEID")):
            # Denticon's managed-care list. Empty on every row in this export; if a
            # practice uses it, it needs a product decision (a third office pointer)
            # rather than a silent guess, so it is only reported.
            managed_care.append(
                f"office {office_id}: MANCAREFEEID {_s(row.get('MANCAREFEEID'))} (no column — reported only)"
            )
        have_default, have_ucr = current.get(office_id, (None, None))
        detail.append(
            f"    office {office_id:<3} UCR <- schedule {ucr} ({names.get(ucr, '?')}) | "
            f"default <- schedule {patient_list} ({names.get(patient_list, '?')})"
            + ("" if (have_ucr is None and have_default is None) else "  [already set]")
        )
        payload = {"id": office_id}
        if ucr and (overwrite or have_ucr is None):
            payload["ucr"] = ucr
        if patient_list and (overwrite or have_default is None):
            payload["default"] = patient_list
        if len(payload) > 1:
            updates.append(payload)

    applied = 0
    for payload in updates:
        sets = []
        if "ucr" in payload:
            sets.append("default_ucr_fee_schedule_id = :ucr")
        if "default" in payload:
            sets.append("default_fee_schedule_id = :default")
        if apply:
            db.execute(text(f"UPDATE offices SET {', '.join(sets)} WHERE id = :id"), payload)
        applied += 1

    return {
        "offices updated": applied,
        "pointers": detail,
        "unresolved FEEIDs": unresolved,
        "managed-care lists found": managed_care,
    }


# ── 3. patients: the list a patient is registered on ─────────────────────────


def section_patients(db: Session, root: Path, maps: Maps, *, apply: bool, overwrite: bool) -> dict:
    """``PATIENT.FEESCHEDULE`` — populated on 94 % of patients and the single best
    predictor of the posted fee (85 % exact on 2025 charges)."""
    by_legacy = {
        (r.tenant_id, _s(r.legacy_id)): (r.id, r.fee_schedule_id)
        for r in db.execute(
            text(
                "SELECT id, tenant_id, legacy_id, fee_schedule_id FROM patients "
                "WHERE legacy_id IS NOT NULL"
            )
        )
    }
    updates: list[dict] = []
    stats: dict[str, int] = defaultdict(int)
    for row in _read_many(root, "PATIENT", "Patient.txt"):
        tenant = maps.tenant(row.get("PGID"))
        found = by_legacy.get((tenant, _s(row.get("PATID")))) if tenant else None
        if not found:
            stats["source rows with no patient here"] += 1
            continue
        patient_id, existing = found
        if not _is_set(row.get("FEESCHEDULE")):
            stats["source rows with no fee schedule"] += 1
            continue
        schedule_id = maps.schedule_id(row.get("PGID"), row.get("FEESCHEDULE"))
        if not schedule_id:
            stats["fee schedule not found here"] += 1
            continue
        if existing is not None and not overwrite:
            stats["already set (kept)"] += 1
            continue
        if existing == schedule_id:
            stats["already correct"] += 1
            continue
        updates.append({"id": patient_id, "fee_schedule_id": schedule_id})

    _apply_arrays(
        db,
        "UPDATE patients AS t SET fee_schedule_id = d.fee_schedule_id "
        "FROM unnest(CAST(:ids AS integer[]), CAST(:fees AS integer[])) AS d(id, fee_schedule_id) "
        "WHERE t.id = d.id",
        {"ids": [u["id"] for u in updates], "fees": [u["fee_schedule_id"] for u in updates]},
        apply=apply,
    )
    return {"patients to set": len(updates), **stats}


# ── 4. carriers: fold the dead fee_id into a real assignment row ─────────────


def section_carriers(db: Session, maps: Maps, *, apply: bool) -> dict:
    """``insurance_carriers.fee_id`` is Denticon's "Assign To Carrier" binding.

    It holds a real ``fee_schedules.legacy_id`` on 13 carriers and has **zero
    readers** anywhere in the app. Binding belongs in one table, so each one
    becomes a carrier-keyed assignment. The column is left in place (read-only)
    until the pricing-health report shows nothing depends on it.
    """
    existing = {
        (r.tenant_id, r.carrier_id)
        for r in db.execute(
            text(
                "SELECT tenant_id, carrier_id FROM fee_schedule_assignments "
                "WHERE carrier_id IS NOT NULL AND ins_plan_id IS NULL "
                "AND provider_id IS NULL AND specialty_id IS NULL "
                "AND office_id IS NULL AND office_group_id IS NULL"
            )
        )
    }
    inserts: list[dict] = []
    unresolved: list[str] = []
    for row in db.execute(
        text(
            "SELECT c.id, c.tenant_id, c.name, c.fee_id FROM insurance_carriers c "
            "WHERE c.fee_id IS NOT NULL AND c.fee_id <> '' AND c.fee_id <> '0'"
        )
    ):
        schedule_id = maps.schedule.get((row.tenant_id, _s(row.fee_id)))
        if not schedule_id:
            unresolved.append(f"carrier {row.id} '{row.name}': fee_id {row.fee_id} matches no schedule")
            continue
        if (row.tenant_id, row.id) in existing:
            continue
        inserts.append(
            {
                "tenant_id": row.tenant_id,
                "carrier_id": row.id,
                "fee_schedule_id": schedule_id,
                # Keyed on the carrier, not the schedule: several carriers bind the
                # same schedule (e.g. carriers 236/248/259 all -> fee_id 110), so a
                # schedule-derived legacy_id collides on (tenant_id, legacy_id).
                # Idempotency is already handled by the ``existing`` (tenant, carrier)
                # set above, so per-carrier uniqueness is all this needs.
                "legacy_id": f"carrier:{row.id}",
            }
        )

    _apply(
        db,
        "INSERT INTO fee_schedule_assignments (tenant_id, carrier_id, fee_schedule_id, legacy_id) "
        "VALUES (:tenant_id, :carrier_id, :fee_schedule_id, :legacy_id)",
        inserts,
        apply=apply,
    )
    return {"carrier assignments to create": len(inserts), "unresolved fee_ids": unresolved}


# ── 5. entries: the alternate-benefit code ───────────────────────────────────


def section_entries(db: Session, root: Path, maps: Maps, *, apply: bool) -> dict:
    """``FeeScheD.AMBCODE`` — the code the carrier actually pays on (``D2391A`` ->
    ``D2140``: posterior composite downgraded to amalgam). 36 real rows across the
    PPO carrier lists, plus 3 junk values that are skipped."""
    junk = {"`", "78.00"}
    updates: list[dict] = []
    skipped: list[str] = []
    for row in _read(root / "FeeScheD.txt"):
        amb = _s(row.get("AMBCODE"))
        if not amb:
            continue
        if amb in junk:
            skipped.append(amb)
            continue
        schedule_id = maps.schedule_id(row.get("PGID"), row.get("FEEID"))
        code = _s(row.get("CODE")) or _s(row.get("ADACODE"))
        if schedule_id and code:
            updates.append(
                {"fee_schedule_id": schedule_id, "procedure_code": code, "amb_code": amb[:20]}
            )

    _apply_arrays(
        db,
        "UPDATE fee_schedule_entries AS t SET amb_code = d.amb_code "
        "FROM unnest(CAST(:sids AS integer[]), CAST(:codes AS text[]), CAST(:ambs AS text[])) "
        "AS d(sid, code, amb_code) "
        "WHERE t.fee_schedule_id = d.sid AND t.procedure_code = d.code",
        {
            "sids": [u["fee_schedule_id"] for u in updates],
            "codes": [u["procedure_code"] for u in updates],
            "ambs": [u["amb_code"] for u in updates],
        },
        apply=apply,
    )
    return {"entry amb_codes to set": len(updates), "junk values skipped": len(skipped)}


# ── 6. plans: the claim-printing and coordination fields ─────────────────────


def section_plans(db: Session, root: Path, maps: Maps, *, apply: bool) -> dict:
    """``PRINTOFFICEUCR`` is the legacy "Fees to Print on Claims" switch and it is
    genuinely used (0 on 3,907 of 31,328 plans). ``s07`` dropped it along with
    ``NETWORKTYPE``, ``PERVISITCOPAY`` and ``ISNONDUPBENEFITS``, so every one of
    those columns currently shows its default rather than the practice's data.

    ``ISPREPAID`` is stored raw only — see the module docstring.
    """
    network = {"U": "unknown", "I": "in_network", "O": "out_of_network"}
    by_legacy = {
        (r.tenant_id, _s(r.legacy_id)): r.id
        for r in db.execute(
            text("SELECT id, tenant_id, legacy_id FROM insurance_plans WHERE legacy_id IS NOT NULL")
        )
    }
    updates: list[dict] = []
    stats: dict[str, int] = defaultdict(int)
    for row in _read(root / "InsPlans.txt"):
        tenant = maps.tenant(row.get("PGID"))
        plan_id = by_legacy.get((tenant, _s(row.get("INSPLANID")))) if tenant else None
        if not plan_id:
            stats["source rows with no plan here"] += 1
            continue
        print_ucr = _s(row.get("PRINTOFFICEUCR"))
        copay = _money(row.get("PERVISITCOPAY"))
        updates.append(
            {
                "id": plan_id,
                # 1 -> print the office's UCR fees, 0 -> print the plan's fees. The
                # frontend also offers "carrier fees"; the source is binary, so a
                # migrated plan never lands on that third value by guesswork.
                "fees_to_print": "office_ucr" if print_ucr in ("1", "True", "true") else "plan_fees",
                "network_type": network.get(_s(row.get("NETWORKTYPE")).upper(), "unknown"),
                "per_visit_copay": copay if copay and copay > 0 else None,
                "is_non_dup": _s(row.get("ISNONDUPBENEFITS")) in ("1", "True", "true"),
                "legacy_prepaid_code": (_s(row.get("ISPREPAID")) or None),
            }
        )
        stats[f"fees_to_print={'office_ucr' if print_ucr in ('1', 'True', 'true') else 'plan_fees'}"] += 1

    _apply_arrays(
        db,
        "UPDATE insurance_plans AS t SET fees_to_print = d.fees_to_print, "
        "network_type = d.network_type, "
        # A plan the export gives no copay for keeps what it has: a silent export
        # is not the same as a zero copay.
        "per_visit_copay = COALESCE(d.per_visit_copay, t.per_visit_copay), "
        "is_non_dup_benefits = d.is_non_dup, legacy_prepaid_code = d.legacy_prepaid_code "
        "FROM unnest(CAST(:ids AS integer[]), CAST(:ftp AS text[]), CAST(:nt AS text[]), "
        "CAST(:copay AS numeric[]), CAST(:nondup AS boolean[]), CAST(:prepaid AS text[])) "
        "AS d(id, fees_to_print, network_type, per_visit_copay, is_non_dup, legacy_prepaid_code) "
        "WHERE t.id = d.id",
        {
            "ids": [u["id"] for u in updates],
            "ftp": [u["fees_to_print"] for u in updates],
            "nt": [u["network_type"] for u in updates],
            "copay": [u["per_visit_copay"] for u in updates],
            "nondup": [u["is_non_dup"] for u in updates],
            "prepaid": [u["legacy_prepaid_code"] for u in updates],
        },
        apply=apply,
    )
    return {"plans to update": len(updates), **stats}


# ── 7. patient insurance slots (gated: this one moves money) ─────────────────


def section_slots(
    db: Session, root: Path, maps: Maps, *,
    apply: bool, apply_deductibles: bool, apply_primary_changes: bool,
) -> dict:
    """Restore the legacy key, the secondary slots and the remaining balances.

    ``s19`` read three columns that do not exist in ``PatInsPlans.txt``:
    ``BILLINGORDER`` (the real discriminator is ``INSTYPE``, P/S), ``INDDEDUCTREM``
    (really ``INDDEDREM``) and ``ORTHOREMAINING`` (really ``INDORTHOREM``). So every
    slot became ``primary``, ``ON CONFLICT`` overwrote the 954 secondary rows, and
    the deductible the estimate engine consumes is ``0`` on 55,105 of 55,119 slots.

    Three separate decisions, three separate flags:

    * the ``legacy_id`` stamp is safe and unconditional (it is what makes any of
      this reconcilable);
    * ``--apply-deductibles`` changes future estimates — a stored ``0`` applies no
      deductible, while NULL falls back to the plan's (50.00 on 9,215 plans), so
      the patient's share rises on the first line of every affected quote;
    * ``--apply-primary-changes`` is needed when a slot that is ``primary`` here is
      ``INSTYPE='S'`` in the source, because demoting it changes which plan's
      coverage rules price that patient.
    """
    rows_by_patient: dict[int, list[dict]] = defaultdict(list)
    patients = {
        (r.tenant_id, _s(r.legacy_id)): r.id
        for r in db.execute(
            text("SELECT id, tenant_id, legacy_id FROM patients WHERE legacy_id IS NOT NULL")
        )
    }
    plans = {
        (r.tenant_id, _s(r.legacy_id)): r.id
        for r in db.execute(
            text("SELECT id, tenant_id, legacy_id FROM insurance_plans WHERE legacy_id IS NOT NULL")
        )
    }
    for row in _read_many(root, "PatInsPlans.txt"):
        tenant = maps.tenant(row.get("PGID"))
        patient_id = patients.get((tenant, _s(row.get("PATID")))) if tenant else None
        if not patient_id:
            continue
        rows_by_patient[patient_id].append(
            {
                "plan_type": _s(row.get("PLANTYPE")) or "D",
                "ins_type": "secondary" if _s(row.get("INSTYPE")).upper() == "S" else "primary",
                "ins_plan_id": plans.get((tenant, _s(row.get("INSPLANID")))) if tenant else None,
                "legacy_id": f"{_s(row.get('PATID'))}:{_s(row.get('PLANTYPE'))}:{_s(row.get('INSTYPE'))}",
                "ded": _money(row.get("INDDEDREM")),
                "ortho": _money(row.get("INDORTHOREM")),
                "max": _money(row.get("INDMAXREM")),
            }
        )

    stamps: list[dict] = []
    deductibles: list[dict] = []
    primary_changes: list[str] = []
    stats: dict[str, int] = defaultdict(int)

    current = defaultdict(list)
    for r in db.execute(
        text(
            "SELECT id, patient_id, ins_plan_id, legacy_plan_type, insurance_type, legacy_id, "
            "deductible_remaining, ortho_remaining FROM patient_insurance"
        )
    ):
        current[r.patient_id].append(r)

    for patient_id, source_rows in rows_by_patient.items():
        for source in source_rows:
            # Match on the plan, which is the only stable identity a slot has.
            match = next(
                (
                    slot for slot in current.get(patient_id, [])
                    if slot.ins_plan_id and slot.ins_plan_id == source["ins_plan_id"]
                ),
                None,
            )
            if match is None:
                stats["source slots with no row here (secondary slots s19 overwrote)"] += 1
                continue
            if match.legacy_id != source["legacy_id"]:
                stamps.append({"id": match.id, "legacy_id": source["legacy_id"]})
            if source["ins_type"] != (match.insurance_type or ""):
                primary_changes.append(
                    f"    slot {match.id} (patient {patient_id}, plan {match.ins_plan_id}): "
                    f"{match.insurance_type} -> {source['ins_type']}"
                )
            if source["ded"] is not None and source["ded"] != match.deductible_remaining:
                deductibles.append(
                    {
                        "id": match.id,
                        "ded": source["ded"] if source["ded"] > 0 else None,
                        "ortho": source["ortho"] if source["ortho"] and source["ortho"] > 0 else None,
                    }
                )

    _apply_arrays(
        db,
        "UPDATE patient_insurance AS t SET legacy_id = d.legacy_id "
        "FROM unnest(CAST(:ids AS integer[]), CAST(:legacy AS text[])) AS d(id, legacy_id) "
        "WHERE t.id = d.id",
        {"ids": [u["id"] for u in stamps], "legacy": [u["legacy_id"] for u in stamps]},
        apply=apply,
    )
    _apply_arrays(
        db,
        "UPDATE patient_insurance AS t SET deductible_remaining = d.ded, ortho_remaining = d.ortho "
        "FROM unnest(CAST(:ids AS integer[]), CAST(:deds AS numeric[]), CAST(:orthos AS numeric[])) "
        "AS d(id, ded, ortho) WHERE t.id = d.id",
        {
            "ids": [u["id"] for u in deductibles],
            "deds": [u["ded"] for u in deductibles],
            "orthos": [u["ortho"] for u in deductibles],
        },
        apply=apply and apply_deductibles,
    )
    return {
        "legacy_id stamps": len(stamps),
        "deductible / ortho rows": len(deductibles),
        "deductibles written": len(deductibles) if (apply and apply_deductibles) else 0,
        "slots whose primary/secondary would change": len(primary_changes),
        "primary changes (first 10)": primary_changes[:10],
        "primary changes written": 0 if not apply_primary_changes else len(primary_changes),
        **stats,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def _print_report(name: str, report: dict) -> None:
    print(f"\n-- {name} " + "-" * max(0, 60 - len(name)))
    for key, value in report.items():
        if isinstance(value, list):
            if not value:
                continue
            print(f"  {key}: {len(value)}")
            for line in value[:10]:
                print(f"    {line}" if not str(line).startswith("    ") else line)
            if len(value) > 10:
                print(f"    ... and {len(value) - 10} more")
        elif isinstance(value, dict):
            if value:
                print(f"  {key}:")
                for k, v in sorted(value.items()):
                    print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace office/patient pointers that are already set")
    parser.add_argument("--only", choices=SECTIONS, action="append",
                        help="run only these sections (repeatable)")
    parser.add_argument("--apply-deductibles", action="store_true",
                        help="slots: write INDDEDREM/INDORTHOREM — changes future estimates")
    parser.add_argument("--apply-primary-changes", action="store_true",
                        help="slots: allow a slot's primary/secondary rank to change")
    args = parser.parse_args()

    sections = tuple(args.only) if args.only else SECTIONS
    root = _source_root()
    db = SessionLocal()
    print(f"Denticon export: {root}")
    print(f"mode: {'APPLY' if args.apply else 'dry run (nothing is written)'}")
    print(f"sections: {', '.join(sections)}")

    try:
        maps = Maps(db)
        print(f"tenants by PGID: {maps.tenant_by_pgid} | schedules mapped: {len(maps.schedule)}")

        if "schedules" in sections:
            _print_report("schedules", section_schedules(db, root, maps, apply=args.apply))
        if "offices" in sections:
            _print_report("offices", section_offices(db, root, maps, apply=args.apply, overwrite=args.overwrite))
        if "patients" in sections:
            _print_report("patients", section_patients(db, root, maps, apply=args.apply, overwrite=args.overwrite))
        if "carriers" in sections:
            _print_report("carriers", section_carriers(db, maps, apply=args.apply))
        if "entries" in sections:
            _print_report("entries", section_entries(db, root, maps, apply=args.apply))
        if "plans" in sections:
            _print_report("plans", section_plans(db, root, maps, apply=args.apply))
        if "slots" in sections:
            _print_report(
                "slots",
                section_slots(
                    db, root, maps, apply=args.apply,
                    apply_deductibles=args.apply_deductibles,
                    apply_primary_changes=args.apply_primary_changes,
                ),
            )

        if args.apply:
            db.commit()
            print("\nCOMMITTED")
        else:
            db.rollback()
            print("\nnothing written (dry run) — re-run with --apply")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
