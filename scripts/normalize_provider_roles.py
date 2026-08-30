"""Normalise the free-text ``providers.role`` column (PROV-3).

Why this exists
---------------
``providers.role`` is a plain ``varchar`` with no vocabulary behind it, so live
tenant 1 holds::

    dentist    78
    hygienist  16
    Dentist     2      <- casing
    Hygenist    1      <- misspelled
    staff       2

and ``specialty`` is blank on 96 of 97 rows. Every screen that needs "doctors
here, hygienists there" therefore had to normalise the column itself — the
frontend grew a ``providerKind()`` heuristic for exactly this — and a single
misspelling is enough to drop a hygienist out of the hygiene dropdown, or into
the treating-provider one.

The write path is fixed (``ProviderCRUD`` canonicalises ``role`` on create and
update) and the vocabulary is seeded as the ``provider_role`` definition group.
This script repairs the rows that were written before either existed.

What it will *not* do
---------------------
An unrecognised role is **left exactly as it is**, not forced into the nearest
canonical value. ``canonical_role`` only lower-cases and trims what it does not
recognise, and a practice may legitimately use a title this list has never heard
of — quietly relabelling someone's role is worse than an unfamiliar string. Such
rows are reported so they can be added to ``_ROLE_ALIASES`` if they turn out to
be variants.

Usage
-----
Dry-run by default::

    python -m scripts.normalize_provider_roles                 # report only
    python -m scripts.normalize_provider_roles --apply
    python -m scripts.normalize_provider_roles --apply --tenant 1
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Provider
from app.db.session import SessionLocal
from app.services.provider_directory_service import (
    PROVIDER_ROLES,
    canonical_role,
    provider_kind,
)


def run(session: Session, *, apply: bool, tenant_id: int | None) -> None:
    stmt = select(Provider)
    if tenant_id is not None:
        stmt = stmt.where(Provider.tenant_id == tenant_id)
    providers = session.execute(stmt).scalars().all()

    changes: Counter[tuple[str | None, str | None]] = Counter()
    unrecognised: Counter[str] = Counter()
    kinds: Counter[str] = Counter()

    for prov in providers:
        canon = canonical_role(prov.role)
        kinds[provider_kind(prov.role, prov.title) or "(unknown)"] += 1
        if canon not in PROVIDER_ROLES and canon is not None:
            unrecognised[canon] += 1
        if canon == prov.role:
            continue
        changes[(prov.role, canon)] += 1
        if apply:
            prov.role = canon

    if apply:
        session.commit()

    verb = "rewritten" if apply else "would be rewritten"
    total = sum(changes.values())
    print(f"providers scanned: {len(providers)}")
    print(f"  rows {verb}: {total}")
    for (before, after), count in sorted(changes.items(), key=lambda kv: -kv[1]):
        print(f"    {str(before)!r:<20} -> {str(after)!r:<14} {count}")

    if unrecognised:
        print("\n  roles outside the canonical vocabulary (left as written):")
        for role, count in unrecognised.most_common():
            print(f"    {role!r:<24} {count}")

    print("\n  resulting provider_kind split:")
    for kind, count in kinds.most_common():
        print(f"    {kind:<12} {count}")

    if not apply:
        print("\nDry run — nothing written. Re-run with --apply.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument("--tenant", type=int, help="restrict to one tenant")
    args = parser.parse_args()

    with SessionLocal() as session:
        run(session, apply=args.apply, tenant_id=args.tenant)


if __name__ == "__main__":
    main()
