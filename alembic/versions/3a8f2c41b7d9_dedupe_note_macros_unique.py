"""dedupe note_macros + add (tenant_id, legacy_id) unique constraint

Revision ID: 3a8f2c41b7d9
Revises: b08a4634a3e3 (medical-alert surfacing landed alongside; this
         was re-parented so the two dedupe migrations do not fork the head)
Create Date: 2026-09-10

NM-7 (Notes Macros Setup — "every macro appears four times"). The same defect
as prescription_library (239077e738d5), chart_materials, code_bundles and
chart_colors: ``note_macros`` had no unique key, so the Denticon importer's
``ON CONFLICT DO NOTHING`` was a no-op and each migration re-run appended the
whole macro catalog again (120 legacy macros x 4 runs = 480 rows, byte-identical
per legacy_id; every macro list in the app — Setup, Progress Notes, Patient
Notes — listed each entry four times). This collapses each (tenant_id,
legacy_id) group to its lowest id and adds the uniqueness constraint so it
cannot recur. API-created rows (NULL legacy_id) are untouched.

Two tables FK to note_macros.id and are repointed to the survivor first:
- ``procedure_codes.default_notes_macro_id`` (the code's default macro)
- ``office_note_macros.note_macro_id`` — unique on (office_id, note_macro_id),
  so a link to a duplicate is dropped when the office already links the
  survivor, and repointed otherwise.

Verified on the dev DB before applying (2026-09-10): 481 rows, 120 groups x 4
identical copies, 360 to delete, 3 procedure_codes + 1 office link pointing at
a duplicate, and those two tables are the only inbound FKs.
"""

from __future__ import annotations

from alembic import op

revision = "3a8f2c41b7d9"
down_revision = "b08a4634a3e3"
branch_labels = None
depends_on = None

# dupe_id -> surviving (lowest) id for each (tenant_id, legacy_id) group.
_REMAP_CTE = """
WITH remap AS (
    SELECT p.id AS dupe_id,
           (SELECT MIN(p2.id) FROM note_macros p2
             WHERE p2.tenant_id = p.tenant_id AND p2.legacy_id = p.legacy_id) AS keep_id
    FROM note_macros p
    WHERE p.legacy_id IS NOT NULL
)
"""

_REPOINT_PROCEDURE_CODES = _REMAP_CTE + """
UPDATE procedure_codes t SET default_notes_macro_id = r.keep_id
FROM remap r
WHERE t.default_notes_macro_id = r.dupe_id AND r.dupe_id <> r.keep_id
"""

_DROP_REDUNDANT_OFFICE_LINKS = _REMAP_CTE + """
DELETE FROM office_note_macros l
USING remap r
WHERE l.note_macro_id = r.dupe_id
  AND r.dupe_id <> r.keep_id
  AND EXISTS (
    SELECT 1 FROM office_note_macros l2
    WHERE l2.office_id = l.office_id AND l2.note_macro_id = r.keep_id
  )
"""

_REPOINT_OFFICE_LINKS = _REMAP_CTE + """
UPDATE office_note_macros t SET note_macro_id = r.keep_id
FROM remap r
WHERE t.note_macro_id = r.dupe_id AND r.dupe_id <> r.keep_id
"""

_DEDUPE_DELETE = """
DELETE FROM note_macros t
WHERE t.legacy_id IS NOT NULL
  AND t.id > (
    SELECT MIN(t2.id) FROM note_macros t2
    WHERE t2.tenant_id = t.tenant_id AND t2.legacy_id = t.legacy_id
  )
"""


def upgrade() -> None:
    op.execute(_REPOINT_PROCEDURE_CODES)
    op.execute(_DROP_REDUNDANT_OFFICE_LINKS)
    op.execute(_REPOINT_OFFICE_LINKS)
    op.execute(_DEDUPE_DELETE)
    op.create_unique_constraint(
        "uq_note_macros_tenant_legacy", "note_macros", ["tenant_id", "legacy_id"]
    )


def downgrade() -> None:
    # Data collapse is not reversible (the removed rows were exact copies).
    op.drop_constraint("uq_note_macros_tenant_legacy", "note_macros", type_="unique")
