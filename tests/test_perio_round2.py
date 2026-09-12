"""Periodontal-charting round 2 (perio dev-report PERIO-BE-9/14/15/16/17/18 +
the tenant-scoping ride-along)."""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Office, Patient, PerioExam, PerioExamDetail, Provider, Tenant

PREFIX = "/api/v1"


@pytest.fixture
def patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Pat", last_name="Perio",
                chart_no="PERIO-2", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def other_patient(db_session) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Other", last_name="Perio",
                chart_no="PERIO-3", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="PERIO", name="Perio Office")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(id="DRP", tenant_id=db_session._tenant_id, office_id=office.id,
                 name="Dr. Perio", role="dentist", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def foreign(db_session):
    """A second tenant with its own office, provider, patient and exam."""
    t = Tenant(name="Other Practice", code="other", is_active=True)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    o = Office(tenant_id=t.id, office_code="OTHR", name="Other Office")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    prov = Provider(id="DRX", tenant_id=t.id, office_id=o.id, name="Dr. Foreign", role="dentist")
    pat = Patient(tenant_id=t.id, first_name="For", last_name="Eign", chart_no="X-1", is_active=True)
    db_session.add_all([prov, pat])
    db_session.commit()
    db_session.refresh(pat)
    exam = PerioExam(patient_id=pat.id, exam_date=date(2026, 1, 1))
    db_session.add(exam)
    db_session.commit()
    db_session.refresh(exam)
    detail = PerioExamDetail(exam_id=exam.id, tooth_no="1", pd1=9)
    db_session.add(detail)
    db_session.commit()
    db_session.refresh(detail)
    return {"tenant": t, "provider": prov, "patient": pat, "exam": exam, "detail": detail}


def _exam(client, patient_id: int, exam_date: str, **extra) -> dict:
    r = client.post(f"{PREFIX}/perio-exams", json={"patient_id": patient_id, "exam_date": exam_date, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _chart(client, exam_id: int, items: list[dict]) -> None:
    r = client.put(f"{PREFIX}/perio-exams/{exam_id}/details", json={"items": items})
    assert r.status_code == 200, r.text


# ── PERIO-BE-9: date_from / date_to aliases ─────────────────────────────────
def test_date_from_to_aliases_filter_exams(client, patient):
    for d in ("2026-01-01", "2026-03-01", "2026-06-01"):
        _exam(client, patient.id, d)
    r = client.get(f"{PREFIX}/perio-exams?patient_id={patient.id}&date_from=2026-02-01&date_to=2026-05-01")
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["total"] == 1
    assert r.json()["items"][0]["exam_date"] == "2026-03-01"
    # the engine's long names still work and compose with the alias
    r = client.get(f"{PREFIX}/perio-exams?patient_id={patient.id}&exam_date_from=2026-02-01&date_to=2026-12-31")
    assert r.json()["meta"]["total"] == 2


# ── PERIO-BE-14: provider on the exam ───────────────────────────────────────
def test_exam_provider_persists_with_name(client, patient, provider):
    body = _exam(client, patient.id, "2026-06-01", provider_id=provider.id)
    assert body["provider_id"] == provider.id
    assert body["provider_name"] == "Dr. Perio"
    got = client.get(f"{PREFIX}/perio-exams/{body['id']}").json()
    assert got["provider_name"] == "Dr. Perio"
    listed = client.get(f"{PREFIX}/perio-exams?patient_id={patient.id}&provider_id={provider.id}").json()
    assert listed["meta"]["total"] == 1
    assert listed["items"][0]["provider_name"] == "Dr. Perio"


def test_exam_provider_unknown_or_foreign_422(client, patient, foreign):
    r = client.post(f"{PREFIX}/perio-exams",
                    json={"patient_id": patient.id, "exam_date": "2026-06-01", "provider_id": "NOPE"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "provider_not_found"
    # another tenant's provider reads as not found (no existence leak)
    r = client.post(f"{PREFIX}/perio-exams",
                    json={"patient_id": patient.id, "exam_date": "2026-06-01",
                          "provider_id": foreign["provider"].id})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "provider_not_found"


def test_exam_provider_inactive_blocks_move_only(client, patient, provider, db_session):
    body = _exam(client, patient.id, "2026-06-01", provider_id=provider.id)
    provider.is_active = False
    db_session.commit()
    # editing the exam while keeping the (now retired) provider is fine
    r = client.patch(f"{PREFIX}/perio-exams/{body['id']}", json={"notes": "x", "provider_id": provider.id})
    assert r.status_code == 200, r.text
    # crediting a *new* exam to the retired provider is not
    r = client.post(f"{PREFIX}/perio-exams",
                    json={"patient_id": patient.id, "exam_date": "2026-06-02", "provider_id": provider.id})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "provider_inactive"


def test_exam_provider_can_be_cleared(client, patient, provider):
    body = _exam(client, patient.id, "2026-06-01", provider_id=provider.id)
    r = client.patch(f"{PREFIX}/perio-exams/{body['id']}", json={"provider_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["provider_id"] is None and r.json()["provider_name"] is None


# ── PERIO-BE-15: multi-exam details filter + details on compare ─────────────
def test_details_exam_ids_filter(client, patient):
    e1 = _exam(client, patient.id, "2026-01-01")
    e2 = _exam(client, patient.id, "2026-02-01")
    e3 = _exam(client, patient.id, "2026-03-01")
    _chart(client, e1["id"], [{"tooth_no": "1", "pd1": 3}])
    _chart(client, e2["id"], [{"tooth_no": "2", "pd1": 4}])
    _chart(client, e3["id"], [{"tooth_no": "3", "pd1": 5}])
    r = client.get(f"{PREFIX}/perio-exam-details?exam_ids={e1['id']},{e3['id']}&size=50")
    assert r.status_code == 200, r.text
    assert {it["exam_id"] for it in r.json()["items"]} == {e1["id"], e3["id"]}
    # an empty / garbage list matches nothing rather than un-filtering
    assert client.get(f"{PREFIX}/perio-exam-details?exam_ids=abc").json()["meta"]["total"] == 0


def test_compare_include_details_embeds_sorted_rows(client, patient):
    e1 = _exam(client, patient.id, "2026-01-01")
    e2 = _exam(client, patient.id, "2026-06-01")
    _chart(client, e1["id"], [{"tooth_no": "10", "pd1": 3}, {"tooth_no": "9", "pd1": 4}, {"tooth_no": "A", "pd1": 2}])
    _chart(client, e2["id"], [{"tooth_no": "9", "pd1": 5}])
    url = f"{PREFIX}/perio-exams/compare?patient_id={patient.id}&exam_ids={e1['id']}&exam_ids={e2['id']}"
    plain = client.get(url).json()
    assert plain["include_details"] is False
    assert all(e["details"] is None for e in plain["exams"])

    r = client.get(url + "&include_details=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["include_details"] is True
    first, second = body["exams"]
    assert [d["tooth_no"] for d in first["details"]] == ["9", "10", "A"]  # numeric, then letters
    assert first["details"][0]["pd1"] == 4
    assert first["details"][0]["created_by_name"]  # enriched like the list route
    assert [d["tooth_no"] for d in second["details"]] == ["9"]


# ── PERIO-BE-16: percentages over probeable sites ───────────────────────────
def test_bleeding_pct_uses_probeable_sites_and_clamps(client, patient):
    e1 = _exam(client, patient.id, "2026-01-01")
    # one tooth: 6 bleeding sites, 3 pocket depths -> was 200 %
    _chart(client, e1["id"], [{
        "tooth_no": "1", "pd1": 3, "pd2": 3, "pd3": 3,
        "bleed1": True, "bleed2": True, "bleed3": True, "bleed4": True, "bleed5": True, "bleed6": True,
        "supp1": True, "supp2": False,
    }])
    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}&exam_ids={e1['id']}")
    s = r.json()["exams"][0]["summary"]
    assert s["teeth_charted"] == 1
    assert s["probeable_sites"] == 6
    assert s["sites_measured"] == 3            # still "sites with a PD"
    assert s["sites_with_findings"] == 6       # every site has *something*
    assert s["bleeding_sites"] == 6 and s["bleeding_pct"] == 100.0
    assert s["suppuration_sites"] == 1 and s["suppuration_pct"] == pytest.approx(16.7)


def test_bleeding_pct_reported_without_pocket_depths(client, patient):
    e1 = _exam(client, patient.id, "2026-01-01")
    _chart(client, e1["id"], [
        {"tooth_no": "1", "bleed1": True, "bleed2": True},
        {"tooth_no": "2", "bleed1": True},
    ])
    s = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}&exam_ids={e1['id']}").json()["exams"][0]["summary"]
    assert s["sites_measured"] == 0 and s["mean_pd"] is None
    assert s["probeable_sites"] == 12
    assert s["bleeding_pct"] == 25.0            # was null
    assert s["suppuration_pct"] == 0.0


# ── PERIO-BE-17: unknown / foreign ids are errors ───────────────────────────
def test_compare_unknown_exam_404_names_the_id(client, patient):
    e1 = _exam(client, patient.id, "2026-01-01")
    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}&exam_ids={e1['id']}&exam_ids=99999999")
    assert r.status_code == 404, r.text
    err = r.json()["error"]
    assert err["details"]["code"] == "perio_exam_not_found"
    assert err["details"]["exam_id"] == 99999999


def test_compare_other_patients_exam_422(client, patient, other_patient):
    mine = _exam(client, patient.id, "2026-01-01")
    theirs = _exam(client, other_patient.id, "2026-01-01")
    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}&exam_ids={mine['id']}&exam_ids={theirs['id']}")
    assert r.status_code == 422, r.text
    err = r.json()["error"]["details"]
    assert err["code"] == "exam_not_owned_by_patient"
    assert err["exam_id"] == theirs["id"] and err["patient_id"] == patient.id


def test_compare_foreign_tenant_exam_is_404_not_422(client, patient, foreign):
    mine = _exam(client, patient.id, "2026-01-01")
    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}&exam_ids={mine['id']}&exam_ids={foreign['exam'].id}")
    assert r.status_code == 404  # existence of another tenant's exam is not revealed
    assert r.json()["error"]["details"]["exam_id"] == foreign["exam"].id


# ── PERIO-BE-18: voided exams ───────────────────────────────────────────────
def test_compare_voided_exam_refused_unless_included(client, patient):
    e1 = _exam(client, patient.id, "2026-01-01")
    e2 = _exam(client, patient.id, "2026-03-01")
    e3 = _exam(client, patient.id, "2026-06-01")
    _chart(client, e1["id"], [{"tooth_no": "1", "pd1": 3}])
    _chart(client, e2["id"], [{"tooth_no": "1", "pd1": 9}])   # will be voided
    _chart(client, e3["id"], [{"tooth_no": "1", "pd1": 5}])
    assert client.delete(f"{PREFIX}/perio-exams/{e2['id']}").status_code == 204

    ids = f"&exam_ids={e1['id']}&exam_ids={e2['id']}&exam_ids={e3['id']}"
    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}{ids}")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"] == {"code": "perio_exam_voided", "exam_id": e2["id"]}

    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}{ids}&include_voided=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["include_voided"] is True
    first, voided, last = body["exams"]
    assert voided["is_voided"] is True and voided["delta"] is None and voided["delta_vs_exam_id"] is None
    # the live exam's delta skips the voided one: 5 - 3, not 5 - 9
    assert last["delta_vs_exam_id"] == e1["id"]
    assert last["delta"]["mean_pd"] == 2.0


