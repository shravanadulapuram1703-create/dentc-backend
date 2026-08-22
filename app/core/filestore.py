"""Local-filesystem upload helper + the shared server-side upload rules.

Writes under ``settings.UPLOAD_DIR/<subdir>`` and returns ``(relative_path, url)``.
Patient documents route through :mod:`app.services.document_store` instead, which
prefers GCS and only falls back here.

NOTE-DOC-3: ``UPLOAD_DIR`` is **not** a public directory. It holds PHI (patient
documents, claim and progress-note attachments) alongside branding assets, so
only ``settings.UPLOAD_PUBLIC_SUBDIRS`` is mounted as static files (see
``app/main.py``); everything else is served by an authenticated ``/content``
endpoint that re-checks tenancy.

NOTE-DOC-5: :func:`validate_upload` is the one place the size cap and the
content-type allow-list live, so every upload route enforces the same rules and
``GET /patient-documents/limits`` can publish them to the UI without a second copy.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import ValidationError

# Declared types that carry no information — a scanner or an older browser sends
# these for any file at all, so they defer to the extension rather than failing.
_UNINFORMATIVE_TYPES = {"", "application/octet-stream", "binary/octet-stream"}


def upload_limits() -> dict:
    """The published upload rules (NOTE-DOC-5), as data.

    Served by ``GET /patient-documents/limits`` so the file picker states exactly
    the limits the API enforces instead of keeping its own hardcoded copy.
    """
    return {
        "max_bytes": settings.DOCUMENT_MAX_BYTES,
        "max_megabytes": round(settings.DOCUMENT_MAX_BYTES / (1024 * 1024), 2),
        "allowed_content_types": list(settings.DOCUMENT_ALLOWED_TYPES),
        "allowed_extensions": list(settings.DOCUMENT_ALLOWED_EXTENSIONS),
    }


def validate_upload(file_name: str | None, content_type: str | None, data: bytes) -> None:
    """Reject an upload that breaks the size cap or the type allow-list.

    Raises :class:`ValidationError` (a 422 with a readable ``message``) — the
    frontend shows it verbatim, so the text names the actual limit rather than
    saying "invalid file".

    Both halves of the check must pass, but a *missing or uninformative* declared
    content type is not treated as a failure: browsers and TWAIN scanners send
    ``application/octet-stream`` for real PDFs, and rejecting those would break
    the Document (Scan) path for no security gain — the extension still has to be
    on the list either way.
    """
    max_bytes = settings.DOCUMENT_MAX_BYTES
    if len(data) > max_bytes:
        raise ValidationError(
            f"File exceeds the {round(max_bytes / (1024 * 1024), 2)} MB limit "
            f"({round(len(data) / (1024 * 1024), 2)} MB uploaded)",
            code="file_too_large",
            details={"max_bytes": max_bytes, "size": len(data)},
        )
    if not data:
        raise ValidationError("File is empty", code="file_empty")

    ext = Path(file_name or "").suffix.lower()
    allowed_ext = {e.lower() for e in settings.DOCUMENT_ALLOWED_EXTENSIONS}
    if ext not in allowed_ext:
        raise ValidationError(
            f"'{ext or file_name or 'file'}' is not an accepted file type. "
            f"Allowed: {', '.join(sorted(allowed_ext))}",
            code="unsupported_file_type",
            details={"allowed_extensions": sorted(allowed_ext)},
        )

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared in _UNINFORMATIVE_TYPES:
        return
    allowed_types = {t.lower() for t in settings.DOCUMENT_ALLOWED_TYPES}
    if declared not in allowed_types:
        raise ValidationError(
            f"Content type '{declared}' is not accepted. "
            f"Allowed: {', '.join(sorted(allowed_types))}",
            code="unsupported_content_type",
            details={"allowed_content_types": sorted(allowed_types)},
        )


def save_file(subdir: str, original_name: str, data: bytes) -> tuple[str, str]:
    directory = Path(settings.UPLOAD_DIR) / subdir
    directory.mkdir(parents=True, exist_ok=True)
    ext = Path(original_name or "").suffix
    stored = f"{uuid.uuid4().hex}{ext}"
    (directory / stored).write_bytes(data)
    rel = f"{subdir}/{stored}"
    return rel, f"{settings.UPLOAD_URL_BASE}/{rel}"


def open_stream(rel_path: str | None, chunk_size: int = 1024 * 1024):  # noqa: ANN201
    """Yield a locally-stored file's bytes for an authenticated ``/content`` route.

    Raises ``FileNotFoundError`` when the blob is gone so the caller can 404.
    """
    if not rel_path:
        raise FileNotFoundError("no stored path")
    local = Path(settings.UPLOAD_DIR) / rel_path
    if not local.is_file():
        raise FileNotFoundError(str(local))

    def _gen():  # noqa: ANN202
        with local.open("rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return _gen(), local.stat().st_size


def delete_file(rel_path: str | None) -> None:
    if not rel_path:
        return
    try:
        (Path(settings.UPLOAD_DIR) / rel_path).unlink(missing_ok=True)
    except OSError:
        pass
