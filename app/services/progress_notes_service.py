"""Progress-notes business logic (addresses the frontend progress-notes report).

- **PN-7/PN-4** ``ProgressNoteCRUD`` — a CRUDBase subclass wired into the generic
  engine that enforces server-side lock (signed or prior-day notes reject text
  edits) and maintains the strike-off audit (``struck_off_at``/``struck_off_by``)
  on the false→true / true→false transition.
- **PN-5/PN-3/PN-7** ``enrich_progress_notes`` — read hook: resolves actor names,
  the per-note attachment count, and the computed ``is_locked`` flag (no N+1).
- **PN-2** ``sign_progress_note`` — sign as the caller, or as a verified provider
  (over-the-shoulder credentials).
- **PN-3** per-note attachment list/create/delete.
- **PN-6** ``note_macro_categories`` — distinct macro categories for the dropdown.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import filestore
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.crud.base import CRUDBase
from app.db.models import (
    NoteMacro,
    Patient,
    ProgressNote,
    ProgressNoteAttachment,
    User,
)
from app.services import auth_service
from app.services.user_admin_service import resolve_user_names

_MAX_UPLOAD = 10 * 1024 * 1024  # 10 MB
_TEXT_FIELDS = ("notes", "notes_html", "tooth", "surface", "region", "note_date")


def _note_is_locked(note: ProgressNote, today: date) -> bool:
    """PN-7: a note locks once signed, or after midnight of its creation day."""
    if note.signed_at is not None:
        return True
    return note.created_at is not None and note.created_at.date() < today


# ── PN-7 / PN-4: lock enforcement + strike-off audit on PATCH ────────────────
class ProgressNoteCRUD(CRUDBase):
    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        data = dict(data)
        # struck_off_* are server-managed — never honour a client-supplied value.
        data.pop("struck_off_at", None)
        data.pop("struck_off_by", None)

        # PN-7: reject text mutations on a locked note (signing/strike-off still ok).
        if _note_is_locked(obj, datetime.now(timezone.utc).date()):
            changed = [f for f in _TEXT_FIELDS if f in data and data[f] != getattr(obj, f)]
            if changed:
                raise ConflictError(
                    "This note is locked (signed or from a prior day) and cannot be edited",
                    details={"locked_fields": changed},
                )

        # PN-4: stamp/clear the strike-off audit on transition.
        if "is_struck_off" in data:
            new_val = bool(data["is_struck_off"])
            if new_val != bool(obj.is_struck_off):
                if new_val:
                    obj.struck_off_at = datetime.now(timezone.utc)
                    obj.struck_off_by = updated_by
                else:
                    obj.struck_off_at = None
                    obj.struck_off_by = None

        for key, value in data.items():
            setattr(obj, key, value)
        self._commit(db)
        db.refresh(obj)
        return obj


# ── PN-5 / PN-3 / PN-7: read enrichment ──────────────────────────────────────
def enrich_progress_notes(db: Session, items, tenant_id: int | None = None) -> None:  # noqa: ARG001
    rows = list(items)
    if not rows:
        return
    wanted: set[int] = set()
    for r in rows:
        for actor in (r.created_by, r.signed_by, r.struck_off_by):
            if actor is not None:
                wanted.add(actor)
    names = resolve_user_names(db, wanted)

    note_ids = [r.id for r in rows]
    counts = dict(
        db.execute(
            select(ProgressNoteAttachment.progress_note_id, func.count())
            .where(
                ProgressNoteAttachment.progress_note_id.in_(note_ids),
                ProgressNoteAttachment.is_deleted.is_(False),
            )
            .group_by(ProgressNoteAttachment.progress_note_id)
        ).all()
    )

    today = datetime.now(timezone.utc).date()
    for r in rows:
        r.created_by_name = names.get(r.created_by) if r.created_by is not None else None
        r.signed_by_name = names.get(r.signed_by) if r.signed_by is not None else None
        r.struck_off_by_name = names.get(r.struck_off_by) if r.struck_off_by is not None else None
        r.attachment_count = counts.get(r.id, 0)
        r.is_locked = _note_is_locked(r, today)


# ── tenant-safe note lookup (progress_notes isn't tenant-columned) ───────────
def _require_note(db: Session, note_id: int, tenant_id: int) -> ProgressNote:
    note = db.execute(
        select(ProgressNote)
        .join(Patient, Patient.id == ProgressNote.patient_id)
        .where(ProgressNote.id == note_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if note is None:
        raise NotFoundError(f"Progress note '{note_id}' was not found")
    return note


# ── PN-2: sign (self or verified provider) ───────────────────────────────────
def sign_progress_note(
    db: Session, tenant_id: int, note_id: int, caller_id: int | None,
    *, username: str | None = None, password: str | None = None,
) -> ProgressNote:
    note = _require_note(db, note_id, tenant_id)

    if username and password:
        provider = auth_service.verify_user_credentials(db, username, password)
        patient = db.get(Patient, note.patient_id)
        if patient is None or provider.tenant_id != patient.tenant_id:
            raise UnauthorizedError(
                "Credentials are not valid for this practice", code="invalid_credentials"
            )
        signer_id: int | None = provider.id
    elif username or password:
        raise ValidationError(
            "Both username and password are required to sign as another user",
            code="incomplete_credentials",
        )
    else:
        signer_id = caller_id

    note.signed_by = signer_id
    note.signed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(note)
    return note


# ── PN-3: per-note attachments ───────────────────────────────────────────────
def list_attachments(db: Session, tenant_id: int, note_id: int) -> list[ProgressNoteAttachment]:
    _require_note(db, note_id, tenant_id)
    return list(
        db.execute(
            select(ProgressNoteAttachment)
            .where(
                ProgressNoteAttachment.progress_note_id == note_id,
                ProgressNoteAttachment.is_deleted.is_(False),
            )
            .order_by(ProgressNoteAttachment.created_at.desc())
        ).scalars().all()
    )


def create_attachment(
    db: Session, tenant_id: int, note_id: int, *, attachment_type: str | None,
    description: str | None, file_name: str, content_type: str | None,
    data: bytes, user_id: int | None,
) -> ProgressNoteAttachment:
    _require_note(db, note_id, tenant_id)
    if len(data) > _MAX_UPLOAD:
        raise ValidationError("File exceeds 10 MB limit", code="file_too_large")
    rel, url = filestore.save_file(f"progress_note_attachments/{note_id}", file_name, data)
    att = ProgressNoteAttachment(
        tenant_id=tenant_id, progress_note_id=note_id, attachment_type=attachment_type,
        description=description, file_name=file_name, content_type=content_type,
        file_size=len(data), file_path=rel, file_url=url, created_by=user_id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return att


def delete_attachment(db: Session, tenant_id: int, note_id: int, att_id: int) -> None:
    _require_note(db, note_id, tenant_id)
    att = db.execute(
        select(ProgressNoteAttachment).where(
            ProgressNoteAttachment.id == att_id,
            ProgressNoteAttachment.progress_note_id == note_id,
            ProgressNoteAttachment.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if att is None or att.is_deleted:
        raise NotFoundError(f"Attachment '{att_id}' was not found")
    att.is_deleted = True
    filestore.delete_file(att.file_path)
    db.commit()


# ── PN-6: macro category lookup ──────────────────────────────────────────────
def note_macro_categories(db: Session, tenant_id: int) -> list[dict]:
    rows = db.execute(
        select(NoteMacro.category, func.count())
        .where(NoteMacro.tenant_id == tenant_id, NoteMacro.category.is_not(None))
        .group_by(NoteMacro.category)
        .order_by(NoteMacro.category)
    ).all()
    return [{"category": cat, "macro_count": count} for cat, count in rows]
