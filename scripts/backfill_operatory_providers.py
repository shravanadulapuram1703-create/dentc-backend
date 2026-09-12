"""Derive the provider <-> operatory defaults from booking history (PLAN-APPT-4).

Two columns, both unseeded on the migrated data (office 1: all five operatories
have ``provider_id`` NULL):

* ``operatories.provider_id``        — the column-header provider of a chair
* ``providers.default_operatory_id`` — the chair a booking for a provider opens on

Neither was exported by Denticon, but the appointment history says who actually
works where: for every (office, operatory) the provider with the most
non-cancelled appointments is that chair's provider, and for every (provider,
office) the chair they were booked in most often is their default. A pair is
only written when it clears ``--min-share`` (default 60 %) of that chair's /
provider's appointments **and** ``--min-count`` appointments back it (default
10) — a chair four providers rotate through has no default, and two historical
bookings are not evidence of one; writing a wrong default would put every
booking in the wrong column.

Dry run on the migrated tenant (2026-09-10): 25 chairs + 1 provider default
clear both bars; 15 pairs rest on fewer than 10 appointments and 19 are shared
(no 60 % majority). Left unapplied — the practice should confirm the printed
pairs before ``--apply``.

Dry-run by default; NULL-only unless ``--overwrite``.

    python -m scripts.backfill_operatory_providers                 # report
    python -m scripts.backfill_operatory_providers --apply
    python -m scripts.backfill_operatory_providers --apply --tenant 1 --min-share 0.5
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Appointment, Office, Operatory, Provider
from app.db.session import SessionLocal


def _history(db: Session, tenant_id: int) -> list[tuple[int, str, str, int]]:
    """(office_id, operatory_id, provider_id, n) over live, non-cancelled appointments."""
    return db.execute(
        select(Appointment.office_id, Appointment.operatory_id, Appointment.provider_id, func.count())
        .join(Office, Office.id == Appointment.office_id)
        .where(
            Office.tenant_id == tenant_id,
            Appointment.operatory_id.is_not(None),
            Appointment.provider_id.is_not(None),
            Appointment.is_archived.is_(False),
            Appointment.is_cancelled.is_(False),
        )
        .group_by(Appointment.office_id, Appointment.operatory_id, Appointment.provider_id)
    ).all()


def run(
    db: Session, *, tenant_id: int, apply: bool, overwrite: bool, min_share: float, min_count: int = 10,
) -> dict:
    per_chair: dict[str, Counter] = defaultdict(Counter)
    per_provider_office: dict[tuple[str, int], Counter] = defaultdict(Counter)
    for office_id, op_id, prov_id, n in _history(db, tenant_id):
        per_chair[op_id][prov_id] += n
        per_provider_office[(prov_id, office_id)][op_id] += n

    stats = Counter()
    for op_id, counts in per_chair.items():
        op = db.get(Operatory, op_id)
        if op is None:
            continue
        prov_id, n = counts.most_common(1)[0]
        total = sum(counts.values())
        share = n / total
        if total < min_count:
            stats["operatory_too_few"] += 1
            continue
        if share < min_share:
            stats["operatory_ambiguous"] += 1
            continue
        if op.provider_id and not overwrite:
            stats["operatory_kept"] += 1
            continue
        stats["operatory_set"] += 1
        print(f"  operatory {op_id} -> {prov_id} ({share:.0%} of {sum(counts.values())})")
        if apply:
            op.provider_id = prov_id

    # A provider serves several offices; the default chair is the one in the
    # provider's home office (providers.office_id) — that is the office New Appt
    # opens by default.
    for (prov_id, office_id), counts in per_provider_office.items():
        prov = db.get(Provider, prov_id)
        if prov is None or prov.office_id != office_id:
            continue
        op_id, n = counts.most_common(1)[0]
        total = sum(counts.values())
        share = n / total
        if total < min_count:
            stats["provider_too_few"] += 1
            continue
        if share < min_share:
            stats["provider_ambiguous"] += 1
            continue
        if prov.default_operatory_id and not overwrite:
            stats["provider_kept"] += 1
            continue
        stats["provider_set"] += 1
        print(f"  provider {prov_id} default operatory -> {op_id} ({share:.0%} of {sum(counts.values())})")
        if apply:
            prov.default_operatory_id = op_id
    if apply:
        db.commit()
    return dict(stats)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tenant", type=int, default=None)
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--overwrite", action="store_true", help="replace values already set")
    ap.add_argument("--min-share", type=float, default=0.6)
    ap.add_argument("--min-count", type=int, default=10, help="minimum appointments backing a pair")
    args = ap.parse_args()
    with SessionLocal() as db:
        tenants = [args.tenant] if args.tenant is not None else list(
            db.execute(select(Office.tenant_id).distinct().order_by(Office.tenant_id)).scalars()
        )
        for tid in tenants:
            print(f"tenant {tid}:")
            stats = run(db, tenant_id=tid, apply=args.apply, overwrite=args.overwrite,
                        min_share=args.min_share, min_count=args.min_count)
            print(f"  {stats or 'no history'}{'' if args.apply else ' (dry run)'}")


if __name__ == "__main__":
    main()
