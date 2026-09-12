"""PN-6 / NM-2: relabel note-macro categories from Denticon codes to names.

``note_macros.category`` holds ``ChartNotesMacros.Macrocat`` — a Denticon
DEFINITIONSID such as ``179`` — because the importer never joined it to the
``NOTESMACROS`` definitions group, which the same export *does* carry
(``DEFINITIONS.txt``: ``179 → DIAGNOSTIC``, ``180 → PREVENTIVE``, …) and which
is already in ``definitions`` under ``legacy_id``. Every Category dropdown in
the app therefore rendered the code.

What one run does, per tenant:

1. ``note_macros.category`` that is a code the tenant's ``NOTESMACROS``
   definitions name is rewritten to that name (``updated_at`` untouched — this
   is not an edit).
2. ``NOTESMACROS`` definitions with a blank ``key1`` get ``key1 = legacy_id``,
   so the generic ``GET /definitions?group_code=NOTESMACROS`` dropdown has a
   key to filter on like every other group.

Codes with no definition are reported and left alone. Reads already resolve
a leftover code to its label (``NoteMacroRead.category_label`` and
``GET /note-macros/categories``), so nothing renders wrong before this runs;
running it makes the stored value what the Setup screen shows and edits.

    python -m scripts.normalize_note_macro_categories            # dry run
    python -m scripts.normalize_note_macro_categories --apply
"""

from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import bindparam, select, update

from app.db.models import Definition, NoteMacro
from app.db.session import SessionLocal
from app.services.note_macro_service import CATEGORY_DEFINITION_GROUP, category_labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    stats: Counter = Counter()
    unmapped: Counter = Counter()
    try:
        tenant_ids = [
            t for (t,) in db.execute(
                select(NoteMacro.tenant_id).where(NoteMacro.category.is_not(None)).distinct()
            ).all()
        ]
        macro_updates: list[dict] = []
        for tenant_id in tenant_ids:
            labels = category_labels(db, tenant_id)
            macros = db.execute(
                select(NoteMacro.id, NoteMacro.category, NoteMacro.updated_at).where(
                    NoteMacro.tenant_id == tenant_id, NoteMacro.category.is_not(None)
                )
            ).all()
            for macro_id, category, updated_at in macros:
                code = (category or "").strip()
                label = labels.get(code)
                if label is None:
                    if code.isdigit():
                        unmapped[(tenant_id, code)] += 1
                    else:
                        stats["already_label"] += 1
                    continue
                if label == category:
                    stats["already_label"] += 1
                    continue
                macro_updates.append(
                    {"_id": macro_id, "category": label, "updated_at": updated_at}
                )
                stats["relabelled"] += 1
                stats[f"tenant_{tenant_id}"] += 1

        blank_key_defs = db.execute(
            select(Definition).where(
                Definition.group_code == CATEGORY_DEFINITION_GROUP,
                (Definition.key1.is_(None)) | (Definition.key1 == ""),
                Definition.legacy_id.is_not(None),
            )
        ).scalars().all()

        if args.apply:
            if macro_updates:
                db.connection().execute(
                    update(NoteMacro.__table__)
                    .where(NoteMacro.id == bindparam("_id"))
                    .values(category=bindparam("category"), updated_at=bindparam("updated_at")),
                    macro_updates,
                )
            for d in blank_key_defs:
                d.key1 = d.legacy_id
            db.commit()
    finally:
        db.close()

    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"[{mode}] note_macros category normalisation")
    for key in sorted(stats):
        print(f"  {key:>18}: {stats[key]}")
    print(f"  definitions key1 filled: {len(blank_key_defs)}")
    if unmapped:
        print("  codes with no NOTESMACROS definition (left as-is):")
        for (tenant_id, code), n in sorted(unmapped.items()):
            print(f"    tenant {tenant_id} code {code!r}: {n} macro(s)")
    if not args.apply:
        print("  (dry run - re-run with --apply to write)")


if __name__ == "__main__":
    main()
