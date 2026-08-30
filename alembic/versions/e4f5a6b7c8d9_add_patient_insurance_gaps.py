"""Insurance — patient-insurance / plan-setup gaps (INS-PT-8, INS-PT-11).

Backs ``docs/patient-insurance/patient_insurance_backend_devreport.md``:

- **INS-PT-8** ``insurance_plans`` had ``created_at`` and nothing else, so the
  Setup -> Insurance -> Plans grid rendered **Modified** as ``—`` on every row
  and **Created** as a bare date with no user. The plan now carries the same
  audit shape ``insurance_carriers`` has had since INS-6: ``updated_at``
  (server, via ``TimestampMixin``) + ``updated_by`` (the acting user, stamped by
  ``CRUDBase.update``), plus the four legacy free-text columns
  ``created_on``/``created_by``/``modified_on``/``modified_by``. The legacy pair
  exists because ``InsPlans.txt`` carries ``CREATEDBY``/``MODIFIEDBY`` as a
  Denticon login string, and 2.2M-odd such logins across the migration have no
  ``users`` row to point a FK at — a name that renders beats a NULL FK.

- **INS-PT-11** ``employers.address2`` — the legacy EMPLOYER DETAILS dialog has
  two address lines and the frontend was joining them on a newline into the
  single ``address`` column. ``insurance_carriers.address2`` already existed;
  this makes the two entities symmetric, and ``Employers.txt`` has an
  ``ADDRESS2`` column that was simply never read (see
  ``scripts/backfill_insurance_source_fields.py``).

Also indexes ``insurance_plans (tenant_id, group_number)``. INS-PT-19/20 turn the
group number into a *lookup* key — the duplicate guard runs on every plan save
and ``GET /insurance-plans/group-availability`` runs on every duplicate probe —
against 31,331 rows, where it was previously only ever an equality filter on a
page the user had already narrowed.

No uniqueness constraint is added on purpose: two offices can legitimately hold
separate plans on one group number and the legacy system allows it, so INS-PT-19
is a **409 with an explicit override**, which a DB constraint cannot express.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # INS-PT-8 — plan audit metadata.
    op.add_column("insurance_plans", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("insurance_plans", sa.Column("created_on", sa.DateTime(), nullable=True))
    op.add_column("insurance_plans", sa.Column("created_by", sa.String(100), nullable=True))
    op.add_column("insurance_plans", sa.Column("modified_on", sa.DateTime(), nullable=True))
    op.add_column("insurance_plans", sa.Column("modified_by", sa.String(100), nullable=True))
    op.add_column("insurance_plans", sa.Column("updated_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_insurance_plans_updated_by_users",
        "insurance_plans", "users", ["updated_by"], ["id"],
    )

    # INS-PT-19/20 — the duplicate guard and the availability probe both look the
    # group number up directly.
    op.create_index(
        "ix_insurance_plans_tenant_group_number",
        "insurance_plans",
        ["tenant_id", "group_number"],
    )

    # INS-PT-11 — second employer address line.
    op.add_column("employers", sa.Column("address2", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("employers", "address2")
    op.drop_index("ix_insurance_plans_tenant_group_number", table_name="insurance_plans")
    op.drop_constraint("fk_insurance_plans_updated_by_users", "insurance_plans", type_="foreignkey")
    op.drop_column("insurance_plans", "updated_by")
    op.drop_column("insurance_plans", "modified_by")
    op.drop_column("insurance_plans", "modified_on")
    op.drop_column("insurance_plans", "created_by")
    op.drop_column("insurance_plans", "created_on")
    op.drop_column("insurance_plans", "updated_at")
