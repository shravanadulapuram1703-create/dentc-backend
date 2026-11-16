"""Who owns a patient document, and what kind of document it is (IMG-DOC-1..4).

``patient_documents`` is one table that at least eight screens write to —
Documents, Imaging, Notes, Patient Photo, Letters/Consent, Progress Notes, the
Restorative drawing and Treatment Plans. Nothing on the row said which one, so
the Imaging gallery had to *guess* from ``document_type`` / the MIME type, and an
insurance-card JPG uploaded on Documents showed up among the radiographs.

This module is the single home for the two vocabularies that fix it:

* **context** — the owning module, a short closed set. Persisted on the row
  (``patient_documents.context``), filterable on the list, and the thing that
  picks the storage prefix (``document_store.prefix_for``).
* **document_type** — the sub-type the picker offers. Per-context catalogs live
  in ``definitions`` (``document_type`` for Documents/Notes,
  ``imaging_document_type`` for Imaging); the system contexts write a fixed
  type of their own and are never validated against a catalog.

The *inference* rule (what a row with no declared context belongs to) is used by
both the upload path — so a client that has not cut over to sending ``context``
still files correctly — and the backfill (Alembic + ``scripts/backfill_document_context.py``),
so the two cannot disagree.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import String, and_, case, cast, exists, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError

# ── context ──────────────────────────────────────────────────────────────────
CONTEXT_DOCUMENTS = "documents"
CONTEXT_IMAGING = "imaging"
CONTEXT_NOTE = "note"
CONTEXT_PATIENT_PHOTO = "patient_photo"
CONTEXT_LETTER = "letter"
CONTEXT_CONSENT = "consent"
CONTEXT_PROGRESS_NOTE = "progress_note"
CONTEXT_RESTORATIVE = "restorative"
CONTEXT_TREATMENT_PLAN = "treatment_plan"

#: Closed on purpose: each value is a folder in a real bucket, so a free-text
#: value would let a typo create a folder nobody knows to look in.
DOCUMENT_CONTEXTS: tuple[str, ...] = (
    CONTEXT_DOCUMENTS,
    CONTEXT_IMAGING,
    CONTEXT_NOTE,
    CONTEXT_PATIENT_PHOTO,
    CONTEXT_LETTER,
    CONTEXT_CONSENT,
    CONTEXT_PROGRESS_NOTE,
    CONTEXT_RESTORATIVE,
    CONTEXT_TREATMENT_PLAN,
)

#: IMG-DOC-5: the contexts a person may move a file between. The others are
#: owned by a record (a note, a consent, a progress note, the chart photo) —
#: re-homing that file would orphan the record that points at it.
MOVABLE_CONTEXTS: tuple[str, ...] = (CONTEXT_DOCUMENTS, CONTEXT_IMAGING)


def normalize_context(context: str | None) -> str | None:
    """Validate and canonicalise a ``context``; None when not supplied."""
    value = (context or "").strip().lower().replace("-", "_") or None
    if value is not None and value not in DOCUMENT_CONTEXTS:
        raise ValidationError(
            f"context must be one of {', '.join(DOCUMENT_CONTEXTS)}",
            code="invalid_document_context",
            details={"allowed_contexts": list(DOCUMENT_CONTEXTS), "context": context},
        )
    return value


def parse_context_list(values: Iterable[str] | None) -> list[str]:
    """``?context=a&context=b`` and ``?context=a,b`` alike; each value validated."""
    out: list[str] = []
    for raw in values or ():
        for part in str(raw).split(","):
            ctx = normalize_context(part)
            if ctx and ctx not in out:
                out.append(ctx)
    return out


# ── system document types (fixed per context, never catalog-validated) ───────
#: What each non-picker screen writes as ``document_type`` today. Lower-cased.
SYSTEM_TYPE_CONTEXT: dict[str, str] = {
    "ph": CONTEXT_PATIENT_PHOTO,
    "patient-photo": CONTEXT_PATIENT_PHOTO,
    "patient_photo": CONTEXT_PATIENT_PHOTO,
    "patient-letter": CONTEXT_LETTER,
    "letter": CONTEXT_LETTER,
    "progress_note": CONTEXT_PROGRESS_NOTE,
    "progress-note": CONTEXT_PROGRESS_NOTE,
    "restorative-drawing": CONTEXT_RESTORATIVE,
    "restorative_drawing": CONTEXT_RESTORATIVE,
    "treatment-plan": CONTEXT_TREATMENT_PLAN,
    "treatment_plan": CONTEXT_TREATMENT_PLAN,
}

#: The labels the Imaging screen has written as ``document_type`` (the FE's
#: ``IMAGING_CATEGORIES``). Deliberately the *labels* only — ``XR`` and
#: ``X-Ray / Radiograph`` are also what Notes and the Documents tab send, so
#: they are never inferred to be Imaging; a person moves them (IMG-DOC-5).
IMAGING_INFERENCE_TYPES: frozenset[str] = frozenset({
    "x-ray", "bitewing", "panoramic", "periapical",
    "intraoral photo", "treatment photo", "other image",
})


def _consent_types() -> set[str]:
    return {t.strip().lower() for t in settings.CONSENT_DOCUMENT_TYPES}


def infer_context(document_type: str | None) -> str:
    """The owning module for a row that did not declare one.

    Used by the upload path when the caller sends no ``context`` (a client that
    has not cut over yet) and mirrored, rule for rule, by :func:`backfill_case`.
    """
    t = (document_type or "").strip().lower()
    if t in SYSTEM_TYPE_CONTEXT:
        return SYSTEM_TYPE_CONTEXT[t]
    if t in _consent_types():
        return CONTEXT_CONSENT
    if t in IMAGING_INFERENCE_TYPES:
        return CONTEXT_IMAGING
    return CONTEXT_DOCUMENTS


def backfill_case():  # noqa: ANN201 - a SQLAlchemy CASE expression
    """IMG-DOC-3: the owner of a pre-existing row, as one SQL expression.

    Rules in order (first match wins):

    1. ``storage_path`` under the notes / consent-forms prefix → ``note`` /
       ``consent`` (``letter`` for a letter type).
    2. An ``image_details`` row joins it by ``tile_id = id`` → ``imaging``.
    3. ``patients.photo_document_id`` points at it → ``patient_photo``.
    4.–6. :func:`infer_context` on ``document_type``.

    The same expression drives the migration's UPDATE and the script's dry-run
    GROUP BY, so the counts reviewed are the counts applied.
    """
    from app.db.models import ImageDetail, Patient, PatientDocument  # noqa: PLC0415

    D = PatientDocument
    path = func.coalesce(D.storage_path, D.file_path, "")
    dtype = func.lower(func.trim(func.coalesce(D.document_type, "")))

    imaging_link = exists(
        select(ImageDetail.id).where(
            ImageDetail.tile_id == cast(D.id, String),
            ImageDetail.tenant_id == D.tenant_id,
        )
    )
    photo_link = exists(select(Patient.id).where(Patient.photo_document_id == D.id))

    letter_types = [k for k, v in SYSTEM_TYPE_CONTEXT.items() if v == CONTEXT_LETTER]
    whens = [
        (path.like(f"%{settings.GCS_NOTES_PREFIX}/%"), CONTEXT_NOTE),
        (and_(path.like(f"%{settings.GCS_CONSENT_FORMS_PREFIX}/%"), dtype.in_(letter_types)),
         CONTEXT_LETTER),
        (path.like(f"%{settings.GCS_CONSENT_FORMS_PREFIX}/%"), CONTEXT_CONSENT),
        (imaging_link, CONTEXT_IMAGING),
        (photo_link, CONTEXT_PATIENT_PHOTO),
    ]
    # Rules 4-6, in infer_context's order.
    by_ctx: dict[str, list[str]] = {}
    for t, ctx in SYSTEM_TYPE_CONTEXT.items():
        by_ctx.setdefault(ctx, []).append(t)
    for ctx, types in by_ctx.items():
        whens.append((dtype.in_(types), ctx))
    whens.append((dtype.in_(sorted(_consent_types())), CONTEXT_CONSENT))
    whens.append((dtype.in_(sorted(IMAGING_INFERENCE_TYPES)), CONTEXT_IMAGING))
    return case(*whens, else_=CONTEXT_DOCUMENTS)


# ── document_type catalogs (IMG-DOC-4) ───────────────────────────────────────
DOCUMENT_TYPE_GROUP = "document_type"
IMAGING_TYPE_GROUP = "imaging_document_type"

#: Which definitions group a picker context reads. Contexts absent here write a
#: fixed system type and are not validated.
CONTEXT_TYPE_GROUP: dict[str, str] = {
    CONTEXT_DOCUMENTS: DOCUMENT_TYPE_GROUP,
    CONTEXT_NOTE: DOCUMENT_TYPE_GROUP,
    CONTEXT_IMAGING: IMAGING_TYPE_GROUP,
}

#: Built-in catalogs (also what ``seed_account_definitions`` seeds). A tenant
#: that has rows in the group uses its own list; otherwise these.
BUILTIN_CATALOGS: dict[str, list[tuple[str, str]]] = {
    DOCUMENT_TYPE_GROUP: [
        ("CF", "Consent Form"),
        ("IC", "Insurance Card"),
        ("ID", "Photo ID"),
        ("XR", "X-Ray / Image"),
        ("RX", "Prescription"),
        ("RF", "Referral Letter"),
        ("LB", "Lab Report"),
        ("MH", "Medical History"),
        ("TP", "Treatment Plan"),
        ("FA", "Financial Agreement"),
        ("EOB", "Explanation of Benefits"),
        ("CR", "Correspondence"),
        ("PH", "Patient Photo"),
        ("OT", "Other"),
    ],
    IMAGING_TYPE_GROUP: [
        ("XR", "X-Ray"),
        ("BW", "Bitewing"),
        ("PA", "Periapical"),
        ("PAN", "Panoramic"),
        ("FMX", "Full Mouth Series"),
        ("CEPH", "Cephalometric"),
        ("CBCT", "CBCT (3D)"),
        ("IO", "Intraoral Photo"),
        ("TXP", "Treatment Photo"),
        ("OI", "Other Image"),
    ],
}

#: Spellings today's screens send that are not the catalog label — the
#: Documents tab's hard-coded list and older Imaging uploads. Literal spellings
#: (matched by :func:`_slug`, so case/punctuation do not matter) → code.
ALIASES: dict[str, dict[str, str]] = {
    DOCUMENT_TYPE_GROUP: {
        "Identification": "ID",
        "Medical Record": "MH",
        "X-Ray / Radiograph": "XR",
        "X-Ray": "XR",
        "Radiograph": "XR",
        "Referral": "RF",
        "Document": "OT",
        "Consent": "CF",
        "consent-form": "CF",
    },
    IMAGING_TYPE_GROUP: {
        "X-Ray / Radiograph": "XR",
        "Radiograph": "XR",
        "Full Mouth": "FMX",
        "CBCT": "CBCT",
        "Other": "OI",
        "Document": "OI",
    },
}


def _slug(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def catalog(db: Session, tenant_id: int, group: str) -> list[tuple[str, str]]:
    """``[(code, label)]`` — the tenant's active definitions, else the built-in."""
    from app.db.models import Definition  # noqa: PLC0415

    rows = db.execute(
        select(Definition.key1, Definition.description).where(
            Definition.tenant_id == tenant_id,
            Definition.group_code == group,
            Definition.is_active.is_(True),
        ).order_by(Definition.sort_order, Definition.id)
    ).all()
    out = [(k, d) for k, d in rows if (k or "").strip()]
    return out or list(BUILTIN_CATALOGS.get(group, []))


