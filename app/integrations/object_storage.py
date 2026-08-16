"""Object storage (GCS) access for the imaging layer.

Two responsibilities:

1. **Signed URLs** — turn a ``(bucket, object_key)`` into a short-lived V4 signed
   GCS URL the browser can fetch directly. ``google-cloud-storage`` is imported
   lazily (like ``reportlab``) so the app boots without it; if the library or
   signing credentials are unavailable, :func:`signed_url` returns ``None`` and
   the caller falls back to streaming the bytes through the API (proxy mode).

2. **Asset tokens** — a stable, browser-facing HMAC token embedded in the
   ``<img src>`` URLs the imaging API hands the frontend. It authorises exactly
   one instance's one asset (thumb/web/original) for one tenant, without a bearer
   header (an ``<img>`` tag can't set one) and independent of the short GCS
   signed-URL TTL. Same idea as the messaging WS query-token.

The bytes themselves never pass through here except in proxy mode (:func:`stream`).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from collections.abc import Iterator
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# kind -> which bucket the object lives in
_ORIGINAL = "original"
_WEB = "web"
_THUMB = "thumb"

_client = None
_client_tried = False


# ── GCS client (lazy) ────────────────────────────────────────────────────────
def _get_client() -> Any:
    global _client, _client_tried
    if _client is not None or _client_tried:
        return _client
    _client_tried = True
    try:
        from google.cloud import storage  # type: ignore

        if settings.GCS_CREDENTIALS_PATH:
            _client = storage.Client.from_service_account_json(settings.GCS_CREDENTIALS_PATH)
        else:
            _client = storage.Client()
    except Exception as exc:  # noqa: BLE001 - lib missing or no creds
        logger.info("GCS client unavailable (imaging runs in proxy mode): %s", exc)
        _client = None
    return _client


def bucket_for(kind: str) -> str | None:
    if kind == _ORIGINAL:
        return settings.GCS_BUCKET_ORIGINALS
    return settings.GCS_BUCKET_DERIVED


def gcs_configured() -> bool:
    return bool(settings.GCS_BUCKET_ORIGINALS or settings.GCS_BUCKET_DERIVED)


def signed_url(
    bucket: str,
    object_key: str,
    *,
    ttl_seconds: int | None = None,
    download_name: str | None = None,
) -> str | None:
    """Return a V4 signed GET URL, or ``None`` if signing isn't available.

    On Cloud Run without an embedded private key, signing needs the IAM
    ``signBlob`` permission (runtime SA must hold ``serviceAccountTokenCreator``
    on itself). If that isn't wired, ``generate_signed_url`` raises and we return
    ``None`` so the caller proxies instead.
    """
    if settings.IMAGING_URL_MODE == "proxy":
        return None
    client = _get_client()
    if client is None or not bucket:
        return None
    ttl = ttl_seconds or settings.IMAGING_SIGNED_URL_TTL_SECONDS
    try:
        blob = client.bucket(bucket).blob(object_key)
        disposition = f'inline; filename="{download_name}"' if download_name else None
        return blob.generate_signed_url(
            version="v4",
            expiration=ttl,
            method="GET",
            response_disposition=disposition,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Signed-URL generation failed for gs://%s/%s: %s", bucket, object_key, exc)
        return None


def upload_bytes(
    bucket: str,
    object_key: str,
    data: bytes,
    *,
    content_type: str = "application/octet-stream",
    create_only: bool = False,
) -> None:
    """Write ``data`` to ``gs://bucket/object_key``.

    ``create_only=True`` mirrors the migration uploader's
    ``if_generation_match=0`` (never overwrite an existing object — content-
    addressed keys mean a collision is the same bytes already there, so a
    412 here is treated as success, not an error).

    Raises ``RuntimeError`` if the GCS client/credentials aren't available —
    callers should treat that as a real failure, not silently drop the
    capture.
    """
    from google.api_core import exceptions as gexc

    client = _get_client()
    if client is None or not bucket:
        raise RuntimeError("GCS is not configured (client unavailable or bucket unset)")
    blob = client.bucket(bucket).blob(object_key)
    blob.content_type = content_type
    try:
        kwargs = {"content_type": content_type}
        if create_only:
            kwargs["if_generation_match"] = 0
        blob.upload_from_string(data, **kwargs)
    except gexc.PreconditionFailed:
        pass  # already there — same sha256, same bytes, dedup success


def stream(bucket: str, object_key: str) -> tuple[Iterator[bytes], str | None, int | None]:
    """Proxy-mode download: yield the object's bytes plus (content_type, size).

    Raises ``FileNotFoundError`` when the object or GCS is unavailable so the
    caller can turn it into a clean 404.
    """
    client = _get_client()
    if client is None or not bucket:
        raise FileNotFoundError("object storage not configured")
    blob = client.bucket(bucket).get_blob(object_key)
    if blob is None:
        raise FileNotFoundError(f"gs://{bucket}/{object_key}")

    def _gen() -> Iterator[bytes]:
        with blob.open("rb") as fh:
            while True:
                chunk = fh.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return _gen(), blob.content_type, blob.size


# ── Asset tokens (browser-facing, HMAC) ──────────────────────────────────────
def _sign(payload: str) -> str:
    mac = hmac.new(settings.JWT_SECRET_KEY.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def make_asset_token(
    sop_instance_uid: str, kind: str, tenant_id: int, *, ttl_seconds: int | None = None
) -> str:
    """Signed token authorising one asset of one instance for one tenant."""
    exp = int(time.time()) + (ttl_seconds or settings.IMAGING_ASSET_TOKEN_TTL_SECONDS)
    body = f"{sop_instance_uid}|{kind}|{tenant_id}|{exp}"
    body_b64 = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return f"{body_b64}.{_sign(body)}"


def verify_asset_token(token: str) -> tuple[str, str, int] | None:
    """Return ``(sop_instance_uid, kind, tenant_id)`` if valid, else ``None``."""
    try:
        body_b64, sig = token.split(".", 1)
        padded = body_b64 + "=" * (-len(body_b64) % 4)
        body = base64.urlsafe_b64decode(padded.encode()).decode()
        sop, kind, tenant_id, exp = body.split("|")
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        if int(exp) < int(time.time()):
            return None
        return sop, kind, int(tenant_id)
    except Exception:  # noqa: BLE001 - any malformed token is simply invalid
        return None
