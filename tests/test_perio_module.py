"""Periodontal-charting backend-gap tests (perio dev-report PERIO-BE-1..13)."""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Patient, PerioExam

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Pat", last_name="Perio",
                chart_no="PERIO-1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def exam(db_session, patient) -> PerioExam:
    e = PerioExam(patient_id=patient.id, exam_date=date(2026, 6, 1), created_by=db_session._admin.id)
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    return e


# ── PERIO-BE-1: unique (exam_id, tooth_no) ───────────────────────────────────
def test_duplicate_tooth_rejected(client, exam):
    base = f"{PREFIX}/perio-exam-details"
    first = client.post(base, json={"exam_id": exam.id, "tooth_no": "4", "pd1": 3})
    assert first.status_code == 201, first.text
    dup = client.post(base, json={"exam_id": exam.id, "tooth_no": "4", "pd1": 5})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "conflict"


# ── PERIO-BE-2: mobility decimals ────────────────────────────────────────────
def test_mobility_half_grade_persists(client, exam):
    base = f"{PREFIX}/perio-exam-details"
    r = client.post(base, json={"exam_id": exam.id, "tooth_no": "5", "mobility_buccal": 0.5})
    assert r.status_code == 201, r.text
    assert float(r.json()["mobility_buccal"]) == 0.5


def test_mobility_out_of_range_rejected(client, exam):
    r = client.post(f"{PREFIX}/perio-exam-details",
                    json={"exam_id": exam.id, "tooth_no": "6", "mobility_buccal": 3.5})
    assert r.status_code == 422


# ── PERIO-BE-3: is_voided filter on exam list ────────────────────────────────
def test_exam_list_excludes_voided_via_filter(client, patient):
    base = f"{PREFIX}/perio-exams"
    a = client.post(base, json={"patient_id": patient.id, "exam_date": "2026-06-01"})
    b = client.post(base, json={"patient_id": patient.id, "exam_date": "2026-06-02"})
    assert a.status_code == 201 and b.status_code == 201
    # void one
    client.delete(f"{base}/{b.json()['id']}")
    all_ = client.get(f"{base}?patient_id={patient.id}").json()
    assert all_["meta"]["total"] == 2  # soft-deleted row retained
    active = client.get(f"{base}?patient_id={patient.id}&is_voided=false").json()
    assert active["meta"]["total"] == 1
    assert active["items"][0]["exam_date"] == "2026-06-01"


# ── PERIO-BE-4: CAL stored ───────────────────────────────────────────────────
def test_cal_persists(client, exam):
    r = client.post(f"{PREFIX}/perio-exam-details",
                    json={"exam_id": exam.id, "tooth_no": "7", "cal1": 5, "cal6": 4})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["cal1"] == 5 and body["cal6"] == 4


# ── PERIO-BE-6: exam attribution names ───────────────────────────────────────
def test_exam_read_exposes_actor_name(client, patient, db_session):
    r = client.post(f"{PREFIX}/perio-exams", json={"patient_id": patient.id, "exam_date": "2026-06-03"})
    assert r.status_code == 201
    body = r.json()
    assert body["created_by"] == db_session._admin.id
    assert body["created_by_name"] == db_session._admin.username  # no first/last -> username


# ── PERIO-BE-7: value-range validation ───────────────────────────────────────
def test_pd_out_of_range_rejected(client, exam):
    r = client.post(f"{PREFIX}/perio-exam-details",
                    json={"exam_id": exam.id, "tooth_no": "8", "pd1": 999})
    assert r.status_code == 422


def test_furcation_out_of_range_rejected(client, exam):
    r = client.post(f"{PREFIX}/perio-exam-details",
                    json={"exam_id": exam.id, "tooth_no": "9", "furc1": 9})
    assert r.status_code == 422


def test_fgm_negative_allowed(client, exam):
    r = client.post(f"{PREFIX}/perio-exam-details",
                    json={"exam_id": exam.id, "tooth_no": "10", "fgm1": -3})
    assert r.status_code == 201, r.text
    assert r.json()["fgm1"] == -3


