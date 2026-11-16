"""IMG-DOC-3/4: review (and optionally re-apply) patient-document owners and types.

Alembic ``03bbb54c0b12`` already stamps ``patient_documents.context`` on every
existing row with ``document_vocabulary.backfill_case`` — this script is the
review tool the frontend asked for, over the *same* expression:

    python -m scripts.backfill_document_context                 # dry run: counts per owner
    python -m scripts.backfill_document_context --apply         # re-derive defaulted rows
    python -m scripts.backfill_document_context --fold-types    # dry run: type -> code folding
    python -m scripts.backfill_document_context --fold-types --apply

Dry run (default) prints:

* rows per derived owner, and how many differ from what is stored;
* the ``document_type`` values that fell through to ``documents`` (the bucket
  to eyeball for radiographs, e.g. ``X-Ray / Radiograph`` / ``XR``) — these are
  never auto-moved; staff move them with ``PATCH /patient-documents/{id}``.

``--apply`` only touches rows still on the ``documents`` default whose derived
owner is something else **and** that no person has edited (``updated_by IS
NULL``) — so it can never undo an IMG-DOC-5 move.

``--fold-types`` previews (``--apply`` writes) the IMG-DOC-4 migration of
free-text ``document_type`` values to definitions codes, per owner context.
Run it with ``--apply`` only together with turning on
``DOCUMENT_TYPE_VOCABULARY_ENFORCED`` and the frontend release that reads its
pickers from ``/definitions`` — today's Imaging gallery matches on the label.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict

from sqlalchemy import func, select, update

from app.db.models import PatientDocument
from app.db.session import SessionLocal
from app.services import document_vocabulary as vocab


def owner_report(db, apply: bool) -> None:  # noqa: ANN001
    derived = vocab.backfill_case().label("derived")
    rows = db.execute(
        select(derived, PatientDocument.context, func.count())
        .where(PatientDocument.is_deleted.is_(False))
        .group_by(derived, PatientDocument.context)
    ).all()
    per_derived: Counter = Counter()
    differs: Counter = Counter()
    for d, stored, n in rows:
        per_derived[d] += n
        if d != stored:
            differs[(stored, d)] += n
    print("Rows per derived owner (non-deleted):")
    for ctx in vocab.DOCUMENT_CONTEXTS:
        print(f"  {ctx:<15} {per_derived.get(ctx, 0):>8}")
    print(f"  {'TOTAL':<15} {sum(per_derived.values()):>8}")
    if differs:
        print("Stored owner differs from the derived one (stored -> derived):")
        for (stored, d), n in sorted(differs.items(), key=lambda kv: -kv[1]):
            print(f"  {stored} -> {d}: {n}")
    else:
        print("Stored owner matches the derived one on every row.")

    fall_through = db.execute(
        select(PatientDocument.document_type, func.count())
        .where(PatientDocument.is_deleted.is_(False), derived == vocab.CONTEXT_DOCUMENTS)
        .group_by(PatientDocument.document_type)
        .order_by(func.count().desc())
    ).all()
    print("document_type values that fall through to 'documents' (review for radiographs):")
    for t, n in fall_through:
        print(f"  {t!r:<40} {n:>8}")

    if apply:
        result = db.execute(
            update(PatientDocument)
            .where(
                PatientDocument.context == vocab.CONTEXT_DOCUMENTS,
                PatientDocument.updated_by.is_(None),
                vocab.backfill_case() != vocab.CONTEXT_DOCUMENTS,
            )
            .values(context=vocab.backfill_case())
            .execution_options(synchronize_session=False)
        )
        db.commit()
        print(f"Applied: {result.rowcount} row(s) re-owned.")


def fold_types_report(db, apply: bool) -> None:  # noqa: ANN001
    rows = db.execute(
        select(PatientDocument.tenant_id, PatientDocument.context,
               PatientDocument.document_type, func.count())
        .where(PatientDocument.is_deleted.is_(False), PatientDocument.document_type.is_not(None))
        .group_by(PatientDocument.tenant_id, PatientDocument.context, PatientDocument.document_type)
    ).all()
    catalogs: dict[tuple[int, str], list] = {}
    folds: Counter = Counter()
    unresolved: Counter = Counter()
    plan: dict[tuple[int, str, str], str] = {}
    for tenant_id, ctx, value, n in rows:
        group = vocab.CONTEXT_TYPE_GROUP.get(ctx)
        if group is None:
            continue  # system contexts keep their fixed type
        key = (tenant_id, group)
        if key not in catalogs:
            catalogs[key] = vocab.catalog(db, tenant_id, group)
        code = vocab._resolve(catalogs[key], group, value)  # noqa: SLF001
        if code is None:
            unresolved[(ctx, value)] += n
        elif code != value:
            folds[(ctx, value, code)] += n
            plan[(tenant_id, ctx, value)] = code
    print("document_type folds (context: stored -> code):")
    for (ctx, value, code), n in sorted(folds.items(), key=lambda kv: -kv[1]):
        print(f"  {ctx}: {value!r} -> {code}  ({n})")
    print("Unresolved (would 422 once enforced; add to definitions or re-type):")
    for (ctx, value), n in sorted(unresolved.items(), key=lambda kv: -kv[1]):
        print(f"  {ctx}: {value!r}  ({n})")
    if apply:
        total = 0
        by_tenant: dict = defaultdict(list)
        for (tenant_id, ctx, value), code in plan.items():
            by_tenant[tenant_id].append((ctx, value, code))
        for tenant_id, items in by_tenant.items():
            for ctx, value, code in items:
                result = db.execute(
                    update(PatientDocument)
                    .where(PatientDocument.tenant_id == tenant_id,
                           PatientDocument.context == ctx,
                           PatientDocument.document_type == value)
                    .values(document_type=code)
                    .execution_options(synchronize_session=False)
                )
                total += result.rowcount or 0
        db.commit()
        print(f"Applied: {total} row(s) re-typed.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--fold-types", action="store_true",
                        help="IMG-DOC-4: free-text document_type -> definitions code")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.fold_types:
            fold_types_report(db, args.apply)
        else:
            owner_report(db, args.apply)
        if not args.apply:
            db.rollback()
            print("(dry run - nothing written)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
