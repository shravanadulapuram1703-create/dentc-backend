"""dedupe chart_materials + chart_colors, add (tenant_id, legacy_id) unique constraints

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-06-17

Same defect as code_bundles: neither chart_materials nor chart_colors had a unique
key, so the Denticon importer's ``ON CONFLICT DO NOTHING`` was a no-op and migration
re-runs produced duplicate rows (materials 4x, colors 5x per legacy_id). This
collapses each (tenant_id, legacy_id) group to its lowest id and adds the uniqueness
constraint so it cannot recur. chart_materials is referenced by four FK columns, which
are repointed to the survivor before the duplicates are removed.
"""

from __future__ import annotations

from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None

# dupe_id -> surviving (lowest) id for each (tenant_id, legacy_id) group.
_REMAP = """
WITH remap AS (
    SELECT m.id AS dupe_id,
           (SELECT MIN(m2.id) FROM chart_materials m2
             WHERE m2.tenant_id = m.tenant_id AND m2.legacy_id = m.legacy_id) AS keep_id
    FROM chart_materials m
    WHERE m.legacy_id IS NOT NULL
)
UPDATE {table} t SET {col} = r.keep_id
FROM remap r
WHERE t.{col} = r.dupe_id AND r.dupe_id <> r.keep_id
"""

# Tables/columns that FK to chart_materials.id.
_MATERIAL_FKS = [
    ("patient_procedures", "material_id"),
    ("chart_conditions", "material_id"),
    ("appointment_procedures", "material_id"),
    ("procedure_codes", "default_material_id"),
]


def _dedupe_delete(table: str) -> str:
    return f"""
    DELETE FROM {table} t
    WHERE t.legacy_id IS NOT NULL
      AND t.id > (
        SELECT MIN(t2.id) FROM {table} t2
        WHERE t2.tenant_id = t.tenant_id AND t2.legacy_id = t.legacy_id
      )
    """


def upgrade() -> None:
    # chart_materials: repoint inbound FKs to the survivor, then drop duplicates.
    for table, col in _MATERIAL_FKS:
        op.execute(_REMAP.format(table=table, col=col))
    op.execute(_dedupe_delete("chart_materials"))
    op.create_unique_constraint(
        "uq_chart_materials_tenant_legacy", "chart_materials", ["tenant_id", "legacy_id"]
    )

    # chart_colors: no inbound FKs — straight delete.
    op.execute(_dedupe_delete("chart_colors"))
    op.create_unique_constraint(
        "uq_chart_colors_tenant_legacy", "chart_colors", ["tenant_id", "legacy_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_chart_colors_tenant_legacy", "chart_colors", type_="unique")
    op.drop_constraint("uq_chart_materials_tenant_legacy", "chart_materials", type_="unique")