# ── PERIO-BE-8: bulk upsert ──────────────────────────────────────────────────
def test_bulk_upsert_inserts_then_updates(client, exam, db_session):
    url = f"{PREFIX}/perio-exams/{exam.id}/details"
    created = client.put(url, json={"items": [
        {"tooth_no": "1", "pd1": 3},
        {"tooth_no": "2", "pd1": 4},
    ]})
    assert created.status_code == 200, created.text
    assert len(created.json()) == 2

    # Re-upsert tooth 1 (update) + add tooth 3 (insert) -> still one row per tooth.
    again = client.put(url, json={"items": [
        {"tooth_no": "1", "pd1": 6},
        {"tooth_no": "3", "pd1": 2},
    ]})
    assert again.status_code == 200, again.text

    listed = client.get(f"{PREFIX}/perio-exam-details?exam_id={exam.id}&size=50").json()
    by_tooth = {it["tooth_no"]: it for it in listed["items"]}
    assert set(by_tooth) == {"1", "2", "3"}
    assert by_tooth["1"]["pd1"] == 6  # updated, not duplicated
    assert by_tooth["1"]["updated_by"] == db_session._admin.id


def test_bulk_upsert_unknown_exam_404(client):
    r = client.put(f"{PREFIX}/perio-exams/999999/details",
                   json={"items": [{"tooth_no": "1", "pd1": 3}]})
    assert r.status_code == 404


# ── PERIO-BE-9: exam_date range filter ───────────────────────────────────────
def test_exam_date_range_filter(client, patient):
    base = f"{PREFIX}/perio-exams"
    for d in ("2026-01-01", "2026-03-01", "2026-06-01"):
        client.post(base, json={"patient_id": patient.id, "exam_date": d})
    r = client.get(f"{base}?patient_id={patient.id}&exam_date_from=2026-02-01&exam_date_to=2026-05-01")
    assert r.json()["meta"]["total"] == 1
    assert r.json()["items"][0]["exam_date"] == "2026-03-01"


# ── PERIO-BE-10: compare ─────────────────────────────────────────────────────
def test_compare_exams(client, patient):
    base = f"{PREFIX}/perio-exams"
    e1 = client.post(base, json={"patient_id": patient.id, "exam_date": "2026-01-01"}).json()
    e2 = client.post(base, json={"patient_id": patient.id, "exam_date": "2026-06-01"}).json()
    client.put(f"{base}/{e1['id']}/details", json={"items": [
        {"tooth_no": "1", "pd1": 3, "pd2": 4, "bleed1": True},
    ]})
    client.put(f"{base}/{e2['id']}/details", json={"items": [
        {"tooth_no": "1", "pd1": 6, "pd2": 7, "bleed1": True, "bleed2": True},
    ]})
    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}"
                   f"&exam_ids={e1['id']}&exam_ids={e2['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["exam_id"] for e in body["exams"]] == [e1["id"], e2["id"]]  # oldest first
    assert body["exams"][0]["delta"] is None
    assert body["exams"][1]["summary"]["max_pd"] == 7
    assert body["exams"][1]["delta"]["mean_pd"] > 0  # got worse


# ── PERIO-BE-11: settings/me ─────────────────────────────────────────────────
def test_settings_me_seeds_and_updates(client, db_session):
    got = client.get(f"{PREFIX}/perio-chart-settings/me")
    assert got.status_code == 200, got.text
    assert got.json()["user_id"] == db_session._admin.id
    assert got.json()["pd_level"] == 4  # seeded default

    upd = client.put(f"{PREFIX}/perio-chart-settings/me", json={"pd_level": 5, "is_mgj": False})
    assert upd.status_code == 200
    assert upd.json()["pd_level"] == 5 and upd.json()["is_mgj"] is False

    # idempotent: a second GET returns the same single row, now updated
    again = client.get(f"{PREFIX}/perio-chart-settings/me").json()
    assert again["pd_level"] == 5


# ── PERIO-BE-12: typed auto_advance on templates ─────────────────────────────
def test_template_auto_advance_typed(client):
    r = client.post(f"{PREFIX}/perio-chart-templates", json={
        "name": "Default order",
        "auto_advance": {"ur_facial": "01-08", "ul_facial": "08-01"},
    })
    assert r.status_code == 201, r.text
    aa = r.json()["auto_advance"]
    assert aa["ur_facial"] == "01-08"
    assert aa["ul_facial"] == "08-01"
    assert aa["ll_lingual"] is None  # unset region defaults to null
