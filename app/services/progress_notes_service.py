"""Progress-notes business logic (addresses the frontend progress-notes report).

- **PN-7/PN-4/PN-8/PN-9/PN-11** ``ProgressNoteCRUD`` — a CRUDBase subclass wired
  into the generic engine that scopes tenancy through the patient (the table
  has no ``tenant_id``), enforces the server-side lock (signed or prior-day
  notes reject text edits — the *day* being the note's office's local day),
  keeps the Date of Service correctable after the prior-day lock, maintains
  the strike-off audit (``struck_off_at``/``struck_off_by``) on the
  false→true / true→false transition, and delegates to ``CRUDBase.update`` so
  every real change stamps ``updated_at``/``updated_by`` and lands its
  before/after diff in ``audit_logs`` (the PN-8 open question: a DOS
  correction *is* audited, field-level).
- **PN-12** the write path derives ``notes`` from ``notes_html`` when a client
  sends only the rich body, so the plain column ``search=`` runs against
  cannot drift from what the screen shows.
- **PN-5/PN-3/PN-7** ``enrich_progress_notes`` — read hook: resolves actor
  names, the per-note attachment count, and the computed ``is_locked`` /
  ``locks_at`` / ``timezone`` (no N+1).
- **PN-2** ``sign_progress_note`` — sign as the caller, or as a verified provider
  (over-the-shoulder credentials).
- **PN-3** per-note attachment list/create/delete.
- **PN-6** ``note_macro_categories`` — distinct macro categories, labelled.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import filestore
from app.core.datetimes import as_utc, office_tz
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.crud.base import CRUDBase
from app.db.models import (
    NoteMacro,
    Office,
    Patient,
    ProgressNote,
    ProgressNoteAttachment,
)
from app.services import auth_service
from app.services import note_macro_service as macro_svc
from app.services import signature_service as sig_svc
from app.services.progress_note_content import html_to_text
from app.services.user_admin_service import resolve_user_names

# PN-7 lock scope. ``note_date`` is deliberately NOT here (PN-8): doctors write
# notes days after the visit and often pick the wrong Date of Service, so the
# DOS stays correctable after the prior-day lock. Signing still freezes it.
_TEXT_FIELDS = ("notes", "notes_html", "tooth", "surface", "region")


def _attachment_url(note_id: int, att_id: int) -> str:
    """NOTE-DOC-3: the authenticated streaming URL for a note attachment.

    Attachments used to be handed back as ``/uploads/...``, served by a public
    static mount with no token and no tenant check. That mount is gone; this is
    the only way to read the bytes.
    """
    from app.core.config import settings
    from app.services import document_store

    return document_store.absolute_url(
        f"{settings.API_V1_PREFIX}/progress-notes/{note_id}/attachments/{att_id}/content"
    )


# ── PN-9: the note's clock ───────────────────────────────────────────────────
def _tenant_patient_ids(tenant_id: int):  # noqa: ANN202
    """Subquery of the patient ids in ``tenant_id`` — the only handle the
    progress-note tables have on tenancy."""
    return select(Patient.id).where(Patient.tenant_id == tenant_id)


def note_timezones(db: Session, notes: Iterable[ProgressNote]) -> dict[int, ZoneInfo]:
    """``{note_id: zone}`` — the office the note was written in, else the
    patient's home office, else the default zone. Batched (two statements for
    any number of notes) because the list feed calls this per page.

    PN-9: ``created_at`` is UTC. A US-Eastern note written at 3 PM used to
    lock at 8 PM local (00:00 UTC) and one written after 8 PM read as created
    "tomorrow"; the lock day has to be judged on the office's clock.
    """
    rows = list(notes)
    if not rows:
        return {}
    patient_ids = {r.patient_id for r in rows if r.office_id is None}
    home_office: dict[int, int | None] = {}
    if patient_ids:
        home_office = dict(
            db.execute(
                select(Patient.id, Patient.home_office_id).where(Patient.id.in_(patient_ids))
            ).all()
        )
    office_ids = {r.office_id for r in rows if r.office_id is not None}
    office_ids |= {oid for oid in home_office.values() if oid is not None}
    tz_by_office: dict[int, str | None] = {}
    if office_ids:
        tz_by_office = dict(
            db.execute(select(Office.id, Office.timezone).where(Office.id.in_(office_ids))).all()
        )
    out: dict[int, ZoneInfo] = {}
    for r in rows:
        oid = r.office_id if r.office_id is not None else home_office.get(r.patient_id)
        out[r.id] = office_tz(tz_by_office.get(oid) if oid is not None else None)
    return out


def note_lock_instant(note: ProgressNote, tz: ZoneInfo) -> datetime | None:
    """The UTC instant the note's text locks: office-local midnight after the
    creation day. ``None`` when the note has no ``created_at`` yet."""
    if note.created_at is None:
        return None
    local_created = as_utc(note.created_at).astimezone(tz)
    next_midnight = datetime.combine(local_created.date() + timedelta(days=1), datetime.min.time(), tz)
    return next_midnight.astimezone(timezone.utc)


def _note_is_locked(note: ProgressNote, tz: ZoneInfo, now: datetime | None = None) -> bool:
    """PN-7/PN-9: a note locks once signed, or after midnight — *the office's*
    midnight — of its creation day."""
    if note.signed_at is not None:
        return True
    if note.created_at is None:
        return False
    now = as_utc(now) if now is not None else datetime.now(timezone.utc)
    return as_utc(note.created_at).astimezone(tz).date() < now.astimezone(tz).date()


def _derive_plain_text(data: dict[str, Any]) -> None:
    """PN-12: a client that sends only ``notes_html`` gets ``notes`` derived
    from it, so the searchable column never holds a stale or empty body."""
    if "notes_html" in data and data.get("notes") is None and data["notes_html"] is not None:
        derived = html_to_text(data["notes_html"])
        data["notes"] = derived or None


# ── PN-7 / PN-4 / PN-8 / PN-11: lock enforcement + audit on the write path ──
class ProgressNoteCRUD(CRUDBase):
    def _scope_tenant(self, stmt, tenant_id: int | None):  # noqa: ANN001
        # progress_notes has no tenant_id: scope through the patient, else a
        # note id from another practice reads and patches.
        if tenant_id is None:
            return stmt
        return stmt.where(ProgressNote.patient_id.in_(_tenant_patient_ids(tenant_id)))

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001
        payload = dict(data)
        if tenant_id is not None and "patient_id" in payload:
            owner = db.execute(
                select(Patient.id).where(
                    Patient.id == payload["patient_id"], Patient.tenant_id == tenant_id
                )
            ).scalar_one_or_none()
            if owner is None:
                raise NotFoundError(f"Patient '{payload['patient_id']}' was not found")
        _derive_plain_text(payload)
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(self, db, obj_id, data, *, tenant_id=None, updated_by=None):  # noqa: ANN001
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        data = dict(data)
        # struck_off_* are server-managed — never honour a client-supplied value.
        data.pop("struck_off_at", None)
        data.pop("struck_off_by", None)
        _derive_plain_text(data)

        # PN-7/PN-9: reject text mutations on a locked note (signing/strike-off
        # still ok). "Today" is the note's office's today, not UTC's.
        tz = note_timezones(db, [obj])[obj.id]
        if _note_is_locked(obj, tz):
            changed = [f for f in _TEXT_FIELDS if f in data and data[f] != getattr(obj, f)]
            if changed:
                raise ConflictError(
                    "This note is locked (signed or from a prior day) and cannot be edited",
                    details={"locked_fields": changed, "timezone": str(tz)},
                )
        # PN-8: the DOS survives the prior-day lock but not a signature.
        if obj.signed_at is not None and "note_date" in data:
            new_dos = data["note_date"]
            if isinstance(new_dos, str):
                new_dos = date.fromisoformat(new_dos)
            if new_dos != obj.note_date:
                raise ConflictError(
                    "This note is signed; its Date of Service can no longer be changed",
                    details={"locked_fields": ["note_date"]},
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

        # PN-11 + PN-8: the engine diffs first (a no-op PATCH stamps nothing),
        # stamps updated_by, and hands the before/after diff to the audit
        # context — so a Date-of-Service correction is recorded field-level.
        return super().update(db, obj_id, data, tenant_id=tenant_id, updated_by=updated_by)


# ── PN-5 / PN-3 / PN-7 / PN-9 / PN-11: read enrichment ───────────────────────
def enrich_progress_notes(db: Session, items, tenant_id: int | None = None) -> None:  # noqa: ARG001
    rows = list(items)
    if not rows:
        return
    wanted: set[int] = set()
    for r in rows:
        for actor in (r.created_by, r.updated_by, r.signed_by, r.struck_off_by):
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

    zones = note_timezones(db, rows)
    now = datetime.now(timezone.utc)
    for r in rows:
        tz = zones[r.id]
        r.signature_status = sig_svc.progress_note_signature_status(r)  # SIG-7
        r.created_by_name = names.get(r.created_by) if r.created_by is not None else None
        r.updated_by_name = names.get(r.updated_by) if r.updated_by is not None else None
        r.signed_by_name = names.get(r.signed_by) if r.signed_by is not None else None
        r.struck_off_by_name = names.get(r.struck_off_by) if r.struck_off_by is not None else None
        r.attachment_count = counts.get(r.id, 0)
        r.is_locked = _note_is_locked(r, tz, now)
        r.locks_at = None if r.is_locked else note_lock_instant(r, tz)
        r.timezone = str(tz)


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
    # SIG-7: freeze the content the signature attests to, so a later edit
    # flips ``signature_status`` to ``stale`` instead of silently re-attesting.
    note.content_hash = sig_svc.progress_note_content_hash(note)
    db.commit()
    db.refresh(note)
    return note


# ── PN-3: per-note attachments ───────────────────────────────────────────────
def list_attachments(db: Session, tenant_id: int, note_id: int) -> list[ProgressNoteAttachment]:
    _require_note(db, note_id, tenant_id)
    rows = list(
        db.execute(
            select(ProgressNoteAttachment)
            .where(
                ProgressNoteAttachment.progress_note_id == note_id,
                ProgressNoteAttachment.is_deleted.is_(False),
            )
            .order_by(ProgressNoteAttachment.created_at.desc())
        ).scalars().all()
    )
    for row in rows:
        row.file_url = _attachment_url(note_id, row.id)
    return rows


def create_attachment(
    db: Session, tenant_id: int, note_id: int, *, attachment_type: str | None,
    description: str | None, file_name: str, content_type: str | None,
    data: bytes, user_id: int | None,
) -> ProgressNoteAttachment:
    _require_note(db, note_id, tenant_id)
    filestore.validate_upload(file_name, content_type, data)
    rel, _public = filestore.save_file(f"progress_note_attachments/{note_id}", file_name, data)
    att = ProgressNoteAttachment(
        tenant_id=tenant_id, progress_note_id=note_id, attachment_type=attachment_type,
        description=description, file_name=file_name, content_type=content_type,
        # NOTE-DOC-3: file_url is the authenticated /content route, stamped once
        # the row has an id. Never the public /uploads path.
        file_size=len(data), file_path=rel, file_url="", created_by=user_id,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    att.file_url = _attachment_url(note_id, att.id)
    return att


def open_attachment(db: Session, tenant_id: int, note_id: int, att_id: int):  # noqa: ANN201
    """Body + headers for ``GET /progress-notes/{id}/attachments/{id}/content``."""
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
    try:
        body, size = filestore.open_stream(att.file_path)
    except FileNotFoundError as exc:
        raise NotFoundError(f"Attachment '{att_id}' content is not available") from exc
    return att, body, att.content_type, size


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
    """Distinct stored categories with a display ``label`` — a Denticon code
    (``179``) resolves through the tenant's ``NOTESMACROS`` definitions, a
    label stored as-is is its own label."""
    rows = db.execute(
        select(NoteMacro.category, func.count())
        .where(NoteMacro.tenant_id == tenant_id, NoteMacro.category.is_not(None))
        .group_by(NoteMacro.category)
        .order_by(NoteMacro.category)
    ).all()
    labels = macro_svc.category_labels(db, tenant_id)
    out = [
        {"category": cat, "label": macro_svc.category_label(cat, labels), "macro_count": count}
        for cat, count in rows
    ]
    out.sort(key=lambda c: (c["label"] or "").lower())
    return out
