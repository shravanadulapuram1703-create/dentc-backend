"""RP-14: import Denticon guarantors (``RespParty.txt``) and resolve migrated accounts.

Migrated patients carry their Denticon ``RPID`` in ``patients.responsible_party_id``
and the account backfill (Alembic ``9435491c1d19``) grouped them into one
``accounts`` row per RPID — but the guarantor itself was never imported, so an
account with no member marked ``S`` (Self) stays *unresolved*. This script:

1. upserts each ``RespParty.txt`` row into ``responsible_parties`` keyed by
   ``(tenant_id, legacy_id = RPID)`` — insert-only; an existing row is never
   overwritten (it may have been edited in the app);
2. fills ``patients.responsible_party_relationship`` from ``PATIENT/*.txt``
   ``RELTORESP`` where it is still NULL (folded to the ``resp_party_rel`` code,
   RP-15) — ``s17`` never carried that column;
3. resolves every still-unresolved legacy account: the ``S`` member becomes the
   primary guarantor (and every member's ``guarantor_patient_id``), otherwise the
   imported RP row (``guarantor_party_id``); account billing flags are seeded
   from the RP row.

    python -m scripts.import_legacy_responsible_parties                  # dry run
    python -m scripts.import_legacy_responsible_parties --apply
    python -m scripts.import_legacy_responsible_parties --source-dir "F:\\...\\Data Migration"

Tenants resolve by ``tenants.legacy_id = PGID``, offices by ``offices.legacy_id = OID``.
Dry run (default) does everything inside a transaction and rolls it back.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.patient_rules_service import normalize_resp_party_relationship

DEFAULT_SOURCE = os.environ.get(
    "DATA_SOURCE_PATH", r"F:\Recon Dental Data\Data Migration\Data Migration")


def _rows(path: Path):
    raw = path.read_bytes().replace(b"\x00", b"")
    yield from csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))


def _clean(v):
    v = (v or "").strip()
    return v or None


def _bool(v):
    return (v or "").strip().lower() in ("true", "1", "y", "yes")


def _date(v):
    v = (v or "").strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def run(source: Path, apply: bool) -> dict:
    db = SessionLocal()
    conn = db.connection()
    stats = {"rp_rows": 0, "rp_inserted": 0, "rp_skipped_existing": 0, "rp_no_tenant": 0,
             "relationships_filled": 0, "accounts_resolved_patient": 0,
             "accounts_resolved_party": 0, "accounts_still_unresolved": 0}
    try:
        tenants = dict(conn.execute(text(
            "SELECT legacy_id, id FROM tenants WHERE legacy_id IS NOT NULL")).all())
        offices = {(t, lid): oid for oid, t, lid in conn.execute(text(
            "SELECT id, tenant_id, legacy_id FROM offices WHERE legacy_id IS NOT NULL")).all()}
        existing = {(t, lid) for t, lid in conn.execute(text(
            "SELECT tenant_id, legacy_id FROM responsible_parties WHERE legacy_id IS NOT NULL")).all()}

        rp_file = source / "RespParty.txt"
        for r in _rows(rp_file):
            stats["rp_rows"] += 1
            rpid = _clean(r.get("RPID"))
            tid = tenants.get(_clean(r.get("PGID")) or "")
            if not rpid:
                continue
            if tid is None:
                stats["rp_no_tenant"] += 1
                continue
            if (tid, rpid) in existing:
                stats["rp_skipped_existing"] += 1
                continue
            existing.add((tid, rpid))
            conn.execute(text("""
                INSERT INTO responsible_parties (
                    tenant_id, legacy_id, home_office_id, title, preferred_name, first_name,
                    last_name, middle_initial, address_line1, address_line2, city, state, zip,
                    email, dob, marital_status, sex, ssn, driver_license, home_phone, cell_phone,
                    work_phone, resp_party_type, send_statements, no_email_statement,
                    send_collections, is_finance_charge, statement_message,
                    statement_message_print_count, is_active, created_at)
                VALUES (:tid, :rpid, :office, :title, :nick, :fn, :ln, :mi, :a1, :a2, :city,
                        :state, :zip, :email, :dob, :ms, :sex, :ssn, :dl, :hp, :cp, :wp, :rtype,
                        :stmt, :noemail, :coll, :fin, :msg, :ptimes, TRUE, now())
            """), {
                "tid": tid, "rpid": rpid[:20],
                "office": offices.get((tid, _clean(r.get("OID")))),
                "title": _clean(r.get("TITLE")), "nick": _clean(r.get("NICKNAME")),
                "fn": _clean(r.get("FNAME")), "ln": _clean(r.get("LNAME")),
                "mi": (_clean(r.get("MI")) or "")[:10] or None,
                "a1": _clean(r.get("ADDRESS")), "a2": _clean(r.get("ADDRESS2")),
                "city": _clean(r.get("CITY")), "state": _clean(r.get("STATE")),
                "zip": _clean(r.get("ZIP")), "email": _clean(r.get("EMAIL")),
                "dob": _date(r.get("BIRTHDATE")), "ms": _clean(r.get("MSTATUS")),
                "sex": _clean(r.get("SEX")), "ssn": _clean(r.get("SSN")),
                "dl": _clean(r.get("DRVLICNO")), "hp": _clean(r.get("HOMEPHONE")),
                "cp": _clean(r.get("CELLPHONE")), "wp": _clean(r.get("WORKPHONE")),
                "rtype": (_clean(r.get("RESPTYPE")) or "")[:20] or None,
                "stmt": _bool(r.get("ISSENDSTMT")) or not _bool(r.get("NOEMAILSTMT")),
                "noemail": _bool(r.get("NOEMAILSTMT")), "coll": _bool(r.get("ISSENDCOLL")),
                "fin": _bool(r.get("ISFINCHARGE")), "msg": _clean(r.get("STMTMSG")),
                "ptimes": int(r["PRINTTIMES"]) if (r.get("PRINTTIMES") or "").strip().isdigit() else None,
            })
            stats["rp_inserted"] += 1

        patient_dir = source / "PATIENT"
        if patient_dir.is_dir():
            pending: list[dict] = []
            for f in sorted(patient_dir.glob("*.txt")):
                for r in _rows(f):
                    rel = normalize_resp_party_relationship(_clean(r.get("RELTORESP")))
                    patid = _clean(r.get("PATID"))
                    if rel and patid:
                        pending.append({"pid": patid, "rel": str(rel)[:50]})
            for i in range(0, len(pending), 5000):
                res = conn.execute(text("""
                    UPDATE patients SET responsible_party_relationship = :rel
                    WHERE legacy_id = :pid AND NULLIF(btrim(responsible_party_relationship), '') IS NULL
                """), pending[i:i + 5000])
                stats["relationships_filled"] += res.rowcount or 0

        # Resolve unresolved legacy accounts: Self member first, then the RP row.
        res = conn.execute(text("""
            WITH s AS (
                SELECT p.account_id, MIN(p.id) AS pid FROM patients p
                JOIN accounts a ON a.id = p.account_id
                WHERE a.legacy_key IS NOT NULL AND a.primary_guarantor_patient_id IS NULL
                  AND a.primary_guarantor_party_id IS NULL
                  AND upper(btrim(p.responsible_party_relationship)) = 'S'
                GROUP BY p.account_id)
            UPDATE accounts a SET primary_guarantor_patient_id = s.pid FROM s WHERE a.id = s.account_id
        """))
        stats["accounts_resolved_patient"] = res.rowcount or 0
        res = conn.execute(text("""
            UPDATE accounts a SET primary_guarantor_party_id = r.id,
                send_statements = r.send_statements, no_email_statement = r.no_email_statement,
                send_collections = r.send_collections, is_finance_charge = r.is_finance_charge,
                statement_message = COALESCE(a.statement_message, r.statement_message),
                home_office_id = COALESCE(a.home_office_id, r.home_office_id)
            FROM (SELECT tenant_id, legacy_id, MIN(id) AS id, bool_or(send_statements) AS send_statements,
                         bool_or(no_email_statement) AS no_email_statement,
                         bool_or(send_collections) AS send_collections,
                         bool_or(is_finance_charge) AS is_finance_charge,
                         MIN(statement_message) AS statement_message, MIN(home_office_id) AS home_office_id
                  FROM responsible_parties WHERE legacy_id IS NOT NULL GROUP BY tenant_id, legacy_id) r
            WHERE a.legacy_key IS NOT NULL AND a.primary_guarantor_patient_id IS NULL
              AND a.primary_guarantor_party_id IS NULL
              AND r.tenant_id = a.tenant_id AND r.legacy_id = a.legacy_key
        """))
        stats["accounts_resolved_party"] = res.rowcount or 0
        conn.execute(text("""
            UPDATE patients p SET guarantor_patient_id = a.primary_guarantor_patient_id
            FROM accounts a
            WHERE a.id = p.account_id AND a.primary_guarantor_patient_id IS NOT NULL
              AND p.guarantor_patient_id IS NULL AND p.guarantor_party_id IS NULL
        """))
        conn.execute(text("""
            UPDATE patients p SET guarantor_party_id = a.primary_guarantor_party_id
            FROM accounts a
            WHERE a.id = p.account_id AND a.primary_guarantor_party_id IS NOT NULL
              AND p.guarantor_patient_id IS NULL AND p.guarantor_party_id IS NULL
        """))
        stats["accounts_still_unresolved"] = conn.execute(text("""
            SELECT count(*) FROM accounts WHERE legacy_key IS NOT NULL AND is_active
              AND primary_guarantor_patient_id IS NULL AND primary_guarantor_party_id IS NULL
        """)).scalar()
        if apply:
            db.commit()
        else:
            db.rollback()
    finally:
        db.close()
    stats["applied"] = apply
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-dir", default=DEFAULT_SOURCE)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    for k, v in run(Path(args.source_dir), args.apply).items():
        print(f"{k:32} {v}")


if __name__ == "__main__":
    main()
