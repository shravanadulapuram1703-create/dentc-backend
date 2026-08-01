"""fix patient_insurance slot uniqueness (BUG-3)

The migrated DB carried a legacy unique constraint on
``(patient_id, insurance_type)`` (Postgres-default name
``patient_insurance_patient_id_insurance_type_key``), which blocked a patient from
holding both a Primary **Dental** and a Primary **Medical** plan (both have
``insurance_type='primary'``). Replace it with a slot-aware unique on
``(patient_id, legacy_plan_type, insurance_type)`` so dental/medical primaries
coexist while still preventing true duplicate slots.

The legacy constraint is not in the migration chain (it came from the Denticon
data migration), so the drop is guarded by an inspector check to stay a no-op on
environments that never had it.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None

_LEGACY = "patient_insurance_patient_id_insurance_type_key"
_SLOT = "uq_patient_insurance_patient_slot"


def _unique_names(bind) -> set[str]:  # noqa: ANN001
    return {uc["name"] for uc in sa.inspect(bind).get_unique_constraints("patient_insurance")}


def upgrade() -> None:
    bind = op.get_bind()
    existing = _unique_names(bind)
    if _LEGACY in existing:
        op.drop_constraint(_LEGACY, "patient_insurance", type_="unique")
    if _SLOT not in existing:
        op.create_unique_constraint(
            _SLOT, "patient_insurance", ["patient_id", "legacy_plan_type", "insurance_type"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    existing = _unique_names(bind)
    if _SLOT in existing:
        op.drop_constraint(_SLOT, "patient_insurance", type_="unique")
    # Best-effort restore of the legacy shape (may fail if duplicate primaries now
    # exist — that is the whole point of this migration, so it is left off on error).
    if _LEGACY not in existing:
        op.create_unique_constraint(
            _LEGACY, "patient_insurance", ["patient_id", "insurance_type"]
        )