def test_compare_deduplicates_repeated_ids(client, patient):
    e1 = _exam(client, patient.id, "2026-01-01")
    r = client.get(f"{PREFIX}/perio-exams/compare?patient_id={patient.id}&exam_ids={e1['id']}&exam_ids={e1['id']}")
    assert r.status_code == 200
    assert len(r.json()["exams"]) == 1


# ── ride-along: perio rows are now tenant-scoped in the generic engine ──────
def test_generic_routes_do_not_cross_tenants(client, patient, foreign):
    fx = foreign["exam"]
    fd = foreign["detail"]
    assert client.get(f"{PREFIX}/perio-exams/{fx.id}").status_code == 404
    assert client.patch(f"{PREFIX}/perio-exams/{fx.id}", json={"notes": "x"}).status_code == 404
    assert client.delete(f"{PREFIX}/perio-exams/{fx.id}").status_code == 404
    assert client.get(f"{PREFIX}/perio-exam-details/{fd.id}").status_code == 404
    assert client.get(f"{PREFIX}/perio-exam-details?exam_id={fx.id}").json()["meta"]["total"] == 0
    assert client.get(f"{PREFIX}/perio-exams?patient_id={foreign['patient'].id}").json()["meta"]["total"] == 0
    # writing a row into the foreign exam is refused
    r = client.post(f"{PREFIX}/perio-exam-details", json={"exam_id": fx.id, "tooth_no": "2", "pd1": 3})
    assert r.status_code == 404
    r = client.post(f"{PREFIX}/perio-exams", json={"patient_id": foreign["patient"].id, "exam_date": "2026-01-01"})
    assert r.status_code == 404
