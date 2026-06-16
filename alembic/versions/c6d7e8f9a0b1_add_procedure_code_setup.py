"""add Procedure Code Setup fields + tables (PROC-1..PROC-4)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-06-14

Resolves procedure-code dev-report gaps:
- PROC-1: procedure_codes charting columns (+ valid_teeth JSON).
- PROC-4: procedure_codes legacy "Main" booleans/codes.
- PROC-2: provider_procedure_codes (provider↔code permission).
- PROC-3: procedure_insurance_rules (per-code, plan-agnostic coverage).

(PROC-5 stats and PROC-6 fee-schedule options are application-layer only.)

Additive; new columns nullable (booleans default false).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.base import Base
from app.db.models.procedure_setup import ProcedureInsuranceRule, ProviderProcedureCode

revision = "c6d7e8f9a0b1"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None

_NEW_TABLES = [
    ProviderProcedureCode.__table__,
    ProcedureInsuranceRule.__table__,
]

# name, type, [server_default]
_PROC_COLS = [
    # PROC-1
    ("chart_category", sa.String(length=100)),
    ("tooth_area", sa.String(length=50)),
    ("draw_as", sa.String(length=50)),
    ("min_surfaces", sa.Integer()),
    ("max_surfaces", sa.Integer()),
    ("default_material_id", sa.Integer()),
    ("valid_teeth", sa.JSON()),
    # PROC-4
    ("taxable", sa.Boolean(), "false"),
    ("sales_tax_code", sa.String(length=50)),
    ("visit_code", sa.String(length=50)),
    ("ledger_code", sa.String(length=50)),
    ("ar_code", sa.String(length=50)),
    ("is_post_op", sa.Boolean(), "false"),
    ("exempt_from_dental_max", sa.Boolean(), "false"),
    ("lock_default_provider", sa.Boolean(), "false"),
    ("default_provider_id", sa.String(length=50)),
    ("default_notes_macro_id", sa.Integer()),
    ("show_ada_code_in_notes", sa.Boolean(), "false"),
    ("nhs_treatment_category", sa.String(length=100)),
    ("nhs_clinical_data_set", sa.String(length=100)),
]


def upgrade() -> None:
    for name, type_, *default in _PROC_COLS:
        server_default = default[0] if default else None
        op.add_column("procedure_codes", sa.Column(name, type_, nullable=True, server_default=server_default))
    op.create_foreign_key(
        "fk_procedure_codes_default_material_id_chart_materials",
        "procedure_codes", "chart_materials", ["default_material_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_procedure_codes_default_provider_id_providers",
        "procedure_codes", "providers", ["default_provider_id"], ["id"],
    )
    op.create_foreign_key(
        "fk_procedure_codes_default_notes_macro_id_note_macros",
        "procedure_codes", "note_macros", ["default_notes_macro_id"], ["id"],
    )

    Base.metadata.create_all(bind=op.get_bind(), tables=_NEW_TABLES, checkfirst=True)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=list(reversed(_NEW_TABLES)))

    for fk in (
        "fk_procedure_codes_default_notes_macro_id_note_macros",
        "fk_procedure_codes_default_provider_id_providers",
        "fk_procedure_codes_default_material_id_chart_materials",
    ):
        op.drop_constraint(fk, "procedure_codes", type_="foreignkey")
    for name, *_ in reversed(_PROC_COLS):
        op.drop_column("procedure_codes", name)
