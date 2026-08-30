"""Repair the insurance columns the Denticon migration read under the wrong name.

Why every migrated plan has no group number (INS-PT-15)
-------------------------------------------------------
``s07_insurance_plans`` read ``row.get("GROUPNO")``. ``InsPlans.txt`` writes the
column as ``GROUPNUMBER``. ``.get`` on a missing key returns ``None``, so the
step inserted NULL for all 31,331 plans without ever failing — 8 rows hold a
group number today and every one of them was typed by hand during testing.

That single field is what the legacy "Search For = Group #" dialog keys on and
what **both** duplicate-prevention layers compare, so the feature was correct and
completely inert against production data.

The same mistake hit the benefit amounts, which is why ``family_max`` is the only
one with data — ``FAMILYMAX`` is the one name that happened to match:

====================  ==============================  =====================
Read as               Actually in InsPlans.txt        Rows non-zero (of 31,331)
====================  ==============================  =====================
``GROUPNO``           ``GROUPNUMBER``                 8
``INDMAX``/``INDIVMAX``   ``INDIVIDUALMAX``           4
``INDDED``/``INDIVDED``   ``INDIVIDUALDEDUCTIBLE``    2
``ORTHOMAX``          ``INDIVIDUALORTHOMAX``          3
``FAMDED``/``FAMILYDED``  ``FAMILYDEDUCTIBLE``        2
``FAMMAX``/``FAMILYMAX``  ``FAMILYMAX``               31,321
====================  ==============================  =====================

The maxima and deductibles are the read-only BENEFIT INFO panel on the patient
insurance screen, and they are inputs to the estimate engine — a plan with a
``0`` individual maximum prices as a plan with no benefit left.

Two more tables were losing columns the export does carry:

* ``insurance_subscribers`` — ``MSTATUS`` (INS-PT-1), ``SUBPHONE`` (INS-PT-2),
  ``SUBADDRESS2`` (INS-PT-4) and ``ELIGVERIFIEDON`` were never read, so the
  columns added for those gaps are empty on all 65,305 migrated rows and staff
  retype what the practice already exported.
* ``employers`` — ``ADDRESS2`` (INS-PT-11).

The migration steps are fixed too, so a re-run is correct; this script exists so
the live database does not need one.

Guards
------
By default only rows whose target is still NULL are written, so a value edited in
the app is never clobbered. The five plan money columns are the exception: the
migration wrote a literal ``0``, not NULL, so the NULL-guard can never fire on
them and they are treated as "empty" when NULL **or** zero. ``--overwrite``
forces every column.

``--group-from-subscribers`` is the fallback for a deployment with no access to
the Denticon export: ``insurance_subscribers.group_number`` was read correctly
(59,804 of 65,305 rows have one), and every subscriber row names its plan, so a
plan's group number can be recovered from its own subscribers. It is only applied
where the subscribers agree unanimously — a plan whose subscribers disagree is
reported and skipped, because guessing there would poison the duplicate check
this whole gap exists to make work.

Usage::

    python -m scripts.backfill_insurance_source_fields --dry-run
    python -m scripts.backfill_insurance_source_fields
    python -m scripts.backfill_insurance_source_fields --only plans --overwrite
    python -m scripts.backfill_insurance_source_fields --group-from-subscribers

Source files come from ``DATA_SOURCE_PATH`` (the same ``.env`` the migration
uses): ``InsPlans.txt``, ``RespInsplan.txt``, ``Employers.txt``.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import bindparam, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

TABLES = ("plans", "subscribers", "employers")
CHUNK = 5_000

#: target column -> (source column, pg cast, "zero counts as empty")
PLAN_FIELDS: dict[str, tuple[str, str, bool]] = {
    "group_number": ("GROUPNUMBER", "varchar", False),
    "individual_max": ("INDIVIDUALMAX", "numeric", True),
    "individual_deductible": ("INDIVIDUALDEDUCTIBLE", "numeric", True),
    "ortho_max": ("INDIVIDUALORTHOMAX", "numeric", True),
    "family_max": ("FAMILYMAX", "numeric", True),
    "family_deductible": ("FAMILYDEDUCTIBLE", "numeric", True),
    "created_on": ("CREATEDON", "timestamp", False),
    "created_by": ("CREATEDBY", "varchar", False),
    "modified_on": ("MODIFIEDON", "timestamp", False),
    "modified_by": ("MODIFIEDBY", "varchar", False),
}

SUBSCRIBER_FIELDS: dict[str, tuple[str, str, bool]] = {
    "marital_status": ("MSTATUS", "varchar", False),
    "sub_phone": ("SUBPHONE", "varchar", False),
    "sub_address2": ("SUBADDRESS2", "varchar", False),
    "elig_verified_on": ("ELIGVERIFIEDON", "timestamp", False),
}

EMPLOYER_FIELDS: dict[str, tuple[str, str, bool]] = {
    "address2": ("ADDRESS2", "varchar", False),
}

SPECS = {
    "plans": ("insurance_plans", "InsPlans.txt", "INSPLANID", PLAN_FIELDS),
    "subscribers": ("insurance_subscribers", "RespInsplan.txt", "RESPPLANID", SUBSCRIBER_FIELDS),
    "employers": ("employers", "Employers.txt", "EMPID", EMPLOYER_FIELDS),
}


def _source_root() -> Path:
    # DATA_SOURCE_PATH lives in .env alongside the DB settings but is a migration
    # concern, so it is not on the app Settings model.
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    except ImportError:  # pragma: no cover - python-dotenv ships with the app
        pass
    raw = os.environ.get("DATA_SOURCE_PATH") or getattr(settings, "DATA_SOURCE_PATH", "")
    if not raw:
        raise SystemExit(
            "DATA_SOURCE_PATH is not set — point it at the Denticon export folder, "
            "or run with --group-from-subscribers, which needs no source files."
        )
    root = Path(raw)
    if not root.exists():
        raise SystemExit(f"DATA_SOURCE_PATH does not exist: {root}")
    return root


def _read(path: Path):
    """Yield each row as a dict. Mirrors ``migration.utils.reader`` (cp1252,
    quoted CSV, blank trailing rows skipped) without importing the migration
    package, so this runs from a plain backend checkout."""
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


def _parse_datetime(value: str):
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _parse_decimal(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    # A zero in the export means "no maximum recorded", which is what the column
    # already holds — writing it back would be a no-op that hides the real count.
    return parsed or None


def _coerce(raw: str, cast: str):
    if cast == "numeric":
        return _parse_decimal(raw)
    if cast == "timestamp":
        return _parse_datetime(raw)
    value = (raw or "").strip()
    return value or None


def _legacy_ids(db, table: str) -> dict[str, int]:
    rows = db.execute(
        text(f"SELECT id, legacy_id FROM {table} WHERE legacy_id IS NOT NULL")
    ).all()
    return {str(legacy).strip(): pk for pk, legacy in rows}


def _apply(db, table: str, column: str, cast: str, zero_is_empty: bool,
           updates: list[tuple], *, dry_run: bool, overwrite: bool) -> int:
    """One UPDATE … FROM (VALUES …) per chunk — a per-row UPDATE over 65k
    subscriber rows is minutes; this is seconds."""
    if not updates:
        return 0
    if overwrite:
        guard = ""
    elif zero_is_empty:
        # The migration wrote 0, not NULL, so a NULL-only guard never fires here.
        guard = f" AND (t.{column} IS NULL OR t.{column} = 0)"
    else:
        guard = f" AND t.{column} IS NULL"

    written = 0
    for start in range(0, len(updates), CHUNK):
        chunk = updates[start:start + CHUNK]
        if dry_run:
            # Count what the guard would actually let through, not how many
            # values the export offers — most family_max rows already have one,
            # and reporting the offer as the write would overstate the repair.
            written += db.execute(
                text(f"SELECT count(*) FROM {table} AS t WHERE t.id IN :ids{guard}").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": [row_id for row_id, _ in chunk]},
            ).scalar_one()
            continue
        values = ", ".join(f"(:id{i}, :val{i})" for i in range(len(chunk)))
        params: dict = {}
        for i, (row_id, value) in enumerate(chunk):
            params[f"id{i}"] = row_id
            params[f"val{i}"] = value
        result = db.execute(
            text(
                f"UPDATE {table} AS t SET {column} = v.val::{cast} "
                f"FROM (VALUES {values}) AS v(id, val) WHERE t.id = v.id{guard}"
            ),
            params,
        )
        written += result.rowcount or 0
        db.commit()
    return written


def _backfill_from_file(db, key: str, root: Path, *, dry_run: bool, overwrite: bool,
                        only_fields: set[str] | None) -> None:
    table, filename, id_column, fields = SPECS[key]
    path = root / filename
    if not path.exists():
        print(f"{key}: {filename} not found under {root} — skipped")
        return

    ids = _legacy_ids(db, table)
    wanted = {c: spec for c, spec in fields.items() if not only_fields or c in only_fields}
    if not wanted:
        return

    updates: dict[str, list[tuple]] = {c: [] for c in wanted}
    seen = unmatched = 0
    for row in _read(path):
        legacy = (row.get(id_column) or "").strip()
        if not legacy:
            continue
        seen += 1
        row_id = ids.get(legacy)
        if row_id is None:
            unmatched += 1
            continue
        for column, (source, cast, _zero) in wanted.items():
            value = _coerce(row.get(source, ""), cast)
            if value is not None:
                updates[column].append((row_id, value))

    print(f"\n{key}: {seen:,} source rows, {len(ids):,} migrated rows"
          + (f", {unmatched:,} source rows have no migrated row" if unmatched else ""))
    for column, (_source, cast, zero_is_empty) in wanted.items():
        pending = updates[column]
        written = _apply(db, table, column, cast, zero_is_empty, pending,
                         dry_run=dry_run, overwrite=overwrite)
        verb = "would fill" if dry_run else "filled"
        print(f"  {column:<24} {len(pending):>7,} values in export, {verb} {written:,}")


def _group_from_subscribers(db, *, dry_run: bool, overwrite: bool) -> None:
    """Recover ``insurance_plans.group_number`` from the plan's own subscribers.

    ``s18`` read ``GROUPNO`` from ``RespInsplan.txt`` — where that *is* the column
    name — so the subscriber side survived intact. Only unanimous plans are
    written: if a plan's subscribers hold two different group numbers, picking one
    would feed the duplicate check a value nobody entered.
    """
    guard = "" if overwrite else " AND p.group_number IS NULL"
    rows = db.execute(text(f"""
        SELECT s.ins_plan_id,
               COUNT(DISTINCT btrim(s.group_number)) AS variants,
               MIN(btrim(s.group_number))            AS value
          FROM insurance_subscribers s
          JOIN insurance_plans p ON p.id = s.ins_plan_id
         WHERE s.group_number IS NOT NULL
           AND btrim(s.group_number) <> ''
           {guard}
         GROUP BY s.ins_plan_id
    """)).all()

    unanimous = [(plan_id, value) for plan_id, variants, value in rows if variants == 1]
    conflicted = len(rows) - len(unanimous)
    written = _apply(db, "insurance_plans", "group_number", "varchar", False,
                     unanimous, dry_run=dry_run, overwrite=overwrite)
    verb = "would write" if dry_run else "wrote"
    print(f"\nplan group_number from subscribers: {len(unanimous):,} unanimous, "
          f"{conflicted:,} skipped (subscribers disagree), {verb} {written:,}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    parser.add_argument("--overwrite", action="store_true",
                        help="also rewrite rows whose target column already holds a value")
    parser.add_argument("--only", choices=TABLES, action="append",
                        help="restrict to one table (repeatable); default: all three")
    parser.add_argument("--field", action="append",
                        help="restrict to one target column (repeatable)")
    parser.add_argument("--group-from-subscribers", action="store_true",
                        help=("recover plan group numbers from insurance_subscribers "
                              "instead of the export — needs no source files"))
    args = parser.parse_args()

    wanted_tables = set(args.only or TABLES)
    only_fields = set(args.field) if args.field else None

    db = SessionLocal()
    try:
        if args.group_from_subscribers:
            _group_from_subscribers(db, dry_run=args.dry_run, overwrite=args.overwrite)
        else:
            root = _source_root()
            print(f"source: {root}")
            for key in TABLES:
                if key in wanted_tables:
                    _backfill_from_file(db, key, root, dry_run=args.dry_run,
                                        overwrite=args.overwrite, only_fields=only_fields)
        if args.dry_run:
            print("\nDry run — nothing written.")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
