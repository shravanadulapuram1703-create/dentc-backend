"""
Reload in-memory lookup maps from the database when resuming with --from N.
"""

from __future__ import annotations


def _legacy_map(cur, table: str, id_col: str = "id") -> dict[str, object]:
    cur.execute(
        f"SELECT legacy_id, {id_col} FROM {table} WHERE legacy_id IS NOT NULL"
    )
    return {str(row[0]): row[1] for row in cur.fetchall()}


def load_maps_from_db(conn) -> dict:
    """Rebuild all standard step maps from rows already in PostgreSQL."""
    cur = conn.cursor()
    maps: dict = {}

    maps["tenant_map"] = _legacy_map(cur, "tenants")
    maps["office_map"] = _legacy_map(cur, "offices")
    maps["provider_map"] = _legacy_map(cur, "providers")
    maps["operatory_map"] = _legacy_map(cur, "operatories")
    maps["employer_map"] = _legacy_map(cur, "employers")
    maps["carrier_map"] = _legacy_map(cur, "insurance_carriers")
    maps["ins_plan_map"] = _legacy_map(cur, "insurance_plans")
    maps["fee_sched_map"] = _legacy_map(cur, "fee_schedules")
    maps["material_map"] = _legacy_map(cur, "chart_materials")
    maps["bundle_map"] = _legacy_map(cur, "code_bundles")
    maps["rx_lib_map"] = _legacy_map(cur, "prescription_library")
    maps["patient_map"] = _legacy_map(cur, "patients")
    # RPID → guarantor's primary patient (lowest patient id on the account),
    # for account-level steps keyed by the responsible party.
    cur.execute(
        "SELECT responsible_party_id, MIN(id) FROM patients "
        "WHERE responsible_party_id IS NOT NULL GROUP BY responsible_party_id"
    )
    maps["rp_patient_map"] = {str(r[0]): r[1] for r in cur.fetchall()}
    maps["sub_map"] = _legacy_map(cur, "insurance_subscribers")
    maps["sig_map"] = _legacy_map(cur, "patient_signatures")
    maps["txplan_map"] = _legacy_map(cur, "treatment_plans")
    maps["appt_map"] = _legacy_map(cur, "appointments")
    maps["procedure_map"] = _legacy_map(cur, "patient_procedures")
    maps["payment_map"] = _legacy_map(cur, "patient_payments")
    maps["claim_map"] = _legacy_map(cur, "insurance_claims")
    maps["perio_exam_map"] = _legacy_map(cur, "perio_exams")
    maps["q_map"] = _legacy_map(cur, "questionnaire_headers")
    maps["color_map"] = _legacy_map(cur, "chart_colors")

    cur.execute("SELECT code FROM procedure_codes")
    maps["proc_code_set"] = {row[0] for row in cur.fetchall()}

    cur.execute(
        "SELECT id, legacy_id, username FROM users WHERE legacy_id IS NOT NULL OR username IS NOT NULL"
    )
    user_map: dict[str, int] = {}
    for user_id, legacy_id, username in cur.fetchall():
        if legacy_id:
            user_map[str(legacy_id)] = user_id
            user_map[str(legacy_id).lower()] = user_id
        if username:
            user_map[str(username)] = user_id
            user_map[str(username).lower()] = user_id
    maps["user_map"] = user_map

    return maps


def summarize_maps(maps: dict) -> str:
    parts = []
    for key in sorted(maps):
        val = maps[key]
        if isinstance(val, set):
            parts.append(f"{key}={len(val)}")
        elif isinstance(val, dict):
            parts.append(f"{key}={len(val)}")
    return ", ".join(parts)


def merge_legacy_map(
    conn,
    maps: dict,
    key: str,
    table: str,
    id_col: str = "id",
) -> dict[str, object]:
    """Merge in-memory map with legacy_id rows already stored in PostgreSQL."""
    merged = dict(maps.get(key, {}))
    cur = conn.cursor()
    cur.execute(
        f"SELECT legacy_id, {id_col} FROM {table} WHERE legacy_id IS NOT NULL"
    )
    for legacy_id, pk in cur.fetchall():
        merged[str(legacy_id)] = pk
    return merged
