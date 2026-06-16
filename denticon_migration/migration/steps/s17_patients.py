"""
STEP 17 — patients
Source: PATIENT/*.txt  (the real patient records, keyed by PATID)
        + RespParty.txt (guarantor/account-level financial fields, joined via RPID)

Denticon model: every PATIENT belongs to a responsible party (RPID). The PATIENT
row carries demographics + clinical fields; the RespParty row carries the
account-level billing flags (finance charge, statements, collections, locked).

This step migrates ALL PATIENT rows as patients keyed by their PATID, so that
the ledger / appointments / clinical tables — which reference PATID — resolve to
the correct person. (The previous version loaded RespParty as patients keyed by
RPID, which left dependents missing and mis-linked ~98% of ledger rows.)

Returns:
  patient_map     : { patid_str : patient_db_id }   — for PATID-keyed steps
Also sets in `maps`:
  rp_patient_map  : { rpid_str  : patient_db_id }   — guarantor's primary patient,
                    for account-level steps keyed by the responsible party
                    (account_notes, insurance_subscribers).
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file, read_folder
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_date, parse_bool, map_gender

COLS = [
    "tenant_id", "home_office_id", "legacy_id", "chart_no",
    "first_name", "last_name", "preferred_name", "title", "middle_initial",
    "dob", "gender", "ssn", "marital_status",
    "phone", "cell_phone", "work_phone", "email", "preferred_contact",
    "address_line1", "address_line2", "city", "state", "zip",
    "is_finance_charge", "send_statements", "send_collections",
    "no_auto_email", "is_locked", "hipaa_agreement",
    "guardian_name", "guardian_phone", "referral_type", "referred_by",
    "patient_notes", "responsible_party_id", "is_active", "patient_type", "medicaid_id",
]

# Default guarantor financial flags when a patient's RPID has no RespParty row:
# (is_finance_charge, send_statements, send_collections, is_locked)
_DEFAULT_FIN = (False, True, False, False)


def _patid_sort_key(patid: str) -> tuple:
    """Sort PATIDs numerically when possible, else lexically."""
    return (0, int(patid)) if patid.isdigit() else (1, patid)


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    office_map = maps["office_map"]
    default_tid = next(iter(tenant_map.values()))

    # ── 1. Guarantor financial flags from RespParty (joined via RPID) ──────────
    rp_fin: dict[str, tuple] = {}
    for r in read_denticon_file(cfg.src("RespParty.txt"), apply_limit=False):
        rid = (r.get("RPID") or "").strip()
        if not rid:
            continue
        rp_fin[rid] = (
            parse_bool(r.get("ISFINCHARGE", "False")),
            not parse_bool(r.get("NOEMAILSTMT", "False")),  # NOEMAILSTMT=True → no stmt
            parse_bool(r.get("ISSENDCOLL", "False")),
            parse_bool(r.get("ISLOCKED", "False")),
        )

    # ── 2. Insert all PATIENT rows keyed by PATID ──────────────────────────────
    skipped = 0
    # Per-account representative patient: prefer a self ('S') patient, else lowest PATID.
    rp_best: dict[str, tuple] = {}   # rpid -> (rank, patid_sort_key, patid)

    buf = BulkBuffer(
        conn, "patients", COLS,
        conflict=(
            "ON CONFLICT (legacy_id) DO UPDATE SET "
            "first_name = EXCLUDED.first_name, "
            "last_name = EXCLUDED.last_name, "
            "email = EXCLUDED.email, "
            "responsible_party_id = EXCLUDED.responsible_party_id, "
            "updated_at = NOW()"
        ),
        returning="id, legacy_id",
        dedup_index=COLS.index("legacy_id"),
        flush_every=10000, page_size=2000, label="patients",
    )

    for row in read_folder(cfg.src("PATIENT")):
        patid = (row.get("PATID") or "").strip()
        if not patid:
            skipped += 1
            continue

        rpid = (row.get("RPID") or "").strip()
        pgid = (row.get("PGID") or "").strip()
        oid  = (row.get("OID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)
        fin  = rp_fin.get(rpid, _DEFAULT_FIN)

        buf.add((
            tid, office_map.get(oid), patid,
            clean(row.get("CHARTNO")),
            clean(row.get("FNAME")), clean(row.get("LNAME")),
            clean(row.get("NICKNAME")), clean(row.get("TITLE")), clean(row.get("MI")),
            parse_date(row.get("BIRTHDATE") or ""),
            map_gender(row.get("SEX") or ""),
            clean(row.get("SSN")),
            clean(row.get("MSTATUS")),
            clean(row.get("HOMEPHONE")), clean(row.get("CELLPHONE")), clean(row.get("WORKPHONE")),
            clean(row.get("EMAIL")),
            clean(row.get("PrefCntMethod")),
            clean(row.get("ADDRESS")), clean(row.get("ADDRESS2")),
            clean(row.get("CITY")), clean(row.get("STATE")), clean(row.get("ZIP")),
            fin[0], fin[1], fin[2],
            parse_bool(row.get("NOAUTOEMAIL", "False")),
            fin[3],
            parse_bool(row.get("ISHIPAA", "False")),
            clean(row.get("POANAME")), clean(row.get("POAPHONE")),
            clean(row.get("REFERRALTYPE")), clean(row.get("REFERREDBY")),
            clean(row.get("NOTES")),
            rpid or None,
            parse_bool(row.get("ACTIVE", "True")),
            clean(row.get("PATTYPE") or row.get("PatTypeDescr")),
            clean(row.get("MEDICAIDID")),
        ))

        # Track the account's representative patient for the RPID bridge.
        if rpid:
            rank = 0 if (row.get("RELTORESP") or "").strip() == "S" else 1
            cand = (rank, _patid_sort_key(patid), patid)
            if rpid not in rp_best or cand < rp_best[rpid]:
                rp_best[rpid] = cand

    buf.flush()
    patient_map = {str(legacy): pk for pk, legacy in buf.returned}

    # ── 3. Build RPID → guarantor's primary patient bridge ─────────────────────
    rp_patient_map: dict[str, int] = {}
    for rpid, (_rank, _sk, patid) in rp_best.items():
        pid = patient_map.get(patid)
        if pid is not None:
            rp_patient_map[rpid] = pid
    maps["rp_patient_map"] = rp_patient_map

    print(
        f"  [s17] patients: {buf.inserted} upserted, {skipped} skipped → "
        f"map size {len(patient_map)} (rp_bridge {len(rp_patient_map)})"
    )
    return patient_map
