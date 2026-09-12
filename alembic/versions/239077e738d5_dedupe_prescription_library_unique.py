"""dedupe prescription_library + add (tenant_id, legacy_id) unique constraint

Revision ID: 239077e738d5
Revises: b6c7d8e9f0a1
Create Date: 2026-09-10

RX-4 (Rx / Prescriptions — duplicate drug names). Same defect as code_bundles,
chart_materials and chart_colors: ``prescription_library`` had no unique key, so
the Denticon importer's ``ON CONFLICT DO NOTHING`` was a no-op and each migration
re-run appended the whole library again (85 legacy drugs x 5 runs = 425 rows; the
Rx Drug Name picker showed every drug 5 times). This collapses each
(tenant_id, legacy_id) group to its lowest id and adds the uniqueness constraint
so it cannot recur. API-created rows (NULL legacy_id) are untouched.

Two tables FK to prescription_library.id and are repointed to the survivor first:
- ``prescriptions.library_rx_id`` (patient Rx rows written from a duplicate id)
- ``office_prescription_library.prescription_library_id`` — unique on
  (office_id, prescription_library_id), so a link to a duplicate is dropped when
  the office already links the survivor, and repointed otherwise.

Rides along (RX-1 round 2): ``prescription_library.created_by`` (FK users) so the
Setup header can show Created By next to Modified By. Nullable — migrated rows
have no author in the export.

Verified on the dev DB before applying (2026-09-10): 427 rows, 85 legacy groups
x 5 identical copies, 340 to delete, 14 ``prescriptions`` + 1 office link
pointing at a duplicate, and ``prescriptions`` / ``office_prescription_library``
are the only two inbound FKs.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "239077e738d5"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None

# dupe_id -> surviving (lowest) id for each (tenant_id, legacy_id) group.
_REMAP_CTE = """
WITH remap AS (
    SELECT p.id AS dupe_id,
           (SELECT MIN(p2.id) FROM prescription_library p2
             WHERE p2.tenant_id = p.tenant_id AND p2.legacy_id = p.legacy_id) AS keep_id
    FROM prescription_library p
    WHERE p.legacy_id IS NOT NULL
)
"""

_REPOINT_PRESCRIPTIONS = _REMAP_CTE + """
UPDATE prescriptions t SET library_rx_id = r.keep_id
FROM remap r
WHERE t.library_rx_id = r.dupe_id AND r.dupe_id <> r.keep_id
"""

# Office links: drop the duplicate's link when the survivor is already linked
# (uq_office_rx would otherwise reject the repoint), then repoint the rest.
_DROP_REDUNDANT_OFFICE_LINKS = _REMAP_CTE + """
DELETE FROM office_prescription_library l
USING remap r
WHERE l.prescription_library_id = r.dupe_id
  AND r.dupe_id <> r.keep_id
  AND EXISTS (
    SELECT 1 FROM office_prescription_library l2
    WHERE l2.office_id = l.office_id AND l2.prescription_library_id = r.keep_id
  )
"""

_REPOINT_OFFICE_LINKS = _REMAP_CTE + """
UPDATE office_prescription_library t SET prescription_library_id = r.keep_id
FROM remap r
WHERE t.prescription_library_id = r.dupe_id AND r.dupe_id <> r.keep_id
"""

_DEDUPE_DELETE = """
DELETE FROM prescription_library t
WHERE t.legacy_id IS NOT NULL
  AND t.id > (
    SELECT MIN(t2.id) FROM prescription_library t2
    WHERE t2.tenant_id = t.tenant_id AND t2.legacy_id = t.legacy_id
  )
"""


def upgrade() -> None:
    op.execute(_REPOINT_PRESCRIPTIONS)
    op.execute(_DROP_REDUNDANT_OFFICE_LINKS)
    op.execute(_REPOINT_OFFICE_LINKS)
    op.execute(_DEDUPE_DELETE)
    op.create_unique_constraint(
        "uq_prescription_library_tenant_legacy", "prescription_library", ["tenant_id", "legacy_id"]
    )
    # RX-1 round 2 — Created By (updated_by shipped in f1a2b3c4d5e6).
    op.add_column("prescription_library", sa.Column("created_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_prescription_library_created_by_users"),
        "prescription_library", "users", ["created_by"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_prescription_library_created_by_users"), "prescription_library", type_="foreignkey"
    )
    op.drop_column("prescription_library", "created_by")
    # Data collapse is not reversible (the removed rows were exact copies).
    op.drop_constraint(
        "uq_prescription_library_tenant_legacy", "prescription_library", type_="unique"
    )
