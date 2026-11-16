"""RP-1/RP-3/RP-4 backfill: give every patient an account and a typed guarantor.

One function, run by the Alembic revision **and** by
``scripts/backfill_patient_accounts.py`` (the Denticon importer writes patients by
raw SQL, so a re-import is followed by a re-run). Postgres only; idempotent — it
touches only patients whose ``account_id`` is NULL.

Classification of ``patients.responsible_party_id`` (``key``), in order:

1. NULL / blank / equal to the patient's own id            → **self** (RP-4)
2. app-created patient, numeric key = a ``responsible_parties.id`` → party
3. app-created patient, numeric key = another *self* patient's id  → that patient
4. anything else (every migrated RPID, unresolvable app keys) → grouped by the key;
   guarantor = the group's ``S`` member, else an imported RP row with that
   ``legacy_id`` (RP-14), else **unresolved** (both guarantor columns NULL).

Migrated rows (``legacy_id IS NOT NULL``) skip 2/3: their key is a Denticon RPID,
and a coincidental match against an app id is exactly the RP-1 collision.
"""

from __future__ import annotations

from sqlalchemy import text

_STEPS: tuple[str, ...] = (
    "DROP TABLE IF EXISTS _rp_class",
    """
    CREATE TEMP TABLE _rp_class AS
    SELECT p.id AS patient_id, p.tenant_id, p.home_office_id,
           NULLIF(btrim(p.responsible_party_id), '') AS key,
           (p.legacy_id IS NOT NULL) AS migrated,
           CAST(NULL AS text) AS kind, CAST(NULL AS text) AS group_key,
           CAST(NULL AS integer) AS guar_patient, CAST(NULL AS integer) AS guar_party
    FROM patients p WHERE p.account_id IS NULL
    """,
    # 1. self
    """
    UPDATE _rp_class SET kind = 'self', group_key = 'P:' || patient_id, guar_patient = patient_id
    WHERE key IS NULL OR key = patient_id::text
    """,
    # 2. app-created → RP row id
    """
    UPDATE _rp_class c SET kind = 'party', group_key = 'RP:' || r.id, guar_party = r.id
    FROM responsible_parties r
    WHERE c.kind IS NULL AND NOT c.migrated AND c.key ~ '^[0-9]{1,9}$'
      AND r.id = c.key::int AND r.tenant_id = c.tenant_id
    """,
    # 3. app-created → another self patient (head of household)
    """
    UPDATE _rp_class c SET kind = 'patient', group_key = 'P:' || g.patient_id,
           guar_patient = g.patient_id
    FROM _rp_class g
    WHERE c.kind IS NULL AND NOT c.migrated AND c.key ~ '^[0-9]{1,9}$'
      AND g.patient_id = c.key::int AND g.tenant_id = c.tenant_id AND g.kind = 'self'
    """,
    # 4. everything else groups by the raw key
    "UPDATE _rp_class SET kind = 'legacy', group_key = 'L:' || key WHERE kind IS NULL",
    # 4a. the group's Self member is the guarantor
    """
    UPDATE _rp_class c SET guar_patient = s.pid
    FROM (
        SELECT c2.tenant_id, c2.group_key, MIN(c2.patient_id) AS pid
        FROM _rp_class c2 JOIN patients p ON p.id = c2.patient_id
        WHERE c2.kind = 'legacy' AND upper(btrim(p.responsible_party_relationship)) IN ('S', 'SELF')
        GROUP BY c2.tenant_id, c2.group_key
    ) s
    WHERE c.kind = 'legacy' AND c.tenant_id = s.tenant_id AND c.group_key = s.group_key
    """,
    # 4b. else an imported legacy guarantor (RP-14)
    """
    UPDATE _rp_class c SET guar_party = r.id
    FROM (SELECT tenant_id, legacy_id, MIN(id) AS id FROM responsible_parties
          WHERE legacy_id IS NOT NULL GROUP BY tenant_id, legacy_id) r
    WHERE c.kind = 'legacy' AND c.guar_patient IS NULL
      AND r.tenant_id = c.tenant_id AND r.legacy_id = c.key
    """,
    # Join an account that already exists for the group (re-run after an import).
    """
    UPDATE patients p SET account_id = a.id
    FROM _rp_class c JOIN accounts a
      ON a.tenant_id = c.tenant_id AND a.is_active
     AND (   (c.kind = 'legacy' AND a.legacy_key = c.key)
          OR (c.kind = 'party' AND a.primary_guarantor_party_id = c.guar_party)
          OR (c.kind IN ('self', 'patient') AND a.primary_guarantor_patient_id = c.guar_patient
              AND a.legacy_key IS NULL))
    WHERE p.id = c.patient_id
    """,
    "DELETE FROM _rp_class c USING patients p WHERE p.id = c.patient_id AND p.account_id IS NOT NULL"
    " AND c.kind <> 'legacy'",
    # New accounts, one per (tenant, group). legacy_key temporarily holds the group key.
    """
    INSERT INTO accounts (tenant_id, legacy_key, primary_guarantor_patient_id,
                          primary_guarantor_party_id, home_office_id, send_statements,
                          no_email_statement, send_collections, is_finance_charge,
                          is_active, created_at)
    SELECT c.tenant_id, c.group_key, MIN(c.guar_patient), MIN(c.guar_party),
           MIN(c.home_office_id), TRUE, FALSE, FALSE, FALSE, TRUE, now()
    FROM _rp_class c JOIN patients p ON p.id = c.patient_id
    WHERE p.account_id IS NULL
    GROUP BY c.tenant_id, c.group_key
    """,
    """
    UPDATE patients p SET account_id = a.id
    FROM _rp_class c JOIN accounts a ON a.tenant_id = c.tenant_id AND a.legacy_key = c.group_key
    WHERE p.id = c.patient_id AND p.account_id IS NULL
    """,
    # Typed guarantor + alias + Self relationship (RP-4 / RP-15).
    """
    UPDATE patients p SET
        guarantor_patient_id = c.guar_patient,
        guarantor_party_id = CASE WHEN c.guar_patient IS NULL THEN c.guar_party END,
        responsible_party_id = CASE WHEN c.kind = 'self' THEN p.id::text ELSE p.responsible_party_id END,
        responsible_party_relationship = CASE
            WHEN c.guar_patient = p.id AND NULLIF(btrim(p.responsible_party_relationship), '') IS NULL
            THEN 'S' ELSE p.responsible_party_relationship END
    FROM _rp_class c
    WHERE p.id = c.patient_id AND p.guarantor_patient_id IS NULL AND p.guarantor_party_id IS NULL
    """,
    # Seed account billing flags + office from the guarantor.
    """
    UPDATE accounts a SET
        home_office_id = COALESCE(p.home_office_id, a.home_office_id),
        send_statements = COALESCE(p.send_statements, TRUE),
        send_collections = COALESCE(p.send_collections, FALSE),
        is_finance_charge = COALESCE(p.is_finance_charge, FALSE)
    FROM patients p
    WHERE p.id = a.primary_guarantor_patient_id AND a.legacy_key LIKE '%:%'
    """,
    """
    UPDATE accounts a SET
        home_office_id = COALESCE(r.home_office_id, a.home_office_id),
        send_statements = COALESCE(r.send_statements, TRUE),
        no_email_statement = COALESCE(r.no_email_statement, FALSE),
        send_collections = COALESCE(r.send_collections, FALSE),
        is_finance_charge = COALESCE(r.is_finance_charge, FALSE),
        collection_agency_id = r.collection_agency_id,
        statement_message = r.statement_message,
        financial_notes = r.financial_notes
    FROM responsible_parties r
    WHERE r.id = a.primary_guarantor_party_id AND a.legacy_key LIKE '%:%'
    """,
    # Account numbers: the RPID for migrated groups, else the id (probed).
    """
    UPDATE accounts SET account_no = substr(legacy_key, 3), legacy_key = substr(legacy_key, 3)
    WHERE legacy_key LIKE 'L:%'
    """,
    "UPDATE accounts SET legacy_key = NULL WHERE legacy_key LIKE 'P:%' OR legacy_key LIKE 'RP:%'",
    """
    UPDATE accounts a SET account_no = CASE
        WHEN EXISTS (SELECT 1 FROM accounts b WHERE b.tenant_id = a.tenant_id
                     AND b.account_no = a.id::text) THEN 'A' || a.id::text
        ELSE a.id::text END
    WHERE a.account_no IS NULL
    """,
    # RP-9: stamp the account on existing money + statements.
    """
    UPDATE patient_payments pp SET account_id = p.account_id
    FROM patients p WHERE p.id = pp.patient_id AND pp.account_id IS NULL
    """,
    """
    UPDATE patient_statements s SET account_id = p.account_id
    FROM patients p WHERE p.id = s.patient_id AND s.account_id IS NULL
    """,
)


def backfill(conn) -> dict:  # noqa: ANN001
    """Run every step on ``conn`` (no commit). Returns a count summary."""
    before = conn.execute(text("SELECT count(*) FROM patients WHERE account_id IS NULL")).scalar()
    for sql in _STEPS[:8]:
        conn.execute(text(sql))
    kinds = dict(conn.execute(text("SELECT kind, count(*) FROM _rp_class GROUP BY kind")).all())
    unresolved = conn.execute(text(
        "SELECT count(*) FROM _rp_class WHERE guar_patient IS NULL AND guar_party IS NULL"
    )).scalar()
    for sql in _STEPS[8:]:
        conn.execute(text(sql))
    conn.execute(text("DROP TABLE IF EXISTS _rp_class"))
    after = conn.execute(text("SELECT count(*) FROM patients WHERE account_id IS NULL")).scalar()
    return {
        "patients_without_account_before": before,
        "patients_without_account_after": after,
        "classified": kinds,
        "unresolved_guarantor": unresolved,
    }
