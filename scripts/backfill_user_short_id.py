"""Backfill ``users.short_id`` from the ``providers`` table (by name match).

Resolves the providers-mapping option of the Users structural-fields work
(docs/users/users_missing_fields_devreport.md, gap #1).

The providers table does NOT hold one clean short_id per person — the same name
appears on many provider rows with different short_ids, and several users can
share a name. ``users.short_id`` is unique-per-tenant, so a blind copy would both
pick an arbitrary code and violate ``uq_users_tenant_short_id``. This script
therefore only writes the **safe, unambiguous, collision-free** subset:

  A user U in tenant T is assigned provider short_id S iff
    1. U.first_name+last_name matches exactly one provider name in T that carries
       a short_id, and all such matches resolve to a SINGLE distinct short_id S, and
    2. S maps to exactly one user in T (no two users would receive the same code).

Users that are ambiguous (>1 candidate code) or colliding (code wanted by >1 user)
are skipped and listed. Idempotent: only fills rows whose short_id is currently
NULL; re-running after data cleanup picks up newly-resolvable users.

    python -m scripts.backfill_user_short_id            # dry-run (report only)
    python -m scripts.backfill_user_short_id --apply    # write the safe subset
    python -m scripts.backfill_user_short_id --apply --tenant 1
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import text

from app.db.session import SessionLocal

_MATCH_SQL = text(
    """
    select u.tenant_id, u.id as user_id, u.username, p.short_id
    from users u
    join providers p
      on p.tenant_id = u.tenant_id
     and lower(trim(p.name)) = lower(trim(u.first_name || ' ' || u.last_name))
    where p.short_id is not null and p.short_id <> ''
      and u.first_name is not null and u.last_name is not null
      and (u.short_id is null or u.short_id = '')
      and (:tenant is null or u.tenant_id = :tenant)
    """
)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument("--tenant", type=int, default=None, help="limit to one tenant_id")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = db.execute(_MATCH_SQL, {"tenant": args.tenant}).all()
        by_user: dict[tuple[int, int], set[str]] = defaultdict(set)
        by_code: dict[tuple[int, str], set[int]] = defaultdict(set)
        usernames: dict[tuple[int, int], str] = {}
        for r in rows:
            by_user[(r.tenant_id, r.user_id)].add(r.short_id)
            by_code[(r.tenant_id, r.short_id)].add(r.user_id)
            usernames[(r.tenant_id, r.user_id)] = r.username

        safe: list[tuple[int, int, str]] = []
        ambiguous: list[tuple[int, int, list[str]]] = []
        for (t, uid), codes in by_user.items():
            if len(codes) != 1:
                ambiguous.append((t, uid, sorted(codes)))
                continue
            code = next(iter(codes))
            if len(by_code[(t, code)]) != 1:  # collision: >1 user wants this code
                ambiguous.append((t, uid, [f"{code} (collides with users "
                                           f"{sorted(by_code[(t, code)])})"]))
                continue
            safe.append((t, uid, code))

        print(f"candidates (users matched to a provider name): {len(by_user)}")
        print(f"  safe / unambiguous / no-collision        : {len(safe)}")
        print(f"  skipped (ambiguous or colliding)          : {len(ambiguous)}")
        print()
        for t, uid, code in sorted(safe):
            print(f"  [fill] tenant {t} user {uid} ({usernames[(t, uid)]}) -> {code!r}")
        if ambiguous:
            print("\n  --- skipped ---")
            for t, uid, why in sorted(ambiguous):
                print(f"  [skip] tenant {t} user {uid} ({usernames[(t, uid)]}): {why}")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to write the safe subset.")
            return

        for t, uid, code in safe:
            db.execute(
                text("update users set short_id = :c where id = :i and short_id is null"),
                {"c": code, "i": uid},
            )
        db.commit()
        print(f"\nApplied {len(safe)} short_id assignments.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
