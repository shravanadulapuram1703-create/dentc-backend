"""Office Setup new-office QA pass (OFF-QA-2/5/8).

* OFF-QA-5: ``office_integrations`` gains the verify-email round trip columns
  (code sha256 + sent/expiry/attempts + ``service_email_verified_at``).
* OFF-QA-2: canonical casing of the Office Setup vocabularies already stored —
  ``office_statement_settings.logo_option``/``address_source`` lowercase,
  ``account_holidays.holiday_type``/``status`` uppercase (older frontend builds
  wrote ``Custom``/``Federal`` and ``OFFICE``/``CUSTOM``). The write schemas now
  refuse anything outside the vocabulary.
* OFF-QA-8: ``office_advanced_settings.place_of_service`` words the old form
  stored become CMS POS codes (office->11, hospital->22, nursing_home->32,
  school->03, other->99).

Not done here, deliberately (see the response doc): a DB unique constraint on
``(tenant_id, upper(short_id))`` — the dev DB holds a real ``MOON`` pair (offices
1 and 4) that needs a practice decision first; the write path 409s new clashes
meanwhile. ``office_code`` stays globally unique: AppointNow resolves the
anonymous booking page from it without a tenant.

Revision ID: 8d1ef924bb92
Revises: a28e9c1d0b7f
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "8d1ef924bb92"
down_revision = "a28e9c1d0b7f"
branch_labels = None
depends_on = None

_POS = {"office": "11", "hospital": "22", "nursing_home": "32", "school": "03", "other": "99"}


def upgrade() -> None:
    with op.batch_alter_table("office_integrations") as b:
        b.add_column(sa.Column("service_email_verified_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("service_email_verification_hash", sa.String(64), nullable=True))
        b.add_column(sa.Column("service_email_verification_sent_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("service_email_verification_expires_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("service_email_verification_attempts", sa.Integer(),
                               nullable=False, server_default="0"))

    op.execute("UPDATE office_statement_settings SET logo_option = lower(trim(logo_option)) "
               "WHERE logo_option IS NOT NULL AND logo_option <> lower(trim(logo_option))")
    op.execute("UPDATE office_statement_settings SET address_source = lower(trim(address_source)) "
               "WHERE address_source IS NOT NULL AND address_source <> lower(trim(address_source))")
    op.execute("UPDATE account_holidays SET holiday_type = upper(trim(holiday_type)) "
               "WHERE holiday_type IS NOT NULL AND holiday_type <> upper(trim(holiday_type))")
    op.execute("UPDATE account_holidays SET status = upper(trim(status)) "
               "WHERE status IS NOT NULL AND status <> upper(trim(status))")
    op.execute("UPDATE account_holidays SET status = 'HALF_DAY' "
               "WHERE status IN ('HALF DAY', 'HALFDAY', 'HALF-DAY')")
    for word, code in _POS.items():
        op.execute(sa.text(
            "UPDATE office_advanced_settings SET place_of_service = :code "
            "WHERE lower(trim(place_of_service)) = :word"
        ).bindparams(code=code, word=word))


def downgrade() -> None:
    # The casing/POS normalisation is not reversible (and needs no reversal).
    with op.batch_alter_table("office_integrations") as b:
        b.drop_column("service_email_verification_attempts")
        b.drop_column("service_email_verification_expires_at")
        b.drop_column("service_email_verification_sent_at")
        b.drop_column("service_email_verification_hash")
        b.drop_column("service_email_verified_at")
