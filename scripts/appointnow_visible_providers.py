"""Curate which providers an office offers on its public AppointNow page (AN-18).

``providers.visible_in_appointnow`` is **opt-in** since Alembic ``431b5da5630e``
(with the old opt-out default MOON exposed 91 providers, test rows included).
Provider Setup toggles the flag per row; this script does it in bulk::

    python -m scripts.appointnow_visible_providers --office MOON --list
    python -m scripts.appointnow_visible_providers --office MOON --set PRV-181,PRV-204
    python -m scripts.appointnow_visible_providers --office MOON --add PRV-210
    python -m scripts.appointnow_visible_providers --office MOON --remove PRV-181
    python -m scripts.appointnow_visible_providers --office MOON --clear

``--set`` makes the list *exactly* those ids (everything else in the office is
turned off); ``--add`` / ``--remove`` adjust it; ``--clear`` turns every provider
off, after which the public page books "any provider" against chair capacity
and staff pick the provider on approve.
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select

from app.db.models import Office, Provider
from app.db.session import SessionLocal


def _ids(value: str | None) -> set[str]:
    return {v.strip() for v in (value or "").split(",") if v.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate AppointNow-visible providers (AN-18)")
    parser.add_argument("--office", required=True, help="office_code (e.g. MOON)")
    parser.add_argument("--list", action="store_true", help="Print the office's providers + flag")
    parser.add_argument("--set", dest="set_ids", help="Comma-separated provider ids to make the exact visible set")
    parser.add_argument("--add", dest="add_ids", help="Comma-separated provider ids to turn on")
    parser.add_argument("--remove", dest="remove_ids", help="Comma-separated provider ids to turn off")
    parser.add_argument("--clear", action="store_true", help="Turn every provider off")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        office = db.execute(
            select(Office).where(func.lower(Office.office_code) == args.office.strip().lower())
        ).scalar_one_or_none()
        if office is None:
            raise SystemExit(f"office '{args.office}' not found")
        providers = list(
            db.execute(
                select(Provider)
                .where(Provider.office_id == office.id, Provider.tenant_id == office.tenant_id)
                .order_by(Provider.name.asc())
            ).scalars().all()
        )
        by_id = {p.id: p for p in providers}

        wanted_on = _ids(args.set_ids) | _ids(args.add_ids)
        wanted_off = _ids(args.remove_ids)
        unknown = (wanted_on | wanted_off) - set(by_id)
        if unknown:
            raise SystemExit(f"not providers of {office.office_code}: {sorted(unknown)}")

        changed = 0
        for p in providers:
            if args.clear or args.set_ids is not None:
                target = p.id in wanted_on
            elif p.id in wanted_on:
                target = True
            elif p.id in wanted_off:
                target = False
            else:
                continue
            if bool(p.visible_in_appointnow) != target:
                p.visible_in_appointnow = target
                changed += 1
        if changed:
            db.commit()

        if args.list or changed or args.clear:
            print(f"{office.office_code} ({office.name}) — {changed} changed")
            for p in providers:
                flag = "ON " if p.visible_in_appointnow else "off"
                active = "" if p.is_active else "  [inactive]"
                print(f"  {flag}  {p.id:<12} {p.name}{active}")
            print(f"visible: {sum(1 for p in providers if p.visible_in_appointnow)} / {len(providers)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
