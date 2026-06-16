"""dedupe code_bundles + add (tenant_id, legacy_id) unique constraint

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-06-14

Explosion Codes data note: ``code_bundles`` had no unique key, so the importer's
``ON CONFLICT DO NOTHING`` was a no-op and produced duplicate bundles per
``legacy_id``. This collapses each (tenant_id, legacy_id) group to its lowest id
(removing the duplicate bundles and their redundant items) and then adds the
uniqueness constraint so it cannot recur.
"""

from __future__ import annotations

from alembic import op

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

# Delete items of non-survivor duplicates, then the duplicate bundles themselves.
_DEDUPE_ITEMS = """
DELETE FROM code_bundle_items
WHERE bundle_id IN (
    SELECT c.id FROM code_bundles c
    WHERE c.legacy_id IS NOT NULL
      AND c.id > (
        SELECT MIN(c2.id) FROM code_bundles c2
        WHERE c2.tenant_id = c.tenant_id AND c2.legacy_id = c.legacy_id
      )
)
"""

_DEDUPE_BUNDLES = """
DELETE FROM code_bundles c
WHERE c.legacy_id IS NOT NULL
  AND c.id > (
    SELECT MIN(c2.id) FROM code_bundles c2
    WHERE c2.tenant_id = c.tenant_id AND c2.legacy_id = c.legacy_id
  )
"""


def upgrade() -> None:
    op.execute(_DEDUPE_ITEMS)
    op.execute(_DEDUPE_BUNDLES)
    op.create_unique_constraint(
        "uq_code_bundles_tenant_legacy", "code_bundles", ["tenant_id", "legacy_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_code_bundles_tenant_legacy", "code_bundles", type_="unique")
