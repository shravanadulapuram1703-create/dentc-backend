"""Seed / repair the ``definitions`` groups behind the INSURANCE DETAILS wizard.

PLAN-DTL-4/6 — the five catalogues the wizard's dropdowns bind to
(``FREQUENCYLIMITATIONS``, ``DEFCOVERAGE``, ``INSLIMITATIONS``, ``PLANTYPE``,
``PLANSUBTYPE``) exist on **one** tenant — the migrated one — because they came
in through ``s43_definitions`` from the Denticon export, not from a seeder. On
the other 42 tenants the wizard has empty pickers and no default coverage
table. The canonical lists live once, in ``app.services.insurance_plan_service``
(the same constants ``GET /insurance-plans/metadata`` falls back to), and this
script writes them to every tenant that lacks them.

It also **patches** existing FREQUENCYLIMITATIONS rows with ``sort_order`` =
the frequency ordinal (``insurance_coverage_rules.freq_limit`` is a 1-based
index into that list, and the migrated rows carried no ordinal at all), and
fills ``DEFCOVERAGE.key2`` (the default coverage %) where it is blank.

The four PLAN-tab vocabularies (``fees_to_print`` / ``claim_option`` /
``form_to_print`` / ``network_type``) are seeded as snake_case groups the same
way the Account-Information dropdowns are, so a practice can extend them.

Idempotent; add-only for new rows (a label the practice edited is never
overwritten); ``sort_order``/``key2`` are filled only where NULL unless
``--overwrite``. Dry run by default.

    python -m scripts.seed_insurance_plan_definitions              # report
    python -m scripts.seed_insurance_plan_definitions --apply
    python -m scripts.seed_insurance_plan_definitions --apply --tenant 1
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Definition, Tenant
from app.db.session import SessionLocal
from app.services.insurance_plan_service import (
    CODE_GROUPS,
    DEF_GROUP_CODE_GROUPS,
    DEF_GROUP_COVERAGE,
    DEF_GROUP_FREQUENCY,
    DEF_GROUP_PLAN_SUBTYPE,
    DEF_GROUP_PLAN_TYPE,
    DEFAULT_COVERAGE_TABLE,
    FREQUENCY_LIMITATIONS,
    PLAN_FIELD_OPTIONS,
    PLAN_SUBTYPES,
    PLAN_TYPES,
)


def _rows(db: Session, tenant_id: int, group_code: str) -> list[Definition]:
    return list(db.execute(
        select(Definition).where(
            Definition.tenant_id == tenant_id, Definition.group_code == group_code
        ).order_by(Definition.id)
    ).scalars())


def _ensure(
    db: Session, tenant_id: int, group_code: str, *,
    key1: str, description: str, key2: str | None, sort_order: int | None,
    existing_by_label: dict[str, Definition], existing_by_key: dict[str, Definition],
    match: str, apply: bool, overwrite: bool, counts: dict,
) -> None:
    if match == "label":
        row = existing_by_label.get(description.strip().lower())
    elif match == "key+label":
        # PLANSUBTYPE: "Aetna" exists under both PPO and HMO, so neither the
        # label nor the parent key identifies a row on its own.
        row = existing_by_label.get((key1, description.strip().lower()))
    else:
        row = existing_by_key.get(key1)
    if row is None:
        counts["added"] += 1
        if apply:
            db.add(Definition(
                tenant_id=tenant_id, group_code=group_code, key1=key1, key2=key2,
                description=description, sort_order=sort_order, is_active=True,
            ))
        return
    patched = False
    if sort_order is not None and (row.sort_order is None or overwrite) and row.sort_order != sort_order:
        if apply:
            row.sort_order = sort_order
        patched = True
    if key2 is not None and (not row.key2 or overwrite) and row.key2 != key2:
        if apply:
            row.key2 = key2
        patched = True
    if patched:
        counts["patched"] += 1


def seed_for_tenant(db: Session, tenant_id: int, *, apply: bool, overwrite: bool) -> dict:
    counts = {"added": 0, "patched": 0}

    def index(group_code: str):
        rows = _rows(db, tenant_id, group_code)
        by_label: dict[str, Definition] = {}
        by_key: dict[str, Definition] = {}
        for r in rows:
            by_label.setdefault((r.description or "").strip().lower(), r)
            by_key.setdefault((r.key1 or "").strip(), r)
        return by_label, by_key

    # Frequency ordinals: matched on label (key1 is the "Once"/"Twice" fragment).
    by_label, by_key = index(DEF_GROUP_FREQUENCY)
    for ordinal, label, key1, key2 in FREQUENCY_LIMITATIONS:
        _ensure(db, tenant_id, DEF_GROUP_FREQUENCY, key1=key1, description=label, key2=key2,
                sort_order=ordinal, existing_by_label=by_label, existing_by_key=by_key,
                match="label", apply=apply, overwrite=overwrite, counts=counts)

    # Default coverage table: key1 = category code, key2 = default %.
    by_label, by_key = index(DEF_GROUP_COVERAGE)
    for idx, (code, label, pct) in enumerate(DEFAULT_COVERAGE_TABLE):
        _ensure(db, tenant_id, DEF_GROUP_COVERAGE, key1=code, description=label, key2=str(pct),
                sort_order=idx, existing_by_label=by_label, existing_by_key=by_key,
                match="key", apply=apply, overwrite=overwrite, counts=counts)

    # Code groups (FREQ tab): key1 = code, key2 = "999" as the export has it.
    by_label, by_key = index(DEF_GROUP_CODE_GROUPS)
    for idx, (code, label) in enumerate(CODE_GROUPS):
        _ensure(db, tenant_id, DEF_GROUP_CODE_GROUPS, key1=code, description=label, key2="999",
                sort_order=idx, existing_by_label=by_label, existing_by_key=by_key,
                match="key", apply=apply, overwrite=overwrite, counts=counts)

    # Plan types: the export stores an empty key1 and the label in description.
    by_label, by_key = index(DEF_GROUP_PLAN_TYPE)
    for idx, label in enumerate(PLAN_TYPES):
        _ensure(db, tenant_id, DEF_GROUP_PLAN_TYPE, key1="", description=label, key2=None,
                sort_order=idx, existing_by_label=by_label, existing_by_key=by_key,
                match="label", apply=apply, overwrite=overwrite, counts=counts)

    # Plan subtypes: key1 = parent plan type, description = subtype label —
    # identified by the pair.
    by_pair = {
        ((r.key1 or "").strip(), (r.description or "").strip().lower()): r
        for r in _rows(db, tenant_id, DEF_GROUP_PLAN_SUBTYPE)
    }
    for idx, (plan_type, label) in enumerate(PLAN_SUBTYPES):
        _ensure(db, tenant_id, DEF_GROUP_PLAN_SUBTYPE, key1=plan_type, description=label, key2=None,
                sort_order=idx, existing_by_label=by_pair, existing_by_key={},
                match="key+label", apply=apply, overwrite=overwrite, counts=counts)

    # PLAN-tab vocabularies (PLAN-DTL-1), keyed by code.
    for group_code, options in PLAN_FIELD_OPTIONS.items():
        by_label, by_key = index(group_code)
        for idx, (code, label) in enumerate(options):
            _ensure(db, tenant_id, group_code, key1=code, description=label, key2=None,
                    sort_order=idx, existing_by_label=by_label, existing_by_key=by_key,
                    match="key", apply=apply, overwrite=overwrite, counts=counts)

    if apply:
        db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant", type=int, default=None, help="Tenant id (default: all active)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Also replace an existing sort_order/key2 that differs from the canonical value")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.tenant is not None:
            tenant_ids = [args.tenant]
        else:
            tenant_ids = list(db.execute(
                select(Tenant.id).where(Tenant.is_active.is_(True)).order_by(Tenant.id)
            ).scalars())
        total_added = total_patched = 0
        for tid in tenant_ids:
            c = seed_for_tenant(db, tid, apply=args.apply, overwrite=args.overwrite)
            total_added += c["added"]
            total_patched += c["patched"]
            print(f"tenant {tid}: {c['added']} added, {c['patched']} patched")
        verb = "applied" if args.apply else "DRY RUN (pass --apply)"
        print(f"{verb}: {total_added} definitions added, {total_patched} patched across {len(tenant_ids)} tenant(s)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
