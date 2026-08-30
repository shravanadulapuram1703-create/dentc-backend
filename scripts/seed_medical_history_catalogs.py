"""Seed the MEDALERT / DENTQUEST / MEDQUEST catalogs (MH-1).

Why this is not just another seeder
-----------------------------------
``definition_groups`` currently holds only three stray test groups
(``MEDALERT_TEST``, ``DENTQUEST_TEST``, ``MEDQUEST_TEST``), each with fewer than
ten definitions — so the frontend's ``MIN_TENANT_CATALOG_ITEMS`` guard rejects
them and renders its own verbatim legacy transcription instead. (The backend now
does the same thing server-side: ``GET /patients/{id}/medical-history`` serves
the built-in catalog and reports ``catalog_sources: {"alerts": "builtin"}`` until
a real one is seeded, so nothing is blocked on running this script.)

**Seeding is a one-way door.** An answer is keyed by a code the frontend derives
from the label (``toCode("Latex Rubber") -> "latex_rubber"``), so the moment a
tenant catalog passes the size guard the client switches to it — and every label
whose derived code differs orphans the rows already answered under the old code.
That is why:

* ``key1`` is always :func:`app.services.medical_history_catalog.to_code` of the
  label, the identical derivation the frontend uses;
* the script is **dry-run by default** and prints the codes it would write;
* ``--from-json`` takes the frontend's ``legacyCatalogs.ts`` exported to JSON and
  uses it as the source of truth instead of the bundled transcription. **Prefer
  this.** The bundled lists are a faithful transcription of the legacy Denticon
  catalogs, but "faithful" is not "byte-identical to the file the answers were
  keyed against", and only one of those is safe;
* ``--report-drift`` compares a catalog against the codes patients have already
  answered and refuses to write a catalog that would orphan any of them unless
  ``--allow-orphans`` is passed.

``key2`` carries the input kind (``text``/``textarea``/``date``/``number``; null
means Yes/No) and is mirrored into ``definitions.input_type``; ``section`` drives
the collapse/expand grouping on the questionnaire tabs.

MH-11: the Emergency Contact block is deliberately **absent** from ``MEDQUEST``.
``patient_emergency_contacts`` is the authoritative store — that is what the rest
of the app reads, and duplicating the three questions is what made the two drift.

JSON hand-over format
---------------------
``--from-json`` accepts either shape, per group type::

    {
      "MEDALERT":  [{"label": "Latex Rubber", "section": "Allergic To"}, ...],
      "DENTQUEST": ["Do your gums bleed when brushing or flossing", ...],
      "MEDQUEST":  [{"label": "Physician Name", "key2": "text"}, ...]
    }

A row may pin its own ``code``/``key1``; otherwise it is derived from the label.

Usage
-----
::

    python -m scripts.seed_medical_history_catalogs                       # report only
    python -m scripts.seed_medical_history_catalogs --report-drift
    python -m scripts.seed_medical_history_catalogs --from-json fe.json
    python -m scripts.seed_medical_history_catalogs --apply --tenant 1
    python -m scripts.seed_medical_history_catalogs --apply              # all tenants
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Definition,
    DefinitionGroup,
    PatientMedicalAlert,
    PatientQuestionnaireResponse,
    Tenant,
)
from app.db.session import SessionLocal
from app.services.medical_history_catalog import (
    ALERT_GROUP_TYPE,
    CATALOGS,
    DEFAULT_GROUP_CODES,
    GROUP_DESCRIPTIONS,
    GROUP_TYPES,
    QUESTIONNAIRE_GROUP_TYPES,
    input_type_for,
    normalize_catalog,
)


def load_catalogs(path: str | None) -> dict[str, list[dict[str, Any]]]:
    if not path:
        return {gt: list(CATALOGS[gt]) for gt in GROUP_TYPES}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, list[dict[str, Any]]] = {}
    for group_type in GROUP_TYPES:
        rows = raw.get(group_type) or raw.get(group_type.lower()) or []
        out[group_type] = normalize_catalog(list(rows))
    return out


def answered_codes(db: Session, tenant_id: int, group_type: str) -> set[str]:
    """Codes patients have already answered under this catalog."""
    if group_type == ALERT_GROUP_TYPE:
        rows = db.execute(
            select(PatientMedicalAlert.alert_code).where(
                PatientMedicalAlert.tenant_id == tenant_id
            )
        ).scalars()
    else:
        kind = next(k for k, v in QUESTIONNAIRE_GROUP_TYPES.items() if v == group_type)
        rows = db.execute(
            select(PatientQuestionnaireResponse.question_code).where(
                PatientQuestionnaireResponse.tenant_id == tenant_id,
                PatientQuestionnaireResponse.questionnaire_type == kind,
            )
        ).scalars()
    return {code for code in rows if code}


def seed_for_tenant(
    db: Session,
    tenant_id: int,
    catalogs: dict[str, list[dict[str, Any]]],
    *,
    apply: bool,
    allow_orphans: bool,
    verbose: bool,
) -> tuple[int, int, dict[str, set[str]]]:
    """``(groups_added, definitions_added, orphans_by_group_type)``."""
    groups_added = defs_added = 0
    orphans: dict[str, set[str]] = {}

    for group_type in GROUP_TYPES:
        catalog = catalogs.get(group_type) or []
        if not catalog:
            continue
        group_code = DEFAULT_GROUP_CODES[group_type]
        codes = {item["code"] for item in catalog}

        already = answered_codes(db, tenant_id, group_type)
        missing = already - codes
        if missing:
            orphans[group_type] = missing
            if verbose:
                print(
                    f"  tenant {tenant_id} {group_type}: {len(missing)} answered code(s) "
                    f"absent from the catalog -> {sorted(missing)[:8]}"
                )
            if not allow_orphans:
                continue

        group = db.execute(
            select(DefinitionGroup).where(
                DefinitionGroup.tenant_id == tenant_id,
                DefinitionGroup.group_code == group_code,
            )
        ).scalar_one_or_none()
        if group is None:
            if apply:
                db.add(
                    DefinitionGroup(
                        tenant_id=tenant_id,
                        group_code=group_code,
                        description=GROUP_DESCRIPTIONS[group_type],
                        group_type=group_type,
                        key1_label="Code",
                        key2_label="Input type",
                        is_editable=True,
                        can_add=True,
                    )
                )
            groups_added += 1

        existing = {
            row.key1: row
            for row in db.execute(
                select(Definition).where(
                    Definition.tenant_id == tenant_id,
                    Definition.group_code == group_code,
                )
            ).scalars()
        }
        for index, item in enumerate(catalog):
            row = existing.get(item["code"])
            kind = item.get("input_kind")
            if row is None:
                if apply:
                    db.add(
                        Definition(
                            tenant_id=tenant_id,
                            group_code=group_code,
                            key1=item["code"],
                            key2=kind,
                            description=item["label"],
                            section=item.get("section"),
                            input_type=input_type_for(kind),
                            sort_order=index,
                            is_active=True,
                        )
                    )
                defs_added += 1
                continue
            # Existing row: fill in only what is missing. A practice may have
            # edited the wording, and the label is not ours to overwrite.
            if apply:
                if row.key2 is None and kind:
                    row.key2 = kind
                if row.section is None and item.get("section"):
                    row.section = item["section"]
                if row.input_type is None:
                    row.input_type = input_type_for(kind)
                if row.sort_order is None:
                    row.sort_order = index

    if apply:
        db.commit()
    return groups_added, defs_added, orphans


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    parser.add_argument("--tenant", type=int, help="one tenant (default: all active)")
    parser.add_argument(
        "--from-json",
        help="a catalog hand-over file (the frontend's legacyCatalogs.ts as JSON)",
    )
    parser.add_argument(
        "--allow-orphans",
        action="store_true",
        help="seed even when answered codes are absent from the catalog",
    )
    parser.add_argument(
        "--report-drift",
        action="store_true",
        help="only report answered codes the catalog does not contain",
    )
    args = parser.parse_args()

    catalogs = load_catalogs(args.from_json)
    print(
        "catalog sizes: "
        + ", ".join(f"{gt}={len(catalogs.get(gt) or [])}" for gt in GROUP_TYPES)
        + (f"  (from {args.from_json})" if args.from_json else "  (bundled transcription)")
    )

    with SessionLocal() as db:
        tenant_ids = (
            [args.tenant]
            if args.tenant is not None
            else list(
                db.execute(select(Tenant.id).where(Tenant.is_active.is_(True))).scalars().all()
            )
        )
        total_groups = total_defs = 0
        total_orphans = 0
        for tid in tenant_ids:
            groups, defs, orphans = seed_for_tenant(
                db,
                tid,
                catalogs,
                apply=args.apply and not args.report_drift,
                allow_orphans=args.allow_orphans,
                verbose=True,
            )
            total_groups += groups
            total_defs += defs
            total_orphans += sum(len(v) for v in orphans.values())
            if groups or defs:
                verb = "" if (args.apply and not args.report_drift) else "would "
                print(f"tenant {tid:>3}: {verb}add {groups} group(s), {defs} definition(s)")

        print(
            f"\n{len(tenant_ids)} tenant(s): {total_groups} groups, {total_defs} definitions"
            f"; {total_orphans} answered code(s) not in the catalog"
        )
        if total_orphans and not args.allow_orphans:
            print(
                "Refused to seed the affected catalogs: those answers would orphan.\n"
                "Hand over the frontend's legacyCatalogs.ts via --from-json, or pass "
                "--allow-orphans once you have decided how to migrate them."
            )
        if not args.apply or args.report_drift:
            print("Dry run — nothing written. Re-run with --apply.")


if __name__ == "__main__":
    main()
