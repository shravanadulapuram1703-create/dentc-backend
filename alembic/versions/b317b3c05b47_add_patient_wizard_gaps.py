"""Add New Patient — full-wizard gaps (GAP-AP-19/20/25)

Revision ID: b317b3c05b47
Revises: 17559b3b70d4
Create Date: 2026-09-11

Frontend reports: ``docs/patients/add_patient_backend_devreport.md`` (GAP-AP-19)
and ``docs/patients/add_patient_full_wizard_backend_issues.md`` (GAP-AP-20..26).

GAP-AP-19 — ``patients.middle_name`` / ``responsible_parties.middle_name``
    The legacy product stored a middle *initial* only (``middle_initial
    VARCHAR(10)``); the wizard's new Middle Name field had to be hard-capped at
    ten characters to avoid a 500. ``middle_initial`` stays for legacy parity
    and is derived (``middle_name[:1]``) when a write carries only the name.

GAP-AP-20 — catalog codes widened 50 -> 100
    ``patient_medical_alerts.alert_code`` and
    ``patient_questionnaire_responses.question_code`` are derived by the
    frontend from the legacy question *labels* (``to_code``), and 12 of the 51
    legacy questions slug to 51–60 characters — every one of them was a
    Postgres ``StringDataRightTruncation`` -> HTTP 500 that rolled back the
    whole ``/patients/register`` transaction. ``medical_history_details.
    question_code`` is widened alongside: the signed-version snapshot (MH-6)
    copies both codes into it, so a widened source with an unwidened sink would
    only move the 500 to ``/medical-history/sign``. A pure widen — no data is
    rewritten and no row can be invalidated.

GAP-AP-25 — ``resp_party_rel`` was seeded twice
    The account seeder carried both the lowercase key set (``self/spouse/…``)
    and the legacy single-letter codes (``S/SP/P/G/C/D/O``, added for PO-9 so
    migrated ``patient_insurance.relationship`` values expand), so the
    "Rel. to Resp" dropdown listed every option twice. The **code** set is
    canonical (legacy parity, and it is the only one with *Dependent*). The
    lowercase rows are deactivated — not deleted — because ``definitions`` is
    Setup-editable and a practice can reactivate a row it wants back; the
    dropdown consumers already request ``is_active=true``. Stored
    ``patients.responsible_party_relationship`` values are normalised to the
    code so the column is comparable across records (the wizard had been
    storing the *label*, ``Spouse``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b317b3c05b47"
down_revision = "17559b3b70d4"
branch_labels = None
depends_on = None

# (table, column) pairs widened 50 -> 100 (GAP-AP-20).
_WIDEN = (
    ("patient_medical_alerts", "alert_code"),
    ("patient_questionnaire_responses", "question_code"),
    ("medical_history_details", "question_code"),
)

# GAP-AP-25: lowercase key -> canonical single-letter code. Labels are folded
# too because the wizard stored the *description* for a while.
_REL_TO_CODE = {
    "self": "S", "spouse": "SP", "parent": "P", "guardian": "G",
    "child": "C", "dependent": "D", "other": "O",
}
_LEGACY_KEYS = tuple(_REL_TO_CODE)


def upgrade() -> None:
    # GAP-AP-19
    op.add_column("patients", sa.Column("middle_name", sa.String(length=50), nullable=True))
    op.add_column(
        "responsible_parties", sa.Column("middle_name", sa.String(length=50), nullable=True)
    )

    # GAP-AP-20 — widen in place (a pure type widen; Postgres rewrites nothing).
    for table, column in _WIDEN:
        op.alter_column(
            table, column,
            existing_type=sa.String(length=50), type_=sa.String(length=100),
            existing_nullable=False,
        )

    # GAP-AP-25 — retire the duplicate lowercase seed rows on every tenant.
    keys = ", ".join(f"'{k}'" for k in _LEGACY_KEYS)
    op.execute(
        "UPDATE definitions SET is_active = false "
        f"WHERE group_code = 'resp_party_rel' AND key1 IN ({keys})"
    )
    # …and normalise what patients already hold to the canonical code. Only
    # values that are unambiguously a key or a label of the catalog are
    # touched; anything else (a migrated free-text value) is left as written.
    cases = " ".join(
        f"WHEN lower(responsible_party_relationship) = '{key}' THEN '{code}'"
        for key, code in _REL_TO_CODE.items()
    )
    op.execute(
        "UPDATE patients SET responsible_party_relationship = "
        f"CASE {cases} ELSE responsible_party_relationship END "
        f"WHERE lower(responsible_party_relationship) IN ({keys})"
    )


def downgrade() -> None:
    # The relationship-code normalisation and the seed retirement are not
    # reversed: both are data corrections the previous schema accepted as-is.
    for table, column in _WIDEN:
        op.alter_column(
            table, column,
            existing_type=sa.String(length=100), type_=sa.String(length=50),
            existing_nullable=False,
        )
    op.drop_column("responsible_parties", "middle_name")
    op.drop_column("patients", "middle_name")
