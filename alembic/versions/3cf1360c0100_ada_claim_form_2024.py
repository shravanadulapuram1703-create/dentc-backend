"""ADA Dental Claim Form (2024) — the columns the form has no home for

Revision ID: 3cf1360c0100
Revises: b317b3c05b47
Create Date: 2026-09-11

Frontend report: ``docs/claims/ada_claim_form_2024_backend_devreport.md``
(ADA-BE-1..14) + the CLM-FO-1..4 fill-out boxes it folds in.

insurance_claims
    ADA-BE-2   is_epsdt / is_locum_tenens / date_last_srp (the three 2024 boxes;
               date_last_srp NULL = derive from the last completed D4341/D4342)
    ADA-BE-3   icd_qualifier + icd_1..icd_4 (Item 34/34a; CLM-FO-3)
    ADA-BE-5   other_fees (Item 31a)
    ADA-BE-6   missing_teeth (Item 33 per-claim override of the charted set)
    ADA-BE-9   other_ins_plan_id + has_other_coverage (Items 4–11 captured at
               creation instead of re-derived from today's slots)
    CLM-FO-1/2/4  predetermination_number, remarks, signature_on_file,
               place_of_treatment, is_ortho / ortho_appliance_date /
               ortho_months_remaining, prosthesis_replacement /
               prosthesis_prior_date, accident_type / accident_date /
               accident_state — Items 2, 35, 36, 38, 40–47, previously kept in
               per-browser localStorage and therefore invisible to every other
               workstation and to the e-claim.
patient_procedures
    ADA-BE-3   diagnosis_pointers (Item 29a, 837D SV3 pointers)
    ADA-BE-4   quantity (Item 29b, 837D SV304) — backfilled to 1
offices
    ADA-BE-8   npi + taxonomy_code (the Type 2 / organisation NPI, Item 49)
    ADA-BE-13  treatment_address_line1/2, treatment_city/state/zip (Item 56
               physical location when the office bills through a P.O. Box)
providers
    ADA-BE-14  taxonomy_code (Item 56a / 837D PRV03)
patients · responsible_parties · insurance_subscribers
    ADA-BE-10  suffix / suffix / sub_suffix (Items 5, 12, 20; 837D NM107)

Every column is additive and nullable (or boolean-default-false / quantity 1),
so no migrated row is rewritten and nothing can be invalidated. The two
``requires_*``-style booleans are NOT NULL DEFAULT false like their siblings so
a NULL never has to be read as "unknown" on a printed form.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "3cf1360c0100"
down_revision = "b317b3c05b47"
branch_labels = None
depends_on = None


_CLAIM_COLUMNS = (
    sa.Column("is_epsdt", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("is_locum_tenens", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("date_last_srp", sa.Date(), nullable=True),
    sa.Column("icd_qualifier", sa.String(2), nullable=True),
    sa.Column("icd_1", sa.String(10), nullable=True),
    sa.Column("icd_2", sa.String(10), nullable=True),
    sa.Column("icd_3", sa.String(10), nullable=True),
    sa.Column("icd_4", sa.String(10), nullable=True),
    sa.Column("other_fees", sa.Numeric(10, 2), nullable=True),
    sa.Column("missing_teeth", sa.String(120), nullable=True),
    sa.Column("other_ins_plan_id", sa.Integer(), sa.ForeignKey("insurance_plans.id"), nullable=True),
    sa.Column("has_other_coverage", sa.Boolean(), nullable=True),
    sa.Column("predetermination_number", sa.String(50), nullable=True),
    sa.Column("remarks", sa.Text(), nullable=True),
    sa.Column("signature_on_file", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("place_of_treatment", sa.String(2), nullable=True),
    sa.Column("is_ortho", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("ortho_appliance_date", sa.Date(), nullable=True),
    sa.Column("ortho_months_remaining", sa.Integer(), nullable=True),
    sa.Column("prosthesis_replacement", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("prosthesis_prior_date", sa.Date(), nullable=True),
    sa.Column("accident_type", sa.String(15), nullable=True),
    sa.Column("accident_date", sa.Date(), nullable=True),
    sa.Column("accident_state", sa.String(2), nullable=True),
)

_OFFICE_COLUMNS = (
    sa.Column("npi", sa.String(10), nullable=True),
    sa.Column("taxonomy_code", sa.String(10), nullable=True),
    sa.Column("treatment_address_line1", sa.String(255), nullable=True),
    sa.Column("treatment_address_line2", sa.String(255), nullable=True),
    sa.Column("treatment_city", sa.String(100), nullable=True),
    sa.Column("treatment_state", sa.String(50), nullable=True),
    sa.Column("treatment_zip", sa.String(20), nullable=True),
)


def upgrade() -> None:
    for col in _CLAIM_COLUMNS:
        op.add_column("insurance_claims", col)
    op.add_column("patient_procedures", sa.Column("diagnosis_pointers", sa.String(4), nullable=True))
    op.add_column(
        "patient_procedures",
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
    )
    for col in _OFFICE_COLUMNS:
        op.add_column("offices", col)
    op.add_column("providers", sa.Column("taxonomy_code", sa.String(10), nullable=True))
    op.add_column("patients", sa.Column("suffix", sa.String(10), nullable=True))
    op.add_column("responsible_parties", sa.Column("suffix", sa.String(10), nullable=True))
    op.add_column("insurance_subscribers", sa.Column("sub_suffix", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("insurance_subscribers", "sub_suffix")
    op.drop_column("responsible_parties", "suffix")
    op.drop_column("patients", "suffix")
    op.drop_column("providers", "taxonomy_code")
    for col in reversed(_OFFICE_COLUMNS):
        op.drop_column("offices", col.name)
    op.drop_column("patient_procedures", "quantity")
    op.drop_column("patient_procedures", "diagnosis_pointers")
    for col in reversed(_CLAIM_COLUMNS):
        op.drop_column("insurance_claims", col.name)
