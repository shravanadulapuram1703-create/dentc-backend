"""Backfill ``users.is_legacy_user`` for migrated accounts.

The Denticon→PMS migration created user rows but left ``is_legacy_user`` at its
default (``False``), so ``POST /auth/legacy-user/verify`` reports every migrated
user as not eligible to activate. This one-time backfill flags the migrated users
so the legacy-activation flow works.

Discriminator: a migrated user is one with ``must_change_password = True`` — set by
the migration and never set by the new-platform signup flow (which creates admins
who already know their password). Fresh signup users keep ``is_legacy_user=False``.

Idempotent and safe to re-run: only flips rows that still need it
(``must_change_password=True`` AND ``is_legacy_user=False`` AND
``legacy_activation_completed=False``). Already-activated users are never touched.

    python -m scripts.backfill_legacy_users --dry-run        # preview only
    python -m scripts.backfill_legacy_users                  # apply (all tenants)
    python -m scripts.backfill_legacy_users --tenant 1       # scope to one tenant
"""

from __future__ import annotations

import argparse

from sqlalchemy import select, update

from app.db.models import User
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Flag migrated users as legacy users.")
    parser.add_argument("--tenant", type=int, default=None, help="Scope to one tenant_id.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without writing."
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        conditions = [
            User.must_change_password.is_(True),
            User.is_legacy_user.is_(False),
            User.legacy_activation_completed.is_(False),
        ]
        if args.tenant is not None:
            conditions.append(User.tenant_id == args.tenant)

        rows = db.execute(
            select(User.id, User.username, User.email, User.tenant_id).where(*conditions)
        ).all()

        if not rows:
            print("Nothing to backfill — no eligible migrated users found.")
            return

        print(f"{len(rows)} user(s) will be flagged is_legacy_user=True:")
        for r in rows[:20]:
            print(f"  - id={r.id} tenant={r.tenant_id} {r.username} <{r.email}>")
        if len(rows) > 20:
            print(f"  … and {len(rows) - 20} more")

        if args.dry_run:
            print("\n[dry-run] No changes written.")
            return

        result = db.execute(update(User).where(*conditions).values(is_legacy_user=True))
        db.commit()
        print(f"\nDone. {result.rowcount} user(s) updated.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
