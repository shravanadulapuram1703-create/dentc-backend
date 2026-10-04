"""Time Clock backend gaps (TC-BE-1…14).

Schema
* ``time_clock_entries`` + ``entry_type`` (TC-BE-12), ``source`` (TC-BE-1),
  ``clock_basis`` (TC-BE-9), ``notes``, ``created_by``, the edit summary
  (``updated_at``/``updated_by``/``is_edited``/``original_clock_in|out``/
  ``edit_reason``), soft delete (``is_active``/``deleted_at|by``/
  ``delete_reason``) (TC-BE-6) and the auto-close flags (TC-BE-10).
* ``time_clock_entry_edits`` (TC-BE-6), ``time_clock_periods`` (TC-BE-14),
  ``time_clock_settings`` (TC-BE-7/10).
* ``user_time_clock_config`` + per-user overtime thresholds / week start (TC-BE-7).
* Indexes: ``(tenant_id, clock_in)`` (TC-BE-4) and the **partial unique**
  ``(tenant_id, user_id) WHERE <open shift>`` (TC-BE-2).

Data (must precede the unique index, so it lives here rather than in a script —
a script leaves a window in which the index cannot be created)
* Every migrated row (``legacy_id`` set) is ``source='legacy'``,
  ``clock_basis='wall_clock'`` — the Denticon export stored the office wall clock
  with a ``Z``. ``scripts/backfill_time_clock_utc.py`` converts them later.
* **TC-BE-10**: 857 open rows on the dev DB, 77 users with more than one. Every
  open row is flagged ``auto_closed`` / ``missing_clock_out`` *except* each
  user's newest open row when it began within the last 20 hours (a shift that
  may genuinely be running). Nothing invents a clock-out time.
* ``user_time_clock_config.overtime_method`` folded onto the TC-BE-7 enum.

Revision ID: 1745e318c65a
Revises: 8e4a6a8e5ab0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "1745e318c65a"
down_revision = "8e4a6a8e5ab0"
branch_labels = None
depends_on = None

_OPEN_PG = "clock_out IS NULL AND is_active AND NOT auto_closed"
_OPEN_SQLITE = "clock_out IS NULL AND is_active = 1 AND auto_closed = 0"


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    false = sa.text("false")
    true = sa.text("true")
    with op.batch_alter_table("time_clock_entries") as b:
        b.add_column(sa.Column("entry_type", sa.String(20), nullable=False, server_default="work"))
        b.add_column(sa.Column("source", sa.String(20), nullable=False, server_default="manual"))
        b.add_column(sa.Column("clock_basis", sa.String(20), nullable=False, server_default="utc"))
        b.add_column(sa.Column("notes", sa.String(500)))
        b.add_column(sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")))
        b.add_column(sa.Column("updated_at", sa.DateTime))
        b.add_column(sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")))
        b.add_column(sa.Column("is_edited", sa.Boolean, nullable=False, server_default=false))
        b.add_column(sa.Column("original_clock_in", sa.DateTime))
        b.add_column(sa.Column("original_clock_out", sa.DateTime))
        b.add_column(sa.Column("edit_reason", sa.String(500)))
        b.add_column(sa.Column("is_active", sa.Boolean, nullable=False, server_default=true))
        b.add_column(sa.Column("deleted_at", sa.DateTime))
        b.add_column(sa.Column("deleted_by", sa.Integer, sa.ForeignKey("users.id")))
        b.add_column(sa.Column("delete_reason", sa.String(500)))
        b.add_column(sa.Column("auto_closed", sa.Boolean, nullable=False, server_default=false))
        b.add_column(sa.Column("auto_closed_at", sa.DateTime))
        b.add_column(sa.Column("auto_close_reason", sa.String(50)))

    # TC-BE-9: the migrated rows are office wall-clock values.
    op.execute(
        "UPDATE time_clock_entries SET source = 'legacy', clock_basis = 'wall_clock' "
        "WHERE legacy_id IS NOT NULL"
    )

    # TC-BE-10: flag every open row except each user's newest one when it may
    # still be running (began within 20 h). ``ranked`` is computed before any
    # row changes, so the newest row per user is judged on the original data.
    if _is_pg():
        op.execute(
            """
            WITH ranked AS (
                SELECT id, clock_in,
                       row_number() OVER (PARTITION BY tenant_id, user_id
                                          ORDER BY clock_in DESC, id DESC) AS rn
                FROM time_clock_entries
                WHERE clock_out IS NULL
            )
            UPDATE time_clock_entries t
               SET auto_closed = true,
                   auto_closed_at = (now() AT TIME ZONE 'utc'),
                   auto_close_reason = 'missing_clock_out'
              FROM ranked r
             WHERE t.id = r.id
               AND (r.rn > 1 OR r.clock_in < (now() AT TIME ZONE 'utc') - interval '20 hours')
            """
        )
    else:  # SQLite (tests build from metadata; kept for completeness)
        op.execute(
            """
            UPDATE time_clock_entries SET auto_closed = 1, auto_close_reason = 'missing_clock_out',
                   auto_closed_at = CURRENT_TIMESTAMP
             WHERE clock_out IS NULL AND (
                   clock_in < datetime('now', '-20 hours')
                   OR id <> (SELECT t2.id FROM time_clock_entries t2
                              WHERE t2.tenant_id = time_clock_entries.tenant_id
                                AND t2.user_id = time_clock_entries.user_id
                                AND t2.clock_out IS NULL
                              ORDER BY t2.clock_in DESC, t2.id DESC LIMIT 1))
            """
        )

    # TC-BE-3: closed rows always carry their derived total.
    if _is_pg():
        op.execute(
            "UPDATE time_clock_entries "
            "SET total_hours = round((extract(epoch FROM clock_out - clock_in) / 3600.0)::numeric, 2) "
            "WHERE clock_out IS NOT NULL AND total_hours IS NULL AND clock_out >= clock_in"
        )

    op.create_index("ix_time_clock_entries_tenant_clock_in", "time_clock_entries", ["tenant_id", "clock_in"])
    op.create_index(
        "uq_time_clock_entries_open_shift", "time_clock_entries", ["tenant_id", "user_id"],
        unique=True, postgresql_where=sa.text(_OPEN_PG), sqlite_where=sa.text(_OPEN_SQLITE),
    )

    op.create_table(
        "time_clock_entry_edits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("entry_id", sa.Integer, sa.ForeignKey("time_clock_entries.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("edited_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("edited_at", sa.DateTime, nullable=False),
        sa.Column("edit_reason", sa.String(500)),
        sa.Column("original_clock_in", sa.DateTime),
        sa.Column("original_clock_out", sa.DateTime),
        sa.Column("new_clock_in", sa.DateTime),
        sa.Column("new_clock_out", sa.DateTime),
        sa.Column("changes", sa.JSON),
    )
    op.create_index("ix_time_clock_entry_edits_tenant_id", "time_clock_entry_edits", ["tenant_id"])
    op.create_index("ix_time_clock_entry_edits_entry_id", "time_clock_entry_edits", ["entry_id"])

    op.create_table(
        "time_clock_periods",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("office_id", sa.Integer, sa.ForeignKey("offices.id")),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("locked", sa.Boolean, nullable=False, server_default=false),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime),
        sa.Column("locked_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("locked_at", sa.DateTime),
        sa.Column("notes", sa.Text),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("ix_time_clock_periods_tenant_id", "time_clock_periods", ["tenant_id"])

    op.create_table(
        "time_clock_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("overtime_method", sa.String(20), nullable=False, server_default="weekly"),
        sa.Column("daily_threshold_hours", sa.Numeric(5, 2), nullable=False, server_default="8"),
        sa.Column("weekly_threshold_hours", sa.Numeric(5, 2), nullable=False, server_default="40"),
        sa.Column("week_start_day", sa.String(10), nullable=False, server_default="sunday"),
        sa.Column("overtime_rate", sa.Numeric(5, 2), nullable=False, server_default="1.5"),
        sa.Column("auto_close_after_hours", sa.Integer, nullable=False, server_default="20"),
        sa.Column("auto_close_policy", sa.String(20), nullable=False, server_default="flag"),
        sa.Column("require_edit_reason", sa.Boolean, nullable=False, server_default=false),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_index("uq_time_clock_settings_tenant", "time_clock_settings", ["tenant_id"], unique=True)

    with op.batch_alter_table("user_time_clock_config") as b:
        b.add_column(sa.Column("daily_threshold_hours", sa.Numeric(5, 2)))
        b.add_column(sa.Column("weekly_threshold_hours", sa.Numeric(5, 2)))
        b.add_column(sa.Column("week_start_day", sa.String(10)))
    # TC-BE-7: fold the pre-enum spellings (dev DB: weekly_40 x1, daily x2, NULL x13).
    for old, new in (("weekly_40", "weekly"), ("daily_8", "daily"), ("california", "daily_weekly")):
        op.execute(
            sa.text("UPDATE user_time_clock_config SET overtime_method = :new WHERE overtime_method = :old")
            .bindparams(old=old, new=new)
        )


def downgrade() -> None:
    with op.batch_alter_table("user_time_clock_config") as b:
        b.drop_column("week_start_day")
        b.drop_column("weekly_threshold_hours")
        b.drop_column("daily_threshold_hours")
    op.drop_index("uq_time_clock_settings_tenant", table_name="time_clock_settings")
    op.drop_table("time_clock_settings")
    op.drop_index("ix_time_clock_periods_tenant_id", table_name="time_clock_periods")
    op.drop_table("time_clock_periods")
    op.drop_index("ix_time_clock_entry_edits_entry_id", table_name="time_clock_entry_edits")
    op.drop_index("ix_time_clock_entry_edits_tenant_id", table_name="time_clock_entry_edits")
    op.drop_table("time_clock_entry_edits")
    op.drop_index("uq_time_clock_entries_open_shift", table_name="time_clock_entries")
    op.drop_index("ix_time_clock_entries_tenant_clock_in", table_name="time_clock_entries")
    # Soft-deleted rows were deleted on purpose; dropping is_active would bring
    # them back, so they go now.
    op.execute("DELETE FROM time_clock_entries WHERE is_active = false")
    with op.batch_alter_table("time_clock_entries") as b:
        for col in ("auto_close_reason", "auto_closed_at", "auto_closed", "delete_reason", "deleted_by",
                    "deleted_at", "is_active", "edit_reason", "original_clock_out", "original_clock_in",
                    "is_edited", "updated_by", "updated_at", "created_by", "notes", "clock_basis",
                    "source", "entry_type"):
            b.drop_column(col)
