"""Curate the access-rights catalog (ACCESS-RIGHTS handover A1/A2/A3 + C2).

Data migration, not schema. Transforms the ``permissions`` catalog from the
529-row legacy Denticon import into the curated **363**-row DentC set:

* **A1** delete 210 obsolete codes; **C2** cascade the delete to
  ``user_group_rights`` so no group references a dead code.
* **A2** insert 44 new codes (Charting / Imaging / AppointNow / Messaging /
  Dashboard + Patient/Transactions/Setup/Help/General gaps).
* **A3** rename 4 surviving labels (the ``code`` is never touched).

The data + logic live once in ``app.services.access_rights_catalog`` so this
migration and ``scripts.seed_permissions`` cannot drift. ``apply_curation`` is
idempotent, so this is safe on a catalog that was already curated (e.g. re-seeded).

``downgrade`` restores the removed catalog rows (their prior group assignments are
not recoverable) and reverts the renames — best-effort, per that module's contract.

Revision ID: 8e4a6a8e5ab0
Revises: f811e916183e
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from alembic import op

from app.services import access_rights_catalog

revision = "8e4a6a8e5ab0"
down_revision = "f811e916183e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # commit=False: only flush; Alembic owns and commits the migration transaction
    # (matches how the other data migrations run their DML).
    with Session(bind=op.get_bind()) as session:
        access_rights_catalog.apply_curation(session, commit=False)


def downgrade() -> None:
    with Session(bind=op.get_bind()) as session:
        access_rights_catalog.revert_curation(session, commit=False)
