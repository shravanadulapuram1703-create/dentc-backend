"""Notes Macros Setup — the rules the generic CRUD engine cannot express.

Backs NM-3/5/6/7 of ``docs/pick-list/pick_list_setup_backend_devreport.md``,
the note-macro twin of :mod:`app.services.prescription_library_service`.

* **NM-7** is the importer defect (fixed by Alembic ``3a8f2c41b7d9``): no unique
  key, so every migration re-run appended the whole catalog again. That stops
  the *importer* recurring it; this module stops the *API* recurring it.
* **NM-5 duplicate guard** — a macro with the same **name + category** (trimmed,
  whitespace-collapsed, case-insensitive; a blank category and a null category
  are the same thing) is a 409 ``duplicate_note_macro`` unless the caller sends
  ``allow_duplicate``. Deliberately **not a DB constraint**: the migrated
  catalog already holds one legitimate-looking name twice under one category
  (``fixed/detach try-in``), and the guard fires on a **move** only, so that
  pair stays editable. Same-name rows under *another* category are reported
  (``other_category_matches``) and never block — the Setup screen's category is
  a first-class filter, so "Cold Sensitivity" under DIAGNOSTIC and under PERIO
  are different macros. ``note_macros`` has no ``is_active`` (``soft_field=None``
  in the registry), so every row counts.
* **Length caps** — the schema factory does not propagate column lengths, so a
  101-character name was a database error, not a 422. Published at
  ``GET /note-macros/limits``.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, ValidationError
from app.crud.base import CRUDBase
from app.db.models import NoteMacro

NAME_MAX_LENGTH = 100
CATEGORY_MAX_LENGTH = 100

DUPLICATE_KEY_FIELDS = ("name", "category")
OVERRIDE_FIELD = "allow_duplicate"

_WS = re.compile(r"\s+")


def normalise_key(value: str | None) -> str:
    """Trim, collapse internal whitespace, lower-case. ``None`` == ``""``."""
    if value is None:
        return ""
    return _WS.sub(" ", str(value).strip()).lower()


def _name_prefilter(name_key: str):  # noqa: ANN001
    """A ``LIKE`` that can over-match but never miss a row :func:`normalise_key`
    would match (whitespace runs become ``%``); the exact compare finishes in
    Python on the candidate set. Portable across Postgres and SQLite."""
    escaped = name_key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = "%".join(escaped.split(" "))
    return func.lower(func.trim(NoteMacro.name)).like(pattern, escape="\\")


def match_payload(rows: list[NoteMacro]) -> list[dict[str, Any]]:
    return [
        {"id": r.id, "name": r.name, "category": r.category, "legacy_id": r.legacy_id}
        for r in rows
    ]


def find_matches(
    db: Session,
    tenant_id: int | None,
    *,
    name: str | None,
    category: str | None,
    exclude_id: int | None = None,
) -> dict[str, list[NoteMacro]]:
    """``same_category``: identical name under the same category (the 409).
    ``other_category``: identical name under another category (informational)."""
    name_key = normalise_key(name)
    if not name_key:
        return {"same_category": [], "other_category": []}
    stmt = select(NoteMacro).where(_name_prefilter(name_key))
    if tenant_id is not None:
        stmt = stmt.where(NoteMacro.tenant_id == tenant_id)
    if exclude_id is not None:
        stmt = stmt.where(NoteMacro.id != exclude_id)
    candidates = db.execute(stmt.order_by(NoteMacro.id)).scalars().all()

    cat_key = normalise_key(category)
    out: dict[str, list[NoteMacro]] = {"same_category": [], "other_category": []}
    for row in candidates:
        if normalise_key(row.name) != name_key:
            continue  # the LIKE prefilter over-matches on purpose
        bucket = "same_category" if normalise_key(row.category) == cat_key else "other_category"
        out[bucket].append(row)
    return out


def availability(
    db: Session,
    tenant_id: int | None,
    *,
    name: str,
    category: str | None = None,
    exclude_id: int | None = None,
) -> dict[str, Any]:
    """NM-5 probe: ``taken`` is exactly what the save path will 409 on."""
    found = find_matches(db, tenant_id, name=name, category=category, exclude_id=exclude_id)
    return {
        "name": name,
        "category": category,
        "taken": bool(found["same_category"]),
        "matches": match_payload(found["same_category"]),
        "other_category_matches": match_payload(found["other_category"]),
        "override_field": OVERRIDE_FIELD,
    }


def limits() -> dict[str, Any]:
    return {
        "name_max_length": NAME_MAX_LENGTH,
        "category_max_length": CATEGORY_MAX_LENGTH,
        "duplicate_key_fields": list(DUPLICATE_KEY_FIELDS),
        "override_field": OVERRIDE_FIELD,
    }


def _check_lengths(payload: dict[str, Any]) -> None:
    """Only the fields the payload carries are judged."""
    for field, cap in (("name", NAME_MAX_LENGTH), ("category", CATEGORY_MAX_LENGTH)):
        value = payload.get(field)
        if value is not None and len(value) > cap:
            raise ValidationError(
                f"{field} may be at most {cap} characters",
                code=f"{field}_too_long",
                details={"field": field, "max_length": cap, "length": len(value)},
            )


def _strip_strings(payload: dict[str, Any]) -> dict[str, Any]:
    for field in DUPLICATE_KEY_FIELDS:
        if field in payload and isinstance(payload[field], str):
            payload[field] = payload[field].strip()
    # A blank category is "no category": store NULL so the ?category= filter and
    # the /categories dropdown never grow an empty-string bucket.
    if payload.get("category") == "":
        payload["category"] = None
    if "name" in payload and not payload["name"]:
        raise ValidationError(
            "name must not be blank", code="name_required", details={"field": "name"}
        )
    return payload


class NoteMacroCRUD(CRUDBase):
    """NM-5 + length caps on every write path (``crud_class`` for ``/note-macros``)."""

    def _guard(
        self, db: Session, *, tenant_id: int | None, name: str | None,
        category: str | None, exclude_id: int | None, allow_duplicate: bool,
    ) -> None:
        if allow_duplicate:
            return
        found = find_matches(db, tenant_id, name=name, category=category, exclude_id=exclude_id)
        if not found["same_category"]:
            return
        raise ConflictError(
            "A note macro with this name already exists in this category",
            code="duplicate_note_macro",
            details={
                "name": name,
                "category": category,
                "matches": match_payload(found["same_category"]),
                "other_category_matches": match_payload(found["other_category"]),
                "override_field": OVERRIDE_FIELD,
            },
        )

    def create(
        self, db: Session, data: dict[str, Any], *,
        tenant_id: int | None = None, created_by: int | None = None,
    ) -> NoteMacro:
        payload = _strip_strings(dict(data))
        allow = bool(payload.pop(OVERRIDE_FIELD, False))
        _check_lengths(payload)
        self._guard(
            db, tenant_id=tenant_id, name=payload.get("name"),
            category=payload.get("category"), exclude_id=None, allow_duplicate=allow,
        )
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(
        self, db: Session, obj_id: Any, data: dict[str, Any], *,
        tenant_id: int | None = None, updated_by: int | None = None,
    ) -> NoteMacro:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        payload = _strip_strings(dict(data))
        allow = bool(payload.pop(OVERRIDE_FIELD, False))
        _check_lengths(payload)
        merged = {f: payload.get(f, getattr(existing, f)) for f in DUPLICATE_KEY_FIELDS}
        # Fires on a move only — the migrated catalog already holds one
        # pre-existing same-name pair, and editing its body must keep working.
        moved = any(
            normalise_key(merged[f]) != normalise_key(getattr(existing, f))
            for f in DUPLICATE_KEY_FIELDS
        )
        if moved:
            self._guard(
                db, tenant_id=tenant_id, name=merged["name"], category=merged["category"],
                exclude_id=existing.id, allow_duplicate=allow,
            )
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)


# ── PN-6: category codes → labels ────────────────────────────────────────────
#: The Denticon definitions group that names the macro categories. The importer
#: wrote ``ChartNotesMacros.Macrocat`` (a DEFINITIONSID such as ``179``) straight
#: into ``note_macros.category`` and never joined it to this group, so every
#: Category dropdown in the app rendered the code.
CATEGORY_DEFINITION_GROUP = "NOTESMACROS"


def category_labels(db: Session, tenant_id: int | None) -> dict[str, str]:
    """``{code: label}`` for the tenant's ``NOTESMACROS`` definitions.

    The migrated rows carry the code in ``legacy_id`` (``key1`` is blank), so
    both are accepted as the key; ``key1`` wins when it is set because that is
    the column the generic ``GET /definitions?group_code=`` dropdown keys on.
    """
    from app.db.models import Definition

    if tenant_id is None:
        return {}
    rows = db.execute(
        select(Definition.key1, Definition.legacy_id, Definition.description).where(
            Definition.tenant_id == tenant_id,
            Definition.group_code == CATEGORY_DEFINITION_GROUP,
        )
    ).all()
    labels: dict[str, str] = {}
    for key1, legacy_id, description in rows:
        label = (description or "").strip()
        if not label:
            continue
        for key in (legacy_id, key1):
            key = (key or "").strip()
            if key and key not in labels:
                labels[key] = label
    return labels


def category_label(value: str | None, labels: dict[str, str]) -> str | None:
    """The label for a stored category: the definition's description when the
    stored value is a code the tenant defines, else the value as written."""
    if value is None:
        return None
    return labels.get(value.strip(), value)


def enrich_note_macros(db: Session, items, tenant_id: int | None = None) -> None:  # noqa: ANN001
    """Read hook: NM-3 actor names + PN-6 ``category_label``."""
    from app.services.perio_service import attach_actor_names

    rows = list(items)
    if not rows:
        return
    attach_actor_names(db, rows, tenant_id)
    labels = category_labels(db, tenant_id)
    for row in rows:
        row.category_label = category_label(row.category, labels)
