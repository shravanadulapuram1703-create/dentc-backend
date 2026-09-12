"""Procedure Codes — supporting-records requirements (PROC-7a..7d).

Backs ``docs/procedure_code/procedure_code_supporting_records_backend_devreport.md``.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.config import settings
from app.db.models import (
    ChartCondition,
    DicomInstance,
    DicomSeries,
    DicomStudy,
    Office,
    Patient,
    PerioExam,
    Provider,
)
from app.services.supporting_records_service import _months_before

PREFIX = "/api/v1"
FLAGS = ("requires_attachment", "requires_perio_chart", "requires_photo",
         "requires_xray", "requires_missing_tooth_info")
DOS = "2026-09-10"


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, name="Main", office_code="MAIN", is_active=True)
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(id="DR-SR", tenant_id=db_session._tenant_id, office_id=office.id,
                 name="Ann Drill", first_name="Ann", last_name="Drill", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Sup", last_name="Records",
                chart_no="SR-1", home_office_id=office.id, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Other", last_name="Person",
                chart_no="SR-2", home_office_id=office.id, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def codes(client):
    rows = [
        {"code": "D2740", "description": "Crown", "category": "Restorative",
         "requires_xray": True, "requires_attachment": True},
        {"code": "D4341", "description": "SRP", "category": "Perio", "requires_perio_chart": True},
        {"code": "D6010", "description": "Implant", "category": "Implant",
         "requires_xray": True, "requires_missing_tooth_info": True, "requires_photo": True},
        {"code": "D0120", "description": "Exam", "category": "Diagnostic"},
        {"code": "D7140", "description": "Extraction", "category": "Oral Surgery"},
    ]
    for row in rows:
        r = client.post(f"{PREFIX}/procedure-codes", json={"default_fee": 100, **row})
        assert r.status_code == 201, r.text
    return rows


def _proc(client, patient, office, provider, code, item_id, **extra):
    body = {"id": item_id, "patient_id": patient.id, "office_id": office.id,
            "provider_id": provider.id, "procedure_code": code, "fee": 100,
            "date_of_service": DOS, **extra}
    r = client.post(f"{PREFIX}/patient-procedures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _claim(client, patient, office, claim_id="CLM-SR"):
    r = client.post(f"{PREFIX}/insurance-claims", json={
        "id": claim_id, "patient_id": patient.id, "office_id": office.id,
        "claim_number": claim_id, "status": "draft"})
    assert r.status_code == 201, r.text
    return r.json()


def _upload(client, patient, document_type=None, **form):
    data = {"patient_id": str(patient.id), **{k: str(v) for k, v in form.items()}}
    if document_type:
        data["document_type"] = document_type
    r = client.post(f"{PREFIX}/patient-documents", data=data,
                    files={"file": ("f.pdf", b"%PDF-1.4 x", "application/pdf")})
    return r


def _dicom_study(db_session, patient, *, modalities, study_date=None, teeth=None, deleted=False):
    n = db_session.query(DicomStudy).count() + 1
    study = DicomStudy(tenant_id=db_session._tenant_id, patient_id=patient.id,
                       study_instance_uid=f"1.2.3.{n}", study_date=study_date,
                       modalities=list(modalities), is_deleted=deleted)
    db_session.add(study)
    db_session.flush()
    series = DicomSeries(tenant_id=db_session._tenant_id, study_id=study.id,
                         series_instance_uid=f"1.2.3.{n}.1", modality=modalities[0])
    db_session.add(series)
    db_session.flush()
    inst = DicomInstance(tenant_id=db_session._tenant_id, series_id=series.id,
                         sop_instance_uid=f"1.2.3.{n}.1.1", tooth_numbers=teeth)
    db_session.add(inst)
    db_session.commit()
    return study


# ── PROC-7a: the five flags round-trip on all three schemas ──────────────────
def test_flags_round_trip_on_patch_get_list_and_post(client, codes):
    # Acceptance check 1 — PATCH round-trip; every key present, three flipped.
    r = client.patch(f"{PREFIX}/procedure-codes/D0120", json={
        "requires_xray": True, "requires_perio_chart": True, "requires_missing_tooth_info": True})
    assert r.status_code == 200, r.text
    g = client.get(f"{PREFIX}/procedure-codes/D0120").json()
    assert {k: g[k] for k in FLAGS} == {
        "requires_attachment": False, "requires_perio_chart": True, "requires_photo": False,
        "requires_xray": True, "requires_missing_tooth_info": True,
    }
    # Acceptance check 2 — the list carries them (Setup + pickers read the list).
    items = client.get(f"{PREFIX}/procedure-codes?size=50").json()["items"]
    assert all(all(k in it and isinstance(it[k], bool) for k in FLAGS) for it in items)
    # Acceptance check 3 — POST accepts them; an omitted flag defaults false.
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D9QA7", "description": "QA supporting records", "category": "DIAGNOSTIC",
        "default_fee": "0", "requires_attachment": True})
    assert r.status_code == 201, r.text
    assert r.json()["requires_attachment"] is True
    assert r.json()["requires_photo"] is False


def test_openapi_exposes_the_flags_on_all_three_components(client):
    spec = client.get(f"{PREFIX}/openapi.json").json()["components"]["schemas"]
    for comp in ("ProcedureCodeRead", "ProcedureCodeCreate", "ProcedureCodeUpdate"):
        assert set(FLAGS) <= set(spec[comp]["properties"]), comp
    assert set(FLAGS) <= set(spec["ProcedureCodeRead"]["required"])


# ── PROC-7b: metadata advertises them ────────────────────────────────────────
def test_metadata_advertises_flags_as_advisory_with_error_codes(client):
    d = client.get(f"{PREFIX}/metadata/procedure-entry-rules").json()
    assert not any(f in d["enforced"] for f in FLAGS)
    assert set(FLAGS) <= set(d["advisory"])
    for code in ("supporting_records_missing", "attachment_required", "perio_chart_required",
                 "photo_required", "xray_required", "missing_tooth_info_required"):
        assert code in d["error_codes"]
    sr = d["supporting_records"]
    assert sr["flags"] == list(FLAGS)
    assert sr["enforced_at"] == "claim_submit"
    assert {r["flag"] for r in sr["rules"]} == set(FLAGS)
    assert all(r["satisfied_when"] for r in sr["rules"])


# ── PROC-7c: readiness — pre-post ────────────────────────────────────────────
def test_pre_post_readiness_reports_missing_and_defers_attachment(client, codes, patient):
    r = client.get(f"{PREFIX}/patients/{patient.id}/procedure-readiness",
                   params={"procedure_code": "D2740", "tooth": "30", "date_of_service": DOS})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["requires"] == ["attachment", "xray"]
    assert d["missing"] == ["xray"]
    assert d["deferred"] == ["attachment"]  # nothing to attach to before the charge exists
    assert d["ready"] is False
    assert d["evidence"]["xray"]["documents"] == 0
    assert d["rules"]["attachment"]["stage"] == "claim"
    # A code with no flags is trivially ready.
    d = client.get(f"{PREFIX}/patients/{patient.id}/procedure-readiness",
                   params={"procedure_code": "D0120"}).json()
    assert d["requires"] == [] and d["ready"] is True


def test_readiness_404s_on_unknown_code_and_foreign_patient(client, codes, patient, db_session):
    r = client.get(f"{PREFIX}/patients/{patient.id}/procedure-readiness",
                   params={"procedure_code": "D9999"})
    assert r.status_code == 404
    r = client.get(f"{PREFIX}/patients/999999/procedure-readiness",
                   params={"procedure_code": "D2740"})
    assert r.status_code == 404


def test_xray_satisfied_by_typed_document_or_dated_dicom_study(client, codes, patient, db_session):
    url = f"{PREFIX}/patients/{patient.id}/procedure-readiness"
    params = {"procedure_code": "D2740", "tooth": "30", "date_of_service": DOS}
    # An untyped document is not a radiograph.
    assert _upload(client, patient).status_code == 201
    assert "xray" in client.get(url, params=params).json()["missing"]
    # A study dated AFTER the DOS does not count; one on/before does.
    _dicom_study(db_session, patient, modalities=["IO"], study_date=date(2026, 9, 11))
    assert "xray" in client.get(url, params=params).json()["missing"]
    _dicom_study(db_session, patient, modalities=["IO"], study_date=date(2026, 9, 1), teeth=["31"])
    d = client.get(url, params=params).json()
    assert "xray" in d["satisfied"]
    assert d["evidence"]["xray"]["dicom_studies"] == 1
    # strict_tooth: the study is tagged #31, not #30 -> missing again.
    assert "xray" in client.get(url, params={**params, "strict_tooth": "true"}).json()["missing"]
    _dicom_study(db_session, patient, modalities=["IO"], study_date=date(2026, 9, 2), teeth=["30"])
    d = client.get(url, params={**params, "strict_tooth": "true"}).json()
    assert "xray" in d["satisfied"] and d["evidence"]["xray"]["tooth_tagged_instances"] == 1
    # A deleted study never counts; a typed XR document does on its own.
    _dicom_study(db_session, patient, modalities=["PX"], deleted=True)
    assert _upload(client, patient, document_type="XR").status_code == 201
    assert client.get(url, params=params).json()["evidence"]["xray"]["documents"] == 1


def test_photo_satisfied_by_ph_document_or_photographic_modality(
    client, codes, patient, db_session,
):
    url = f"{PREFIX}/patients/{patient.id}/procedure-readiness"
    params = {"procedure_code": "D6010"}
    # An IO radiograph is not a photo.
    _dicom_study(db_session, patient, modalities=["IO"])
    assert "photo" in client.get(url, params=params).json()["missing"]
    _dicom_study(db_session, patient, modalities=["XC"])
    assert "photo" in client.get(url, params=params).json()["satisfied"]


def test_perio_chart_respects_dos_voided_and_max_age(client, codes, patient, db_session):
    url = f"{PREFIX}/patients/{patient.id}/procedure-readiness"
    params = {"procedure_code": "D4341", "date_of_service": DOS}
    # A voided exam and one dated after the DOS do not count.
    db_session.add(PerioExam(patient_id=patient.id, exam_date=date(2026, 9, 1), is_voided=True))
    db_session.add(PerioExam(patient_id=patient.id, exam_date=date(2026, 9, 12)))
    db_session.commit()
    d = client.get(url, params=params).json()
    assert d["missing"] == ["perio_chart"] and d["evidence"]["perio_chart"]["exams_on_file"] == 1
    # An exam 8 months before the DOS satisfies by default …
    db_session.add(PerioExam(patient_id=patient.id, exam_date=date(2026, 1, 10)))
    db_session.commit()
    d = client.get(url, params=params).json()
    assert d["satisfied"] == ["perio_chart"]
    assert d["evidence"]["perio_chart"]["latest_exam_date"] == "2026-01-10"
    # … but not inside a 6-month window (per call), and the setting is the default.
    d = client.get(url, params={**params, "perio_max_age_months": 6}).json()
    assert d["missing"] == ["perio_chart"]
    assert d["evidence"]["perio_chart"]["not_before"] == "2026-03-10"
    old = settings.SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS
    settings.SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS = 6
    try:
        assert client.get(url, params=params).json()["missing"] == ["perio_chart"]
    finally:
        settings.SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS = old


def test_months_before_handles_year_wrap_and_short_months():
    assert _months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert _months_before(date(2026, 1, 15), 13) == date(2024, 12, 15)
    assert _months_before(date(2024, 3, 31), 1) == date(2024, 2, 29)


def test_missing_tooth_info_from_dated_condition_or_posted_extraction(
    client, codes, patient, office, provider, db_session,
):
    url = f"{PREFIX}/patients/{patient.id}/procedure-readiness"
    params = {"procedure_code": "D6010", "tooth": "19"}
    # An undated MISSING condition is reported but does not satisfy.
    db_session.add(ChartCondition(patient_id=patient.id, tooth="19", condition_code="missing"))
    db_session.commit()
    d = client.get(url, params=params).json()
    assert "missing_tooth_info" in d["missing"]
    assert d["evidence"]["missing_tooth_info"]["undated_missing"] == 1
    # A posted extraction (its DOS is the extraction date) satisfies.
    _proc(client, patient, office, provider, "D7140", "PP-EXT", tooth="19")
    d = client.get(url, params=params).json()
    assert "missing_tooth_info" in d["satisfied"]
    assert d["evidence"]["missing_tooth_info"]["extractions"][0]["tooth"] == "19"


# ── PROC-7c: readiness — posted charge + attachment link ─────────────────────
def test_posted_charge_readiness_and_document_link(client, codes, patient, office, provider):
    proc = _proc(client, patient, office, provider, "D2740", "PP-CRN", tooth="30")
    url = f"{PREFIX}/patient-procedures/{proc['id']}/readiness"
    d = client.get(url).json()
    assert d["procedure_id"] == proc["id"] and d["tooth"] == "30"
    assert d["missing"] == ["attachment", "xray"] and d["deferred"] == []
    # Linking a document to the charge satisfies requires_attachment.
    r = _upload(client, patient, procedure_id=proc["id"])
    assert r.status_code == 201, r.text
    assert r.json()["procedure_id"] == proc["id"]
    d = client.get(url).json()
    assert "attachment" in d["satisfied"] and d["evidence"]["attachment"]["documents"] == 1
    # The link is a list filter.
    listed = client.get(f"{PREFIX}/patient-documents", params={"procedure_id": proc["id"]}).json()
    assert listed["meta"]["total"] == 1
    none = client.get(f"{PREFIX}/patient-documents", params={"procedure_id": "nope"}).json()
    assert none["meta"]["total"] == 0


def test_document_link_must_belong_to_the_same_patient(
    client, codes, patient, other_patient, office, provider,
):
    proc = _proc(client, patient, office, provider, "D2740", "PP-X", tooth="30")
    r = _upload(client, other_patient, procedure_id=proc["id"])
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "document_procedure_mismatch"
    claim = _claim(client, patient, office)
    r = _upload(client, other_patient, claim_id=claim["id"])
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "document_claim_mismatch"
    # Blank form values mean "no link", not a mismatch.
    assert _upload(client, patient, procedure_id="", claim_id="").status_code == 201


def test_document_on_a_claimed_charge_inherits_the_claim(client, codes, patient, office, provider):
    claim = _claim(client, patient, office)
    proc = _proc(client, patient, office, provider, "D2740", "PP-C", tooth="30",
                 claim_id=claim["id"])
    doc = _upload(client, patient, procedure_id=proc["id"]).json()
    assert doc["claim_id"] == claim["id"]
    listed = client.get(f"{PREFIX}/patient-documents", params={"claim_id": claim["id"]}).json()
    assert listed["meta"]["total"] == 1


# ── PROC-7c: claim readiness + submit gate ───────────────────────────────────
def test_claim_readiness_and_submit_gate(client, codes, patient, office, provider, db_session):
    claim = _claim(client, patient, office)
    _proc(client, patient, office, provider, "D2740", "PP-1", tooth="30", claim_id=claim["id"])
    _proc(client, patient, office, provider, "D0120", "PP-2", claim_id=claim["id"])
    # A voided line is ignored.
    _proc(client, patient, office, provider, "D6010", "PP-3", tooth="19", claim_id=claim["id"])
    client.delete(f"{PREFIX}/patient-procedures/PP-3")

    d = client.get(f"{PREFIX}/insurance-claims/{claim['id']}/readiness").json()
    assert d["ready"] is False and d["enforced_on_submit"] is True
    assert [p["procedure_id"] for p in d["procedures"]] == ["PP-1", "PP-2"]
    assert {(m["procedure_id"], m["record"], m["code"]) for m in d["missing"]} == {
        ("PP-1", "attachment", "attachment_required"), ("PP-1", "xray", "xray_required"),
    }
    # Submit refuses with the same list …
    r = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/submit", json={})
    assert r.status_code == 422, r.text
    err = r.json()["error"]["details"]
    assert err["code"] == "supporting_records_missing"
    assert {m["record"] for m in err["missing"]} == {"attachment", "xray"}
    assert client.get(f"{PREFIX}/insurance-claims/{claim['id']}").json()["status"] == "draft"

    # … satisfy both and it goes through cleanly.
    _dicom_study(db_session, patient, modalities=["IO"], study_date=date(2026, 9, 1))
    r = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/attachments",
                    data={"attachment_type": "narrative"},
                    files={"file": ("n.pdf", b"%PDF-1.4 n", "application/pdf")})
    assert r.status_code == 201, r.text
    d = client.get(f"{PREFIX}/insurance-claims/{claim['id']}/readiness").json()
    assert d["ready"] is True and d["missing"] == []
    assert d["enclosures"]["narratives"] == 1 and d["enclosures"]["attachments_enclosed"] is True
    r = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/submit", json={})
    assert r.status_code == 200, r.text
    assert r.json()["missing_records_overridden"] is False


def test_submit_override_and_enforcement_switch(client, codes, patient, office, provider):
    claim = _claim(client, patient, office, claim_id="CLM-OV")
    _proc(client, patient, office, provider, "D2740", "PP-OV", tooth="30", claim_id=claim["id"])
    r = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/submit",
                    json={"allow_missing_records": True})
    assert r.status_code == 200, r.text
    assert r.json()["missing_records_overridden"] is True
    assert r.json()["status"] == "sent"

    claim2 = _claim(client, patient, office, claim_id="CLM-OFF")
    _proc(client, patient, office, provider, "D2740", "PP-OFF", tooth="31", claim_id=claim2["id"])
    old = settings.SUPPORTING_RECORDS_ENFORCE_ON_SUBMIT
    settings.SUPPORTING_RECORDS_ENFORCE_ON_SUBMIT = False
    try:
        d = client.get(f"{PREFIX}/insurance-claims/{claim2['id']}/readiness").json()
        assert d["ready"] is False and d["enforced_on_submit"] is False  # still reported
        r = client.post(f"{PREFIX}/insurance-claims/{claim2['id']}/submit", json={})
        assert r.status_code == 200, r.text
        assert r.json()["missing_records_overridden"] is False
    finally:
        settings.SUPPORTING_RECORDS_ENFORCE_ON_SUBMIT = old


# ── PROC-7d: enclosures ───────────────────────────────────────────────────────
def test_enclosures_derived_from_attachments_and_required_types(
    client, codes, patient, office, provider,
):
    claim = _claim(client, patient, office, claim_id="CLM-ENC")
    _proc(client, patient, office, provider, "D6010", "PP-ENC", tooth="19", claim_id=claim["id"])
    d = client.get(f"{PREFIX}/insurance-claims/{claim['id']}/readiness").json()["enclosures"]
    assert d["required_attachment_types"] == ["PHOTO", "XRAY"]
    assert d["missing_attachment_types"] == ["PHOTO", "XRAY"]
    assert d["attachments_enclosed"] is False
    for kind, name in (("x-ray", "x.jpg"), ("x-ray", "y.jpg"), ("photo", "p.jpg")):
        r = client.post(f"{PREFIX}/insurance-claims/{claim['id']}/attachments",
                        data={"attachment_type": kind},
                        files={"file": (name, b"\xff\xd8\xff jpeg", "image/jpeg")})
        assert r.status_code == 201, r.text
    _upload(client, patient, document_type="XR", claim_id=claim["id"])
    d = client.get(f"{PREFIX}/insurance-claims/{claim['id']}/readiness").json()["enclosures"]
    assert d["radiographs"] == 3 and d["oral_images"] == 1 and d["models"] == 0
    assert d["missing_attachment_types"] == [] and d["attachments_enclosed"] is True


def test_claim_readiness_is_tenant_scoped(client, codes, patient, office, db_session):
    _claim(client, patient, office, claim_id="CLM-T")
    other = Patient(tenant_id=db_session._tenant_id + 1, first_name="X", last_name="Y",
                    chart_no="T2")
    db_session.add(other)
    db_session.commit()
    from app.db.models import InsuranceClaim
    db_session.add(InsuranceClaim(id="CLM-FOREIGN", patient_id=other.id,
                                  claim_number="CLM-FOREIGN"))
    db_session.commit()
    assert client.get(f"{PREFIX}/insurance-claims/CLM-FOREIGN/readiness").status_code == 404
    assert client.get(f"{PREFIX}/insurance-claims/CLM-T/readiness").status_code == 200
