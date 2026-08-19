"""Seed the office <-> letter-template assignment join (LTR-7).

``GET /offices/{id}/letter-templates`` returned ``[]`` for every office because
``office_letter_templates`` was never populated by the migration — the legacy
export carries no per-office letter assignment.

The API answer to that is documented and shipped:
**unassigned = the whole tenant catalog** (see
``GET /offices/{id}/letter-templates/effective``). This script is the other half
— it materialises an explicit assignment for offices that want to curate a
shorter list, so the Letters dialog stops showing all 153 templates.

    # what would happen, nothing written
    python -m scripts.seed_office_letter_templates --tenant 1 --dry-run

    # assign the full active catalog to every office of tenant 1
    python -m scripts.seed_office_letter_templates --tenant 1

    # only the consent + financial groups, only two offices
    python -m scripts.seed_office_letter_templates --tenant 1 --letter-type C --letter-type F \\
        --office 2 --office 9

Idempotent: rows already present are left alone (the table has a unique on
``(office_id, letter_template_id)``). Offices that already carry an assignment
are skipped unless ``--replace`` is given, so this never silently undoes curation.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.db.models import LetterTemplate, Office, OfficeLetterTemplate, Tenant
from app.db.session import SessionLocal


def seed_for_tenant(
    db,  # noqa: ANN001
    tenant_id: int,
    *,
    office_ids: list[int] | None,
    letter_types: list[str] | None,
    include_inactive: bool,
    replace: bool,
    dry_run: bool,
) -> tuple[int, int]:
    """Return ``(assignments_added, offices_touched)``."""
    tpl_stmt = select(LetterTemplate.id).where(LetterTemplate.tenant_id == tenant_id)
    if not include_inactive:
        tpl_stmt = tpl_stmt.where(LetterTemplate.is_active.is_(True))
    if letter_types:
        tpl_stmt = tpl_stmt.where(LetterTemplate.letter_type.in_(letter_types))
    template_ids = list(db.execute(tpl_stmt).scalars().all())
    if not template_ids:
        print(f"  tenant {tenant_id}: no matching letter templates, nothing to do")
        return 0, 0

    off_stmt = select(Office.id).where(Office.tenant_id == tenant_id, Office.is_active.is_(True))
    if office_ids:
        off_stmt = off_stmt.where(Office.id.in_(office_ids))
    offices = list(db.execute(off_stmt).scalars().all())

    added = touched = 0
    for office_id in offices:
        existing = set(db.execute(
            select(OfficeLetterTemplate.letter_template_id).where(
                OfficeLetterTemplate.office_id == office_id
            )
        ).scalars().all())
        if existing and not replace:
            print(f"  office {office_id}: already has {len(existing)} assignment(s), skipping")
            continue
        if replace:
            for row in db.execute(
                select(OfficeLetterTemplate).where(
                    OfficeLetterTemplate.office_id == office_id,
                    OfficeLetterTemplate.letter_template_id.not_in(template_ids),
                )
            ).scalars():
                if not dry_run:
                    db.delete(row)

        missing = [t for t in template_ids if t not in existing]
        if not missing:
            continue
        touched += 1
        added += len(missing)
        if not dry_run:
            for template_id in missing:
                db.add(OfficeLetterTemplate(
                    tenant_id=tenant_id, office_id=office_id, letter_template_id=template_id,
                ))
        print(f"  office {office_id}: +{len(missing)} letter template(s)")

    if not dry_run:
        db.commit()
    return added, touched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all active)")
    parser.add_argument("--office", type=int, action="append", dest="offices",
                        help="Restrict to this office id (repeatable)")
    parser.add_argument("--letter-type", action="append", dest="letter_types",
                        help="Restrict to this letter_type code, e.g. C (repeatable)")
    parser.add_argument("--include-inactive", action="store_true",
                        help="Also assign templates with is_active = false")
    parser.add_argument("--replace", action="store_true",
                        help="Overwrite an office's existing assignment instead of skipping it")
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        tenant_ids = (
            [args.tenant] if args.tenant is not None
            else list(db.execute(select(Tenant.id).where(Tenant.is_active.is_(True))).scalars().all())
        )
        for tid in tenant_ids:
            print(f"tenant {tid}:")
            added, touched = seed_for_tenant(
                db, tid,
                office_ids=args.offices, letter_types=args.letter_types,
                include_inactive=args.include_inactive, replace=args.replace,
                dry_run=args.dry_run,
            )
            verb = "would add" if args.dry_run else "added"
            print(f"  {verb} {added} assignment(s) across {touched} office(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
