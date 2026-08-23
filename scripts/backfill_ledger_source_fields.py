"""Backfill the ledger columns the Denticon migration dropped (AL-6 / AL-10).

The account ledger renders four columns straight from the source export that
``s28_patient_procedures`` / ``s29_patient_payments`` never carried across:

===================  ==========================  ==================================
Source column        Target                      Ledger column it drives
===================  ==========================  ==================================
``CREATEDBY``        ``created_by`` (FK) +       **User** — who posted the
                     ``created_by_legacy``       transaction (AL-10)
``CREATEDON``        ``created_at``              row timestamp / audit (AL-10) —
                                                 needs ``--restore-created-at``
``DURATION``         ``duration_minutes``        **Durati…** (AL-6)
``CLAIMID``          ``claim_id``                **N** / ``unbilled`` (AL-6)
``PATPAID``          ``pat_paid``                Pat Paid / Outstanding (AL-15)
``PATADJUST``        ``pat_adjust``              Pat Adj / Outstanding (AL-15)
===================  ==========================  ==================================

``PATPAID``/``PATADJUST`` matter more than they look. The per-procedure roll-ups
behind ``/patient-procedures/{id}/allocations-summary`` were always ``0`` because
``payment_allocations`` cannot supply them — the Denticon allocation export holds
6,951 rows for 1.33M payments and **every ``AMOUNT`` in it is ``0.0000``** (AL-16).
These two columns are the only surviving record of what was applied to a charge.

``CLAIMID`` is the load-bearing one: ``unbilled`` is derived from "this procedure
has no ``claim_id``", and because the column was never populated, *every*
migrated procedure reported ``unbilled: true`` — including ones long since paid —
so the ledger's ``Prn`` column offered them all up for a new claim.

``CREATEDBY`` is a Denticon login string (``SHORTID``). Where that login still has
a ``users`` row it becomes the ``created_by`` FK; the raw string is stored either
way, so the User column reads for staff who left before the migration.

Idempotent: re-running rewrites the same values. By default only rows whose target
is still NULL are touched, so a value edited in the app is never clobbered — pass
``--overwrite`` to force.

``created_at`` is the exception: the column is ``NOT NULL DEFAULT now()``, so every
migrated row already holds the *migration run* timestamp rather than when the
transaction was actually posted, and the NULL-guard can never fire on it. Restoring
the real ``CREATEDON`` therefore means overwriting — a separate, explicit
``--restore-created-at`` flag, so the ordinary run stays conservative.

Usage::

    python -m scripts.backfill_ledger_source_fields --dry-run
    python -m scripts.backfill_ledger_source_fields
    python -m scripts.backfill_ledger_source_fields --only claim_id --overwrite

Source files come from ``DATA_SOURCE_PATH`` (the same ``.env`` the migration uses):
``LEDGER/*.txt`` plus ``Ledger_archive.txt``.
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

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402

FIELDS = ("created_by", "duration_minutes", "claim_id", "pat_amounts")
CHUNK = 5_000


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
            "DATA_SOURCE_PATH is not set — point it at the Denticon export folder."
        )
    root = Path(raw)
    if not root.exists():
        raise SystemExit(f"DATA_SOURCE_PATH does not exist: {root}")
    return root


def _ledger_files(root: Path) -> list[Path]:
    files: list[Path] = []
    folder = root / "LEDGER"
    if folder.exists():
        files.extend(sorted(folder.glob("*.txt")))
    archive = root / "Ledger_archive.txt"
    if archive.exists():
        files.append(archive)
    if not files:
        raise SystemExit(f"No LEDGER/*.txt or Ledger_archive.txt under {root}")
    return files


def _read(path: Path):
    """Yield each row as a dict. Mirrors ``migration.utils.reader`` (cp1252, quoted
    CSV, blank trailing rows skipped) without importing the migration package, so
    this script runs from a plain backend checkout."""
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
        return Decimal(value)
    except InvalidOperation:
        return None


def _parse_int(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _user_map(db) -> dict[str, int]:
    """Denticon login -> users.id, keyed case-insensitively on legacy_id, short_id
    and username (the export is not consistent about which one it writes)."""
    out: dict[str, int] = {}
    rows = db.execute(text("SELECT id, legacy_id, short_id, username FROM users")).all()
    for uid, legacy_id, short_id, username in rows:
        for key in (legacy_id, short_id, username):
            if key:
                out.setdefault(str(key).strip().lower(), uid)
    return out


def _claim_ids(db) -> set[str]:
    return {r[0] for r in db.execute(text("SELECT id FROM insurance_claims")).all()}


def _apply(  # noqa: ANN001
    db, table: str, column: str, updates: list[tuple], dry_run: bool, overwrite: bool
) -> int:
    """One UPDATE … FROM (VALUES …) per chunk — a per-row UPDATE over 1.3M ledger
    rows is hours; this is minutes."""
    if not updates:
        return 0
    guard = "" if overwrite else f" AND t.{column} IS NULL"
    written = 0
    for start in range(0, len(updates), CHUNK):
        chunk = updates[start:start + CHUNK]
        if dry_run:
            written += len(chunk)
            continue
        values = ", ".join(f"(:id{i}, :val{i})" for i in range(len(chunk)))
        params = {}
        for i, (row_id, value) in enumerate(chunk):
            params[f"id{i}"] = row_id
            params[f"val{i}"] = value
        cast = {
            "created_by": "integer", "duration_minutes": "integer",
            "claim_id": "varchar", "created_by_legacy": "varchar",
            "created_at": "timestamp",
            "pat_paid": "numeric", "pat_adjust": "numeric",
        }[column]
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="also rewrite rows whose target column is already set",
    )
    parser.add_argument(
        "--only", choices=FIELDS, action="append",
        help="restrict to one field (repeatable); default: all",
    )
    parser.add_argument(
        "--restore-created-at", action="store_true",
        help=(
            "overwrite created_at with the source CREATEDON. The column is NOT NULL "
            "DEFAULT now(), so migrated rows currently carry the migration run date, "
            "not the posting date — this is the only way to recover it"
        ),
    )
    args = parser.parse_args()
    wanted = set(args.only or FIELDS)

    root = _source_root()
    files = _ledger_files(root)

    # Read the lookups, then drop the connection: scanning 2.8M ledger rows takes
    # minutes and a session held open across it gets reaped by the server ("SSL
    # connection has been closed unexpectedly") right when the writes start.
    lookup_db = SessionLocal()
    try:
        users = _user_map(lookup_db)
        claims = _claim_ids(lookup_db) if "claim_id" in wanted else set()
    finally:
        lookup_db.close()

    db = SessionLocal()
    try:
        print(f"source: {root}  ({len(files)} file(s))")
        print(f"users:  {len(users)} login keys   claims: {len(claims)}")

        proc_user: list[tuple] = []
        proc_user_legacy: list[tuple] = []
        proc_created_at: list[tuple] = []
        proc_duration: list[tuple] = []
        proc_claim: list[tuple] = []
        proc_pat_paid: list[tuple] = []
        proc_pat_adjust: list[tuple] = []
        pay_user: list[tuple] = []
        pay_user_legacy: list[tuple] = []
        pay_created_at: list[tuple] = []
        seen = unresolved_logins = missing_claims = 0

        for path in files:
            for row in _read(path):
                ledger_id = (row.get("LEDGERID") or "").strip()
                if not ledger_id:
                    continue
                ltype = (row.get("LTYPE") or "").strip()
                if ltype == "C":
                    table_id, is_proc = f"PROC-{ledger_id}", True
                elif ltype in ("P", "I", "A"):
                    table_id, is_proc = f"PAY-{ledger_id}", False
                else:
                    continue
                seen += 1

                if "created_by" in wanted:
                    login = (row.get("CREATEDBY") or "").strip()
                    if login:
                        uid = users.get(login.lower())
                        if uid is None:
                            unresolved_logins += 1
                        target_u = proc_user if is_proc else pay_user
                        target_l = proc_user_legacy if is_proc else pay_user_legacy
                        if uid is not None:
                            target_u.append((table_id, uid))
                        target_l.append((table_id, login))
                    created_on = _parse_datetime(row.get("CREATEDON") or "")
                    if created_on is not None:
                        (proc_created_at if is_proc else pay_created_at).append(
                            (table_id, created_on)
                        )

                if not is_proc:
                    continue
                if "duration_minutes" in wanted:
                    minutes = _parse_int(row.get("DURATION") or "")
                    if minutes:  # 0 in the export means "not recorded", not "0 min"
                        proc_duration.append((table_id, minutes))
                if "pat_amounts" in wanted:
                    paid = _parse_decimal(row.get("PATPAID") or "")
                    if paid:
                        proc_pat_paid.append((table_id, paid))
                    adjust = _parse_decimal(row.get("PATADJUST") or "")
                    if adjust:
                        proc_pat_adjust.append((table_id, adjust))
                if "claim_id" in wanted:
                    raw_claim = (row.get("CLAIMID") or "").strip()
                    if raw_claim:
                        claim_pk = f"CLM-{raw_claim}"
                        if claim_pk in claims:
                            proc_claim.append((table_id, claim_pk))
                        else:
                            # A claim the CLAIMH export never carried. Leaving
                            # claim_id NULL is safer than an unresolvable FK.
                            missing_claims += 1

        print(f"ledger rows scanned: {seen:,}")
        if unresolved_logins:
            print(
                f"  {unresolved_logins:,} rows name a login with no users row — "
                "created_by_legacy still records it (AL-10)"
            )
        if missing_claims:
            print(
                f"  {missing_claims:,} rows name a CLAIMID absent from "
                "insurance_claims — skipped"
            )

        # Reconnect: the scan above ran long enough to have idled the session out.
        db.close()
        db = SessionLocal()

        plan = [
            ("patient_procedures", "created_by", proc_user, False),
            ("patient_procedures", "created_by_legacy", proc_user_legacy, False),
            ("patient_procedures", "duration_minutes", proc_duration, False),
            ("patient_procedures", "claim_id", proc_claim, False),
            ("patient_procedures", "pat_paid", proc_pat_paid, False),
            ("patient_procedures", "pat_adjust", proc_pat_adjust, False),
            ("patient_payments", "created_by", pay_user, False),
            ("patient_payments", "created_by_legacy", pay_user_legacy, False),
        ]
        if args.restore_created_at:
            plan += [
                ("patient_procedures", "created_at", proc_created_at, True),
                ("patient_payments", "created_at", pay_created_at, True),
            ]
        elif proc_created_at or pay_created_at:
            print(
                f"  created_at: {len(proc_created_at) + len(pay_created_at):,} source "
                "timestamps read but NOT written — the column is NOT NULL DEFAULT now() "
                "and holds the migration date; pass --restore-created-at to overwrite it"
            )
        for table, column, updates, force in plan:
            written = _apply(
                db, table, column, updates, args.dry_run, args.overwrite or force
            )
            verb = "would update" if args.dry_run else "updated"
            print(
                f"  {table}.{column}: {verb} {written:,} row(s) "
                f"(from {len(updates):,} candidates)",
                flush=True,
            )

        if args.dry_run:
            print("dry run — nothing written")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
