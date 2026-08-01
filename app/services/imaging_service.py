"""Imaging (DICOM archive) read + serving logic.

Builds the per-patient study→series→instance tree in a fixed number of queries
(never N+1), and turns each instance's object-storage links into stable,
browser-facing asset URLs. The bytes are served either as a redirect to a GCS
signed URL (prod) or streamed through the API (proxy/dev) — see
:mod:`app.integrations.object_storage`.

Nothing here decodes DICOM: thumbnails/web JPEGs are produced by the separate
derivative worker (per the migration plan). This layer only indexes and serves.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.db.models import (
    DicomInstance,
    DicomSeries,
    DicomStudy,
    Patient,
    StoredObject,
)
from app.integrations import object_storage as obj

# endpoint path segment per asset kind (also the token 'kind')
_KIND_PATH = {"thumb": "thumbnail", "web": "web", "original": "original"}


def _verify_patient(db: Session, patient_id: int, tenant_id: int) -> None:
    found = db.execute(
        select(Patient.id).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if found is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")


def _asset_url(sop_instance_uid: str, kind: str, tenant_id: int) -> str:
    token = obj.make_asset_token(sop_instance_uid, kind, tenant_id)
    path = _KIND_PATH[kind]
    return f"{settings.API_V1_PREFIX}/dicom-instances/{sop_instance_uid}/{path}?token={token}"


def _build_assets(inst: DicomInstance, tenant_id: int) -> dict:
    has_web = inst.web_object_id is not None
    has_thumb = inst.thumb_object_id is not None
    has_original = inst.original_object_id is not None
    if has_web:
        status = "ready"
    elif inst.derivative_status == "failed":
        status = "failed"
    else:
        status = "pending"
    sop = inst.sop_instance_uid
    return {
        "status": status,
        "thumbnail_url": _asset_url(sop, "thumb", tenant_id) if has_thumb else None,
        "web_url": _asset_url(sop, "web", tenant_id) if has_web else None,
        "original_url": _asset_url(sop, "original", tenant_id) if has_original else None,
    }


def _instance_out(inst: DicomInstance, modality: str | None, tenant_id: int) -> dict:
    return {
        "id": inst.id,
        "sop_instance_uid": inst.sop_instance_uid,
        "sop_class_uid": inst.sop_class_uid,
        "instance_number": inst.instance_number,
        "modality": modality,
        "rows": inst.rows,
        "columns": inst.columns,
        "bits_allocated": inst.bits_allocated,
        "photometric_interpretation": inst.photometric_interpretation,
        "window_center": inst.window_center,
        "window_width": inst.window_width,
        "tooth_numbers": inst.tooth_numbers or [],
        "anatomic_codes": inst.anatomic_codes or [],
        "derivative_status": inst.derivative_status,
        "has_original_attributes": bool(inst.has_original_attributes),
        "assets": _build_assets(inst, tenant_id),
    }


def get_patient_imaging(
    db: Session,
    patient_id: int,
    tenant_id: int,
    *,
    modality: str | None = None,
    tooth: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Study→series→instance tree for a patient. 4 queries, tenant-scoped."""
    _verify_patient(db, patient_id, tenant_id)

    study_q = select(DicomStudy).where(
        DicomStudy.patient_id == patient_id,
        DicomStudy.tenant_id == tenant_id,
        DicomStudy.is_deleted.is_(False),
    )
    if date_from:
        study_q = study_q.where(DicomStudy.study_date >= date_from)
    if date_to:
        study_q = study_q.where(DicomStudy.study_date <= date_to)
    studies = db.execute(study_q.order_by(DicomStudy.study_date.desc().nullslast(),
                                          DicomStudy.id.desc())).scalars().all()
    if not studies:
        return {"patient_id": patient_id, "study_count": 0, "image_count": 0,
                "latest_study_date": None, "studies": []}

    study_ids = [s.id for s in studies]
    series_q = select(DicomSeries).where(
        DicomSeries.study_id.in_(study_ids), DicomSeries.is_deleted.is_(False)
    )
    if modality:
        series_q = series_q.where(DicomSeries.modality == modality)
    series_rows = db.execute(
        series_q.order_by(DicomSeries.series_number, DicomSeries.id)
    ).scalars().all()

    series_ids = [s.id for s in series_rows]
    instances: list[DicomInstance] = []
    if series_ids:
        inst_q = select(DicomInstance).where(
            DicomInstance.series_id.in_(series_ids),
            DicomInstance.is_deleted.is_(False),
            DicomInstance.superseded_by.is_(None),
        )
        instances = db.execute(
            inst_q.order_by(DicomInstance.instance_number, DicomInstance.id)
        ).scalars().all()
    if tooth is not None:
        instances = [i for i in instances if tooth in (i.tooth_numbers or [])]

    # group instances under series, series under studies
    inst_by_series: dict[int, list[DicomInstance]] = {}
    for i in instances:
        inst_by_series.setdefault(i.series_id, []).append(i)
    series_modality = {s.id: s.modality for s in series_rows}
    series_by_study: dict[int, list[DicomSeries]] = {}
    for s in series_rows:
        series_by_study.setdefault(s.study_id, []).append(s)

    total_images = 0
    out_studies = []
    for st in studies:
        st_series = []
        st_count = 0
        for se in series_by_study.get(st.id, []):
            inst_list = inst_by_series.get(se.id, [])
            if modality and not inst_list:
                # series kept by modality filter but tooth filter emptied it
                pass
            st_count += len(inst_list)
            st_series.append({
                "id": se.id,
                "series_instance_uid": se.series_instance_uid,
                "modality": se.modality,
                "series_number": se.series_number,
                "body_part": se.body_part,
                "description": se.description,
                "instances": [
                    _instance_out(i, series_modality.get(se.id), tenant_id) for i in inst_list
                ],
            })
        # drop empty series that a tooth/modality filter emptied
        filtering = tooth is not None or modality
        if filtering:
            st_series = [s for s in st_series if s["instances"]]
        if filtering and not st_series:
            continue
        total_images += st_count
        out_studies.append({
            "id": st.id,
            "study_instance_uid": st.study_instance_uid,
            "study_date": st.study_date.isoformat() if st.study_date else None,
            "study_time": st.study_time,
            "description": st.description,
            "accession_number": st.accession_number,
            "modalities": st.modalities or [],
            "identity_review_required": bool(st.identity_review_required),
            "image_count": st_count,
            "series": st_series,
        })

    latest = next((s["study_date"] for s in out_studies if s["study_date"]), None)
    return {
        "patient_id": patient_id,
        "study_count": len(out_studies),
        "image_count": total_images,
        "latest_study_date": latest,
        "studies": out_studies,
    }


