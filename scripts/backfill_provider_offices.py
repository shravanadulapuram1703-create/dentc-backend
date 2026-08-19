"""Backfill the office↔provider assignment table (PROV-1).

``provider_offices`` is the many-to-many truth behind
``GET /offices/{id}/providers`` and behind office scoping on ``GET /providers``,
but the Denticon migration only carried each provider's *home* office
(``providers.office_id``) — so the join arrived effectively unseeded (1 row for
office 1, 0 for office 9, 1 inactive row for office 10, against 97 providers).

This reconstructs the real set from evidence already in the database:

1. ``providers.office_id``           — the legacy home office
2. ``patient_procedures``            — where the provider actually produced
3. ``appointments``                  — where the provider is actually scheduled
4. ``operatories.provider_id``       — the operatory's default provider

Sources 2–4 are historical usage, which is exactly what "this provider serves
this office" means in practice. Idempotent: existing links are left alone, so a
re-run only adds what is newly evidenced.

    python -m scripts.backfill_provider_offices              # all tenants
    python -m scripts.backfill_provider_offices --tenant 1   # one tenant
    python -m scripts.backfill_provider_offices --dry-run    # report only
    python -m scripts.backfill_provider_offices --home-only  # skip usage sources
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Appointment,
    Operatory,
    PatientProcedure,
    Provider,
    ProviderOffice,
)
from app.db.session import SessionLocal


def _tenant_providers(db: Session, tenant_id: int) -> dict[str, Provider]:
    return {
        p.id: p
        for p in db.execute(select(Provider).where(Provider.tenant_id == tenant_id)).scalars()
    }


def _evidenced_pairs(
    db: Session, provider_ids: set[str], *, home_only: bool
) -> set[tuple[str, int]]:
    """(provider_id, office_id) pairs this tenant's data actually supports."""
    pairs: set[tuple[str, int]] = set()
    if home_only or not provider_ids:
        return pairs
    sources = (
        (PatientProcedure.provider_id, PatientProcedure.office_id),  # produced here
        (Appointment.provider_id, Appointment.office_id),            # scheduled here
        (Operatory.provider_id, Operatory.office_id),                # default op provider
    )
    for provider_col, office_col in sources:
        rows = db.execute(
            select(provider_col, office_col)
            .where(provider_col.in_(provider_ids), office_col.is_not(None))
            .group_by(provider_col, office_col)
        ).all()
        pairs.update((provider_id, office_id) for provider_id, office_id in rows)
    return pairs


def backfill(
    db: Session, tenant_id: int, *, dry_run: bool = False, home_only: bool = False
) -> tuple[int, int]:
    """Add the missing links for one tenant. Returns (added, already_present)."""
    providers = _tenant_providers(db, tenant_id)
    if not providers:
        return 0, 0

    existing = {
        (link.provider_id, link.office_id)
        for link in db.execute(
            select(ProviderOffice).where(ProviderOffice.tenant_id == tenant_id)
        ).scalars()
    }

    wanted = {
        (p.id, p.office_id) for p in providers.values() if p.office_id is not None
    }
    wanted |= _evidenced_pairs(db, set(providers), home_only=home_only)
    # Never invent a link for a provider outside this tenant.
    wanted = {(pid, oid) for pid, oid in wanted if pid in providers}

    missing = sorted(wanted - existing)
    if missing and not dry_run:
        db.add_all(
            ProviderOffice(tenant_id=tenant_id, provider_id=pid, office_id=oid)
            for pid, oid in missing
        )
        db.commit()
    return len(missing), len(wanted & existing)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing")
    parser.add_argument(
        "--home-only", action="store_true", help="Seed from providers.office_id only"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.tenant is not None:
            tenant_ids = [args.tenant]
        else:
            tenant_ids = [
                t for (t,) in db.execute(
                    select(Provider.tenant_id).group_by(Provider.tenant_id)
                ).all()
            ]
        total_added = 0
        for tenant_id in tenant_ids:
            added, present = backfill(
                db, tenant_id, dry_run=args.dry_run, home_only=args.home_only
            )
            total_added += added
            print(f"tenant {tenant_id}: +{added} link(s), {present} already present")
        verb = "would add" if args.dry_run else "added"
        print(f"{verb} {total_added} provider_offices link(s)")


if __name__ == "__main__":
    main()
