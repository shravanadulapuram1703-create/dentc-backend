"""Real-time capture ingest: turn a freshly captured image/DICOM file into a
``stored_objects`` + ``dicom_studies``/``series``/``instances`` record —
GCS-uploaded and derivative-ready.

This is the live-capture counterpart to the DICOM migration toolkit
(``dicom_migration/``): ``02_upload.py`` (hash + content-addressed GCS
upload) + ``05_promote.py`` (studies/series/instances upsert) +
``06_derivatives.py`` (thumbnail/web JPEG generation), collapsed into one
synchronous call for a single new image instead of a bulk batch. Landing in
the exact same tables and bucket as migrated history is what "matches" a new
capture to a patient's legacy imaging — it's the same ``patient_id``, same
``stored_objects``/``dicom_studies`` rows the migration populates, not a
separate system.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models import DicomInstance, DicomSeries, DicomStudy, Patient, StoredObject
from app.integrations import object_storage as obj

logger = get_logger(__name__)

THUMB_EDGE = 320
WEB_EDGE = 2600


# ── small helpers ────────────────────────────────────────────────────────────
def _s(v) -> str | None:  # noqa: ANN001
    if v is None:
        return None
    try:
        s = str(v).strip()
        return s or None
    except Exception:  # noqa: BLE001
        return None


def _i(v) -> int | None:  # noqa: ANN001
    try:
        return int(v)
    except Exception:  # noqa: BLE001
        return None


def _dicom_date(s: str | None) -> date | None:
    """DICOM DA format YYYYMMDD -> date."""
    if not s or not s.isdigit() or len(s) != 8:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _synthetic_uid() -> str:
    """A valid DICOM UID (PS3.5 Annex B: the 2.25 root + a UUID-derived
    integer) for captures with no real DICOM header to draw one from — e.g.
    a plain camera JPEG. ``dicom_studies``/``series``/``instances`` all
    require a non-null unique UID regardless of source."""
    return f"2.25.{uuid.uuid4().int}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object_key(prefix: str, sha256_hex: str, ext: str) -> str:
    """Same layout as ``common.py::object_key_for`` in the migration
    toolkit: ``<prefix>/<aa>/<bb>/<sha256><ext>`` — content-addressed, so a
    capture whose bytes exactly match something already migrated collapses
    to the same object automatically."""
    return f"{prefix}/{sha256_hex[0:2]}/{sha256_hex[2:4]}/{sha256_hex}{ext}"


def _is_dicom(data: bytes) -> bool:
    return len(data) > 132 and data[128:132] == b"DICM"


def _parse_dicom(data: bytes):  # noqa: ANN202
    import pydicom

    return pydicom.dcmread(io.BytesIO(data), force=True)


def _to_image(ds):  # noqa: ANN001, ANN202
    """DICOM dataset -> 8-bit PIL Image, with basic windowing for 16-bit.
    Identical logic to ``06_derivatives.py::_to_image`` in the migration
    toolkit, so real-time derivatives look the same as migrated ones."""
    import numpy as np
    from PIL import Image

    arr = ds.pixel_array
    photometric = str(getattr(ds, "PhotometricInterpretation", "") or "")
    applied_wc = applied_ww = None

    if arr.ndim == 3:  # RGB / colour photo
        return Image.fromarray(arr.astype("uint8"), "RGB"), None, None

    arr = arr.astype("float32")
    if photometric == "MONOCHROME1":  # min = white -> invert to a normal look
        arr = arr.max() - arr

    bits_stored = int(getattr(ds, "BitsStored", 8) or 8)
    if bits_stored > 8:
        wc = getattr(ds, "WindowCenter", None)
        ww = getattr(ds, "WindowWidth", None)
        if wc is not None and ww is not None:
            wc = float(wc[0] if hasattr(wc, "__iter__") and not isinstance(wc, str) else wc)
            ww = float(ww[0] if hasattr(ww, "__iter__") and not isinstance(ww, str) else ww)
        else:  # robust default: 1st-99th percentile stretch
            lo_p, hi_p = np.percentile(arr, [1, 99])
            wc, ww = (lo_p + hi_p) / 2.0, max(hi_p - lo_p, 1.0)
        applied_wc, applied_ww = wc, ww
        lo, hi = wc - ww / 2.0, wc + ww / 2.0
        arr = np.clip((arr - lo) / max(hi - lo, 1.0), 0, 1) * 255.0

    return Image.fromarray(arr.astype("uint8"), "L"), applied_wc, applied_ww


def _encode(img, edge: int, quality: int) -> bytes:  # noqa: ANN001
    from PIL import Image

    w, h = img.size
    scale = min(1.0, edge / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, progressive=(edge == WEB_EDGE), optimize=True)
    return buf.getvalue()


def _decode_for_derivatives(data: bytes, is_dicom: bool):  # noqa: ANN201
    """(PIL.Image, applied_wc, applied_ww) for either a real DICOM capture
    or a plain raster (camera JPEG/PNG)."""
    from PIL import Image

    if is_dicom:
        ds = _parse_dicom(data)
        if "PixelRepresentation" not in ds:
            ds.PixelRepresentation = 0
        if "PlanarConfiguration" not in ds and int(getattr(ds, "SamplesPerPixel", 1) or 1) > 1:
            ds.PlanarConfiguration = 0
        return _to_image(ds)
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return img, None, None


# ── upserts (single-row — this is one capture at a time, not a bulk batch) ──
def _upsert_stored_object(
    db: Session, *, tenant_id: int, bucket: str, object_key: str, kind: str,
    content_type: str, size_bytes: int, sha256: str,
) -> StoredObject:
    existing = db.execute(
        select(StoredObject).where(StoredObject.bucket == bucket, StoredObject.object_key == object_key)
    ).scalar_one_or_none()
    if existing:
        existing.sha256 = sha256
        existing.size_bytes = size_bytes
        db.flush()
        return existing
    row = StoredObject(
        tenant_id=tenant_id, bucket=bucket, object_key=object_key, kind=kind,
        content_type=content_type, size_bytes=size_bytes, sha256=sha256, ref_count=1,
    )
    db.add(row)
    db.flush()
    return row


def _upsert_study(
    db: Session, *, tenant_id: int, patient_id: int, study_instance_uid: str,
    study_date: date | None, study_time: str | None, accession_number: str | None,
    description: str | None, modality: str,
) -> DicomStudy:
    existing = db.execute(
        select(DicomStudy).where(DicomStudy.study_instance_uid == study_instance_uid)
    ).scalar_one_or_none()
    if existing:
        existing.patient_id = patient_id
        mods = set(existing.modalities or [])
        mods.add(modality)
        existing.modalities = sorted(mods)
        db.flush()
        return existing
    row = DicomStudy(
        tenant_id=tenant_id, patient_id=patient_id, study_instance_uid=study_instance_uid,
        accession_number=accession_number, study_date=study_date, study_time=study_time,
        description=description, modalities=[modality], is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


def _upsert_series(
    db: Session, *, tenant_id: int, study_id: int, series_instance_uid: str,
    modality: str, body_part: str | None, description: str | None,
) -> DicomSeries:
    existing = db.execute(
        select(DicomSeries).where(DicomSeries.series_instance_uid == series_instance_uid)
    ).scalar_one_or_none()
    if existing:
        existing.modality = modality
        db.flush()
        return existing
    row = DicomSeries(
        tenant_id=tenant_id, study_id=study_id, series_instance_uid=series_instance_uid,
        modality=modality, body_part=body_part, description=description, is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


def _upsert_instance(
    db: Session, *, tenant_id: int, series_id: int, sop_instance_uid: str,
    sop_class_uid: str | None, instance_number: str | None, rows: int | None,
    columns: int | None, bits_allocated: int | None, photometric_interpretation: str | None,
    window_center: str | None, window_width: str | None, original_object_id: int,
) -> DicomInstance:
    existing = db.execute(
        select(DicomInstance).where(DicomInstance.sop_instance_uid == sop_instance_uid)
    ).scalar_one_or_none()
    if existing:
        existing.original_object_id = original_object_id
        db.flush()
        return existing
    row = DicomInstance(
        tenant_id=tenant_id, series_id=series_id, sop_instance_uid=sop_instance_uid,
        sop_class_uid=sop_class_uid, instance_number=instance_number, rows=rows,
        columns=columns, bits_allocated=bits_allocated,
        photometric_interpretation=photometric_interpretation, window_center=window_center,
        window_width=window_width, original_object_id=original_object_id,
        derivative_status="pending", is_deleted=False,
    )
    db.add(row)
    db.flush()
    return row


# ── entry point ──────────────────────────────────────────────────────────────
def ingest_capture(
    db: Session,
    *,
    tenant_id: int,
    patient_id: int,
    data: bytes,
    content_type: str,
    modality_hint: str | None = None,
    description: str | None = None,
) -> DicomInstance:
    """Hash -> content-addressed GCS upload -> dicom_studies/series/instances
    upsert -> decode + thumb/web derivative upload -> mark ready.

    Derivatives are generated synchronously (not deferred to a separate
    worker): a real-time capture needs to be viewable right away, unlike a
    bulk migration batch. If derivative generation fails, the original is
    still safely uploaded and indexed — only ``derivative_status`` reflects
    the failure, matching how 06_derivatives.py treats per-image failures as
    non-fatal.
    """
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")

    originals_bucket = settings.GCS_BUCKET_ORIGINALS
    if not originals_bucket:
        raise RuntimeError("GCS_BUCKET_ORIGINALS is not configured")

    is_dicom = _is_dicom(data)
    sha = _sha256(data)
    original_ext = ".dcm" if is_dicom else ".jpg"
    original_key = _object_key(settings.GCS_ORIGINALS_PREFIX, sha, original_ext)
    obj.upload_bytes(originals_bucket, original_key, data, content_type=content_type, create_only=True)

    original_obj = _upsert_stored_object(
        db, tenant_id=tenant_id, bucket=originals_bucket, object_key=original_key,
        kind="original", content_type=content_type, size_bytes=len(data), sha256=sha,
    )

    if is_dicom:
        ds = _parse_dicom(data)
        study_uid = _s(ds.get("StudyInstanceUID")) or _synthetic_uid()
        series_uid = _s(ds.get("SeriesInstanceUID")) or study_uid
        sop_uid = _s(ds.get("SOPInstanceUID")) or _synthetic_uid()
        sop_class_uid = _s(ds.get("SOPClassUID"))
        modality = _s(ds.get("Modality")) or modality_hint or "IO"
        study_date = _dicom_date(_s(ds.get("StudyDate"))) or date.today()
        study_time = _s(ds.get("StudyTime"))
        accession_number = _s(ds.get("AccessionNumber"))
        rows_, cols_ = _i(ds.get("Rows")), _i(ds.get("Columns"))
        bits_allocated = _i(ds.get("BitsAllocated"))
        photometric = _s(ds.get("PhotometricInterpretation"))
        window_center = _s(ds.get("WindowCenter"))
        window_width = _s(ds.get("WindowWidth"))
        instance_number = _s(ds.get("InstanceNumber"))
        body_part = _s(ds.get("BodyPartExamined"))
    else:
        # No real DICOM header (camera photo) — each capture is its own
        # single-instance study; synthetic UIDs per PS3.5 Annex B.
        study_uid = _synthetic_uid()
        series_uid = _synthetic_uid()
        sop_uid = _synthetic_uid()
        sop_class_uid = None
        modality = modality_hint or "OT"
        study_date = date.today()
        study_time = None
        accession_number = None
        rows_ = cols_ = bits_allocated = None
        photometric = window_center = window_width = None
        instance_number = None
        body_part = None

    study = _upsert_study(
        db, tenant_id=tenant_id, patient_id=patient_id, study_instance_uid=study_uid,
        study_date=study_date, study_time=study_time, accession_number=accession_number,
        description=description, modality=modality,
    )
    series = _upsert_series(
        db, tenant_id=tenant_id, study_id=study.id, series_instance_uid=series_uid,
        modality=modality, body_part=body_part, description=description,
    )
    instance = _upsert_instance(
        db, tenant_id=tenant_id, series_id=series.id, sop_instance_uid=sop_uid,
        sop_class_uid=sop_class_uid, instance_number=instance_number, rows=rows_, columns=cols_,
        bits_allocated=bits_allocated, photometric_interpretation=photometric,
        window_center=window_center, window_width=window_width,
        original_object_id=original_obj.id,
    )

    try:
        img, awc, aww = _decode_for_derivatives(data, is_dicom)
        thumb_bytes = _encode(img, THUMB_EDGE, 80)
        web_bytes = _encode(img, WEB_EDGE, 85)
        derived_bucket = settings.GCS_BUCKET_DERIVED or originals_bucket
        thumb_key = f"{settings.GCS_DERIVED_PREFIX}/thumb/{sha}.jpg"
        web_key = f"{settings.GCS_DERIVED_PREFIX}/web/{sha}.jpg"
        obj.upload_bytes(derived_bucket, thumb_key, thumb_bytes, content_type="image/jpeg")
        obj.upload_bytes(derived_bucket, web_key, web_bytes, content_type="image/jpeg")
        thumb_obj = _upsert_stored_object(
            db, tenant_id=tenant_id, bucket=derived_bucket, object_key=thumb_key,
            kind="thumb", content_type="image/jpeg", size_bytes=len(thumb_bytes), sha256=sha,
        )
        web_obj = _upsert_stored_object(
            db, tenant_id=tenant_id, bucket=derived_bucket, object_key=web_key,
            kind="web", content_type="image/jpeg", size_bytes=len(web_bytes), sha256=sha,
        )
        instance.thumb_object_id = thumb_obj.id
        instance.web_object_id = web_obj.id
        instance.applied_window_center = str(awc) if awc is not None else None
        instance.applied_window_width = str(aww) if aww is not None else None
        instance.derivative_status = "ready"
        instance.derivative_error = None
    except Exception as exc:  # noqa: BLE001 — the original is safely stored either way
        logger.warning("Derivative generation failed for %s: %r", sop_uid, exc)
        instance.derivative_status = "failed"
        instance.derivative_error = repr(exc)[:2000]

    db.commit()
    db.refresh(instance)
    return instance
