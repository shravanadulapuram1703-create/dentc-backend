"""Binary storage for patient documents & consent forms (LTR-1).

Consent PDFs printed from the Letters dialog are patient-facing legal records the
practice keeps in a cloud bucket (``gs://reco-documents/consent-forms/``). Before
this module they were written to the app server's local disk and handed back as a
server-relative path, so they did not survive a Cloud Run container restart and
nothing else in the estate could find them.

Routing
-------
``document_type`` decides the object prefix::

    consent-form    -> gs://{BUCKET}/{GCS_CONSENT_FORMS_PREFIX}/{tenant}/{patient}/{uuid}.pdf
    everything else -> gs://{BUCKET}/{GCS_DOCUMENTS_PREFIX}/{tenant}/{patient}/{uuid}{ext}

With ``GCS_BUCKET_DOCUMENTS`` unset the bytes stay on the local filesystem — dev
and the test suite run with no cloud credentials, exactly as before.

URLs
----
``file_url`` is always something a browser can fetch: a short-lived V4 signed GCS
URL when signing is available, otherwise the authenticated proxy
``GET /api/v1/patient-documents/{id}/content``, absolute when
``PUBLIC_API_BASE_URL`` is configured. The frontend never sees a ``gs://`` URI and
never holds bucket credentials.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.core import filestore
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations import object_storage as obj

logger = get_logger(__name__)

LOCAL = "local"
GCS = "gcs"


@dataclass(slots=True)
class StoredObject:
    """Where a freshly-written blob landed."""

    backend: str            # local | gcs
    bucket: str | None      # GCS bucket (None for local)
    path: str               # object key (GCS) or path under UPLOAD_DIR (local)
    url: str                # browser-fetchable URL (local rows only; GCS is late-bound)


def gcs_enabled() -> bool:
    return bool(settings.GCS_BUCKET_DOCUMENTS)


def is_consent_type(document_type: str | None) -> bool:
    return (document_type or "").strip().lower() in {
        t.lower() for t in settings.CONSENT_DOCUMENT_TYPES
    }


def prefix_for(document_type: str | None) -> str:
    return (
        settings.GCS_CONSENT_FORMS_PREFIX
        if is_consent_type(document_type)
        else settings.GCS_DOCUMENTS_PREFIX
    )


def object_key(tenant_id: int, patient_id: int, document_type: str | None, file_name: str) -> str:
    ext = Path(file_name or "").suffix or (".pdf" if is_consent_type(document_type) else "")
    return f"{prefix_for(document_type)}/{tenant_id}/{patient_id}/{uuid.uuid4().hex}{ext}"


def absolute_url(path: str) -> str:
    """Fully-qualify an API path against ``PUBLIC_API_BASE_URL`` when configured."""
    base = (settings.PUBLIC_API_BASE_URL or "").rstrip("/")
    return f"{base}{path}" if base else path


def content_path(document_id: int) -> str:
    return f"{settings.API_V1_PREFIX}/patient-documents/{document_id}/content"


def store(
    *,
    tenant_id: int,
    patient_id: int,
    document_type: str | None,
    file_name: str,
    content_type: str | None,
    data: bytes,
) -> StoredObject:
    """Write the bytes and report where they went.

    Falls back to local storage (with a logged error) when GCS is configured but
    the upload fails — dropping a just-printed consent form because the bucket is
    unreachable would be worse than keeping it on the pod until someone notices.
    """
    if gcs_enabled():
        bucket = settings.GCS_BUCKET_DOCUMENTS
        key = object_key(tenant_id, patient_id, document_type, file_name)
        try:
            obj.upload_bytes(
                bucket, key, data,
                content_type=content_type or "application/octet-stream",
            )
            return StoredObject(backend=GCS, bucket=bucket, path=key, url="")
        except Exception as exc:  # noqa: BLE001 - lib missing, creds, network
            logger.error(
                "GCS upload failed for gs://%s/%s - falling back to local storage: %s",
                bucket, key, exc,
            )

    rel, url = filestore.save_file(f"patient_documents/{patient_id}", file_name, data)
    return StoredObject(backend=LOCAL, bucket=None, path=rel, url=url)


def public_url(doc) -> str:  # noqa: ANN001 - PatientDocument (import cycle otherwise)
    """The URL to hand the frontend for ``doc``.

    GCS rows get a signed URL when signing works; otherwise (and always in
    ``DOCUMENT_URL_MODE=proxy``) the authenticated streaming endpoint, which
    applies the caller's tenant checks before a byte moves.
    """
    if getattr(doc, "storage_backend", LOCAL) == GCS and doc.storage_bucket and doc.storage_path:
        if settings.DOCUMENT_URL_MODE != "proxy":
            signed = obj.signed_url(
                doc.storage_bucket, doc.storage_path,
                ttl_seconds=settings.DOCUMENT_SIGNED_URL_TTL_SECONDS,
                download_name=doc.file_name,
            )
            if signed:
                return signed
        return absolute_url(content_path(doc.id))
    # Local rows keep the existing /uploads path, absolutised when configured.
    url = doc.file_url or ""
    return absolute_url(url) if url.startswith("/") else url


def open_stream(doc) -> tuple[Iterator[bytes], str | None, int | None]:  # noqa: ANN001
    """Yield the object's bytes for the proxy endpoint.

    Raises ``FileNotFoundError`` when the blob is gone so the caller can 404.
    """
    if getattr(doc, "storage_backend", LOCAL) == GCS and doc.storage_bucket and doc.storage_path:
        return obj.stream(doc.storage_bucket, doc.storage_path)

    local = Path(settings.UPLOAD_DIR) / (doc.storage_path or doc.file_path)
    if not local.is_file():
        raise FileNotFoundError(str(local))
    size = local.stat().st_size

    def _gen() -> Iterator[bytes]:
        with local.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return _gen(), doc.content_type, size


def delete(doc) -> None:  # noqa: ANN001
    """Best-effort removal of the underlying blob (the row itself is soft-deleted).

    GCS objects are deliberately left in place: the bucket's retention/lifecycle
    policy owns a signed clinical record, and the soft-deleted row is the marker.
    """
    if getattr(doc, "storage_backend", LOCAL) == GCS:
        return
    filestore.delete_file(doc.storage_path or doc.file_path)


def list_consent_masters(prefix: str | None = None, limit: int = 500) -> list[dict]:
    """LTR-1 ask #4: the blank consent-form masters already sitting in the bucket.

    Returns ``[]`` when GCS isn't configured (dev), so the endpoint is always safe
    to call. Read-only: it lists the bucket, it never mutates it.
    """
    if not gcs_enabled():
        return []
    client = obj._get_client()  # noqa: SLF001 - same package, single lazy client
    if client is None:
        return []
    bucket = settings.GCS_BUCKET_DOCUMENTS
    key_prefix = (prefix or settings.GCS_CONSENT_FORMS_PREFIX).strip("/") + "/"
    out: list[dict] = []
    for blob in client.list_blobs(bucket, prefix=key_prefix, max_results=limit):
        if blob.name.endswith("/"):
            continue
        out.append({
            "name": Path(blob.name).name,
            "storage_bucket": bucket,
            "storage_path": blob.name,
            "content_type": blob.content_type,
            "size": blob.size,
            "updated_at": blob.updated.isoformat() if blob.updated else None,
            "url": obj.signed_url(
                bucket, blob.name,
                ttl_seconds=settings.DOCUMENT_SIGNED_URL_TTL_SECONDS,
                download_name=Path(blob.name).name,
            ),
        })
    return out