def _resolve(entries: list[tuple[str, str]], group: str, value: str) -> str | None:
    """The catalog code ``value`` names (code, label or alias), else None."""
    s = _slug(value)
    if not s:
        return None
    for code, label in entries:
        if _slug(code) == s or _slug(label) == s:
            return code
    for spelling, code in ALIASES.get(group, {}).items():
        if _slug(spelling) == s and any(c == code for c, _ in entries):
            return code
    return None


def enforced() -> bool:
    return bool(settings.DOCUMENT_TYPE_VOCABULARY_ENFORCED)


def normalize_document_type(
    db: Session, tenant_id: int, context: str, value: str | None,
) -> str | None:
    """The ``document_type`` to store for an upload/edit in ``context``.

    With ``DOCUMENT_TYPE_VOCABULARY_ENFORCED`` off (the default until the
    frontend reads its pickers from ``/definitions``) the value is stored as
    written: folding ``Bitewing`` to ``BW`` today would make every new upload
    vanish from the current Imaging gallery, which still matches on the label.
    With it on, a picker context folds a code / label / alias to the code and
    refuses anything else (422 ``invalid_document_type`` with the allowed list).
    """
    raw = (value or "").strip() or None
    group = CONTEXT_TYPE_GROUP.get(context)
    if raw is None or group is None or not enforced():
        return raw
    entries = catalog(db, tenant_id, group)
    code = _resolve(entries, group, raw)
    if code is None:
        raise ValidationError(
            f"document_type '{raw}' is not a {context} document type",
            code="invalid_document_type",
            details={
                "field": "document_type", "context": context, "group_code": group,
                "allowed": [{"code": c, "label": lbl} for c, lbl in entries],
            },
        )
    return code


