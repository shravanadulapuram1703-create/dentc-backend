"""Progress notes round 2 (PN-11)

Revision ID: 17559b3b70d4
Revises: 47371579152e
Create Date: 2026-09-11

Frontend report: ``docs/progress notes/progress_notes_backend_devreport.md``
(PN-8 open question, PN-9, PN-11, PN-12).

``progress_notes.updated_at`` / ``updated_by`` (PN-11)
    the "Modified" half of the legacy Created / Modified column. ``updated_by``
    is stamped by ``CRUDBase.update`` on every real change (a no-op PATCH does
    not re-stamp, MH-20) and ``updated_at`` by the ORM ``onupdate``. A Date-of-
    Service correction (PN-8) now leaves its trace here as well as in
    ``audit_logs.details.before/after``.

No data is touched here. The PN-12 body repair (``~^^~`` decode, ``notes``
regeneration, rx-draw rows → ``drawing_strokes``) is
``scripts/repair_progress_note_content.py`` (dry run by default, backs up the
original columns before writing), and the PN-6 category relabel is
``scripts/normalize_note_macro_categories.py`` — both are one-off repairs a
practice may want to review first, not schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "17559b3b70d4"
down_revision = "47371579152e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("progress_notes", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column(
        "progress_notes",
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("progress_notes", "updated_by")
    op.drop_column("progress_notes", "updated_at")