def get_patient_imaging_summary(db: Session, patient_id: int, tenant_id: int) -> dict:
    """Cheap counts for the tab badge / patient overview integration."""
    _verify_patient(db, patient_id, tenant_id)
    studies = db.execute(
        select(DicomStudy).where(
            DicomStudy.patient_id == patient_id,
            DicomStudy.tenant_id == tenant_id,
            DicomStudy.is_deleted.is_(False),
        )
    ).scalars().all()
    if not studies:
        return {"patient_id": patient_id, "study_count": 0, "image_count": 0,
                "latest_study_date": None, "modalities": [], "pending_derivatives": 0}

    study_ids = [s.id for s in studies]
    series_rows = db.execute(
        select(DicomSeries.id).where(DicomSeries.study_id.in_(study_ids),
                                     DicomSeries.is_deleted.is_(False))
    ).scalars().all()
    image_count = pending = 0
    if series_rows:
        rows = db.execute(
            select(DicomInstance.derivative_status).where(
                DicomInstance.series_id.in_(series_rows),
                DicomInstance.is_deleted.is_(False),
                DicomInstance.superseded_by.is_(None),
            )
        ).scalars().all()
        image_count = len(rows)
        pending = sum(1 for s in rows if s != "ready")

    modalities = sorted({m for s in studies for m in (s.modalities or [])})
    dates = [s.study_date for s in studies if s.study_date]
    latest = max(dates).isoformat() if dates else None
    return {
        "patient_id": patient_id,
        "study_count": len(studies),
        "image_count": image_count,
        "latest_study_date": latest,
        "modalities": modalities,
        "pending_derivatives": pending,
    }


def get_instance_detail(db: Session, sop_instance_uid: str, tenant_id: int) -> dict:
    """Single-instance metadata + asset URLs (authed endpoint)."""
    inst = db.execute(
        select(DicomInstance).where(
            DicomInstance.sop_instance_uid == sop_instance_uid,
            DicomInstance.tenant_id == tenant_id,
            DicomInstance.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if inst is None:
        raise NotFoundError(f"Image '{sop_instance_uid}' was not found")
    modality = db.execute(
        select(DicomSeries.modality).where(DicomSeries.id == inst.series_id)
    ).scalar_one_or_none()
    return _instance_out(inst, modality, tenant_id)


def resolve_asset(
    db: Session, sop_instance_uid: str, kind: str, tenant_id: int
) -> tuple[StoredObject, DicomInstance] | None:
    """Return ``(StoredObject, DicomInstance)`` for a token-authorised asset, or
    ``None`` if not found / not ready. ``kind`` is thumb | web | original."""
    inst = db.execute(
        select(DicomInstance).where(
            DicomInstance.sop_instance_uid == sop_instance_uid,
            DicomInstance.tenant_id == tenant_id,
            DicomInstance.is_deleted.is_(False),
        )
    ).scalar_one_or_none()
    if inst is None:
        return None
    obj_id = {
        "thumb": inst.thumb_object_id,
        "web": inst.web_object_id,
        "original": inst.original_object_id,
    }.get(kind)
    if obj_id is None:
        return None
    stored = db.get(StoredObject, obj_id)
    if stored is None:
        return None
    return stored, inst