def label_for(entries_by_group: dict[str, list[tuple[str, str]]], context: str | None,
              value: str | None) -> str | None:
    """Display label for a stored type: the catalog label when it resolves, else
    the stored text (a system type, or a not-yet-migrated free-text value)."""
    if not value:
        return None
    group = CONTEXT_TYPE_GROUP.get(context or "")
    if group is None:
        return value
    entries = entries_by_group.get(group) or []
    code = _resolve(entries, group, value)
    if code is None:
        return value
    return next((lbl for c, lbl in entries if c == code), value)


def type_spellings(db: Session, tenant_id: int, values: Iterable[str]) -> set[str]:
    """Every lower-cased stored spelling a ``?document_type=`` filter should match.

    ``XR`` matches rows stored as ``XR``, ``X-Ray / Image``, ``X-Ray / Radiograph``…
    so the filter keeps working across the free-text → code migration. A value
    no catalog knows is matched case-insensitively as itself.
    """
    out: set[str] = set()
    groups = {g: catalog(db, tenant_id, g) for g in BUILTIN_CATALOGS}
    for raw in values:
        v = (raw or "").strip()
        if not v:
            continue
        out.add(v.lower())
        for group, entries in groups.items():
            code = _resolve(entries, group, v)
            if code is None:
                continue
            out.add(code.lower())
            out.update(lbl.lower() for c, lbl in entries if c == code)
            out.update(sp.lower() for sp, c in ALIASES.get(group, {}).items() if c == code)
    return out


def vocabulary(db: Session, tenant_id: int) -> dict:
    """Published on ``GET /patient-documents/limits`` → the pickers' source."""
    return {
        "contexts": list(DOCUMENT_CONTEXTS),
        "movable_contexts": list(MOVABLE_CONTEXTS),
        "document_type_enforced": enforced(),
        "document_types": {
            ctx: {
                "group_code": group,
                "options": [{"code": c, "label": lbl} for c, lbl in catalog(db, tenant_id, group)],
            }
            for ctx, group in CONTEXT_TYPE_GROUP.items()
        },
    }


def type_filter_clause(column, spellings: set[str]):  # noqa: ANN001, ANN201
    return func.lower(func.trim(column)).in_(sorted(spellings))


__all__ = [
    "DOCUMENT_CONTEXTS", "MOVABLE_CONTEXTS", "normalize_context", "parse_context_list",
    "infer_context", "backfill_case", "normalize_document_type", "label_for",
    "type_spellings", "vocabulary", "catalog",
]
