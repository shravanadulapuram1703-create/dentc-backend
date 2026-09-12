"""Lab Tracking (M12) gap tests — ``docs/lab-tracking/lab_tracking_backend_devreport.md``.

* LAB-1   ``labs`` catalog + ``lab_vendor_id`` / ``lab_short_notice`` on the appointment
* LAB-2   ``has_lab`` / ``lab_status`` / lab-date-range filters on ``GET /appointments``
* LAB-3   the scheduler feed carries the lab block
* LAB-4   cost report + PDF / CSV exports
* LAB-5   ``GET /appointments/lab-cases`` (office-wide, counts, paging)
* LAB-6   ``lab_dds`` > 100 chars is a 422 naming the field (was a 500)
* LAB-7   ``lab_cost`` overflow / negative is a 422 (was 500 / accepted)
* LAB-8   ``has_lab=false`` clears the lab block; lab data derives ``has_lab=true``
* LAB-9   received / due before sent is a 422 on the merge of payload + stored row
* LAB-10  unknown body keys are a 422 (``extra="forbid"``)
* LAB-11  archived appointments leave the default listing
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.db.models import Appointment, Lab, Office, Operatory, Patient, Provider, Tenant

TODAY = date.today()


def _appt(id_, patient, office, d=None, **lab):  # noqa: ANN001, ANN202
    return Appointment(
        id=id_, patient_id=patient.id, provider_id="PRV-L1", operatory_id="OPR-L1",
        office_id=office.id, date=d or date(2026, 8, 19), start_time=time(9, 0),
        end_time=time(9, 30), duration=30, status="Scheduled", **lab,
    )


@pytest.fixture
def lab_fixtures(db_session):
    tid = db_session._tenant_id
    office = Office(tenant_id=tid, office_code="LAB", name="Lab Office", timezone="America/New_York")
    office2 = Office(tenant_id=tid, office_code="LAB2", name="Second Office")
    db_session.add_all([office, office2])
    db_session.commit()
    db_session.refresh(office)
    db_session.refresh(office2)
    provider = Provider(id="PRV-L1", tenant_id=tid, office_id=office.id, name="Dr. Crown")
    operatory = Operatory(id="OPR-L1", office_id=office.id, name="Op L", provider_id="PRV-L1")
    patient = Patient(tenant_id=tid, first_name="Paloju", last_name="Udayk", chart_no="CH-L1",
                      cell_phone="555-0100")
    patient2 = Patient(tenant_id=tid, first_name="Ann", last_name="Other", chart_no="CH-L2")
    lab = Lab(tenant_id=tid, name="Creative Dental", phone="555-0199", default_turnaround_days=10)
    lab_inactive = Lab(tenant_id=tid, name="Closed Lab", is_active=False)
    db_session.add_all([provider, operatory, patient, patient2, lab, lab_inactive])
    db_session.commit()
    for obj in (patient, patient2, lab, lab_inactive):
        db_session.refresh(obj)
    # A second tenant with its own lab, to prove vendor ids are tenant-scoped.
    other = Tenant(name="Other Practice", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    foreign_lab = Lab(tenant_id=other.id, name="Foreign Lab")
    db_session.add(foreign_lab)
    db_session.commit()
    db_session.refresh(foreign_lab)

    db_session.add_all([
        # plain appointment, no lab
        _appt("APPT-L0", patient, office),
        # not sent
        _appt("APPT-L1", patient, office, has_lab=True, lab_cost=100, lab_dds="Dr. Crown"),
        # sent, due in the future
        _appt("APPT-L2", patient, office, has_lab=True, lab_cost=50, lab_vendor_id=lab.id,
              lab_sent_on=TODAY - timedelta(days=2), lab_due_on=TODAY + timedelta(days=5)),
        # overdue
        _appt("APPT-L3", patient, office, has_lab=True, lab_cost=75, lab_vendor_id=lab.id,
              lab_short_notice=True,
              lab_sent_on=TODAY - timedelta(days=20), lab_due_on=TODAY - timedelta(days=3)),
        # received, other patient, other office
        _appt("APPT-L4", patient2, office2, d=date(2026, 7, 1), has_lab=True, lab_cost=200,
              lab_sent_on=date(2026, 6, 20), lab_due_on=date(2026, 6, 30),
              lab_received_on=date(2026, 6, 29)),
    ])
    db_session.commit()
    return {"office": office, "office2": office2, "patient": patient, "patient2": patient2,
            "lab": lab, "lab_inactive": lab_inactive, "foreign_lab": foreign_lab}


def _err(resp):  # noqa: ANN001, ANN202
    return resp.json()["error"]


# ── LAB-6 / LAB-7 / LAB-10 — schema validation ───────────────────────────────
def test_lab_dds_over_100_chars_is_a_422_naming_the_field(client, lab_fixtures):
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"lab_dds": "x" * 150})
    assert resp.status_code == 422, resp.text
    err = _err(resp)
    assert err["code"] == "validation_error"
    assert any("lab_dds" in e["loc"] for e in err["details"])


def test_factory_propagates_column_lengths_to_every_generated_write_schema(client, lab_fixtures):
    # The same defect on any other String(n) column used to be a 500 too.
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"campaign_id": "c" * 101})
    assert resp.status_code == 422, resp.text
    assert any("campaign_id" in e["loc"] for e in _err(resp)["details"])
    assert client.patch("/api/v1/appointments/APPT-L1", json={"campaign_id": "c" * 100}).status_code == 200


@pytest.mark.parametrize("bad", ["123456789.00", -5, "12.345"])
def test_lab_cost_is_validated(client, lab_fixtures, bad):
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"lab_cost": bad})
    assert resp.status_code == 422, resp.text
    assert any("lab_cost" in e["loc"] for e in _err(resp)["details"])


def test_lab_cost_accepts_numbers_and_strings(client, lab_fixtures):
    assert client.patch("/api/v1/appointments/APPT-L1", json={"lab_cost": 123.45}).json()["lab_cost"] == "123.45"
    assert client.patch("/api/v1/appointments/APPT-L1", json={"lab_cost": "100.00"}).json()["lab_cost"] == "100.00"
    assert client.patch("/api/v1/appointments/APPT-L1", json={"lab_cost": None}).json()["lab_cost"] is None


def test_unknown_keys_are_rejected(client, lab_fixtures):
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"short_notice": True})
    assert resp.status_code == 422, resp.text
    assert any("short_notice" in e["loc"] for e in _err(resp)["details"])
    # ... and on create.
    resp = client.post("/api/v1/appointments", json={
        "id": "APPT-NEW", "provider_id": "PRV-L1", "office_id": lab_fixtures["office"].id,
        "date": "2026-08-20", "start_time": "10:00:00", "end_time": "10:30:00", "duration": 30,
        "lab_recvd_on": "2026-08-21",
    })
    assert resp.status_code == 422
    assert any("lab_recvd_on" in e["loc"] for e in _err(resp)["details"])


# ── LAB-1 — vendor + short notice ────────────────────────────────────────────
def test_vendor_and_short_notice_round_trip_with_vendor_name(client, lab_fixtures):
    lab = lab_fixtures["lab"]
    body = client.patch("/api/v1/appointments/APPT-L1", json={
        "lab_vendor_id": lab.id, "lab_short_notice": True,
    }).json()
    assert body["lab_vendor_id"] == lab.id
    assert body["lab_vendor_name"] == "Creative Dental"
    assert body["lab_short_notice"] is True
    assert body["lab_dds"] == "Dr. Crown"  # the dentist, untouched
    reloaded = client.get("/api/v1/appointments/APPT-L1").json()
    assert (reloaded["lab_vendor_name"], reloaded["lab_short_notice"]) == ("Creative Dental", True)


def test_vendor_must_belong_to_the_tenant(client, lab_fixtures):
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"lab_vendor_id": lab_fixtures["foreign_lab"].id})
    assert resp.status_code == 422
    assert _err(resp)["details"]["code"] == "lab_vendor_not_found"
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"lab_vendor_id": 999999})
    assert resp.status_code == 422


def test_inactive_vendor_blocks_a_move_but_not_an_edit(client, lab_fixtures, db_session):
    inactive = lab_fixtures["lab_inactive"]
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"lab_vendor_id": inactive.id})
    assert resp.status_code == 422
    assert _err(resp)["details"]["code"] == "lab_vendor_inactive"
    # A case already on the (since-retired) lab stays editable.
    appt = db_session.get(Appointment, "APPT-L1")
    appt.lab_vendor_id = inactive.id
    db_session.commit()
    assert client.patch("/api/v1/appointments/APPT-L1",
                        json={"lab_vendor_id": inactive.id, "lab_cost": "20.00"}).status_code == 200


def test_labs_catalog_crud_and_duplicate_guard(client, lab_fixtures):
    created = client.post("/api/v1/labs", json={"name": "Smile Lab", "phone": "555-0111", "city": "Austin"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["is_active"] is True
    assert body["created_by_name"]  # actor names attached on the read

    dup = client.post("/api/v1/labs", json={"name": "  smile   LAB "})
    assert dup.status_code == 409
    assert _err(dup)["details"]["code"] == "duplicate_lab_name"
    assert _err(dup)["details"]["matches"][0]["id"] == body["id"]
    assert client.post("/api/v1/labs", json={"name": "Smile Lab", "allow_duplicate_name": True}).status_code == 201

    probe = client.get("/api/v1/labs/name-availability", params={"name": "smile lab"}).json()
    assert probe["available"] is False and len(probe["conflicts"]) == 2
    assert client.get("/api/v1/labs/name-availability",
                      params={"name": "smile lab", "exclude_id": body["id"]}).json()["conflicts"][0]["id"] != body["id"]
    assert client.get("/api/v1/labs/name-availability", params={"name": "Brand New"}).json()["available"] is True

    # Inactive twins never collide; the foreign tenant's lab is invisible.
    assert client.post("/api/v1/labs", json={"name": "Closed Lab"}).status_code == 201
    assert client.post("/api/v1/labs", json={"name": "Foreign Lab"}).status_code == 201
    listing = client.get("/api/v1/labs?size=50").json()
    assert "Foreign Lab" in {r["name"] for r in listing["items"]}
    assert all(r["id"] != lab_fixtures["foreign_lab"].id for r in listing["items"])
    # Batch lookup for the grid.
    ids = f"{lab_fixtures['lab'].id},{body['id']}"
    assert {r["id"] for r in client.get(f"/api/v1/labs?ids={ids}").json()["items"]} == {lab_fixtures["lab"].id, body["id"]}


# ── LAB-8 — has_lab contract ─────────────────────────────────────────────────
def test_has_lab_false_clears_the_lab_block_including_same_payload_values(client, lab_fixtures):
    body = client.patch("/api/v1/appointments/APPT-L3", json={
        "has_lab": False, "lab_sent_on": "2026-09-11", "lab_dds": "stale",
    }).json()
    assert body["has_lab"] is False
    assert body["lab_vendor_id"] is None and body["lab_vendor_name"] is None
    assert body["lab_dds"] is None and body["lab_cost"] is None
    assert body["lab_sent_on"] is None and body["lab_due_on"] is None and body["lab_received_on"] is None
    assert body["lab_short_notice"] is False
    assert body["lab_status"] is None


def test_lab_data_on_a_non_lab_row_derives_has_lab_true(client, lab_fixtures):
    body = client.patch("/api/v1/appointments/APPT-L0", json={"lab_sent_on": "2026-08-20"}).json()
    assert body["has_lab"] is True
    assert body["lab_status"] in ("sent", "overdue")
    # A null / zero value is not lab data.
    body = client.patch("/api/v1/appointments/APPT-L0", json={"has_lab": False}).json()
    assert body["has_lab"] is False
    body = client.patch("/api/v1/appointments/APPT-L0", json={"lab_cost": 0, "lab_dds": None}).json()
    assert body["has_lab"] is False


def test_lab_status_is_derived_on_the_read(client, lab_fixtures):
    get = lambda i: client.get(f"/api/v1/appointments/{i}").json()["lab_status"]  # noqa: E731
    assert (get("APPT-L0"), get("APPT-L1"), get("APPT-L2"), get("APPT-L3"), get("APPT-L4")) == (
        None, "not_sent", "sent", "overdue", "received",
    )


# ── LAB-9 — date order ───────────────────────────────────────────────────────
def test_received_or_due_before_sent_is_a_422(client, lab_fixtures):
    resp = client.patch("/api/v1/appointments/APPT-L1", json={
        "lab_sent_on": "2026-09-20", "lab_due_on": "2026-09-10",
    })
    assert resp.status_code == 422
    assert _err(resp)["details"] == {
        "code": "lab_date_order", "field": "lab_due_on",
        "lab_sent_on": "2026-09-20", "lab_due_on": "2026-09-10",
    }
    # Judged against the stored sent date when only received arrives.
    assert client.patch("/api/v1/appointments/APPT-L1", json={"lab_sent_on": "2026-09-20"}).status_code == 200
    resp = client.patch("/api/v1/appointments/APPT-L1", json={"lab_received_on": "2026-09-01"})
    assert resp.status_code == 422
    assert _err(resp)["details"]["field"] == "lab_received_on"
    assert client.patch("/api/v1/appointments/APPT-L1", json={"lab_received_on": "2026-09-20"}).status_code == 200


def test_bad_stored_dates_do_not_block_an_unrelated_edit(client, lab_fixtures, db_session):
    appt = db_session.get(Appointment, "APPT-L1")
    appt.lab_sent_on, appt.lab_received_on = date(2026, 9, 20), date(2026, 9, 1)  # migrated nonsense
    db_session.commit()
    assert client.patch("/api/v1/appointments/APPT-L1", json={"lab_cost": "10.00"}).status_code == 200
    # ... but touching a date re-validates the merge.
    assert client.patch("/api/v1/appointments/APPT-L1", json={"lab_due_on": "2026-09-25"}).status_code == 422


def test_create_applies_the_same_rules(client, lab_fixtures):
    base = {
        "id": "APPT-NEW", "provider_id": "PRV-L1", "office_id": lab_fixtures["office"].id,
        "patient_id": lab_fixtures["patient"].id, "date": "2026-08-20", "start_time": "10:00:00",
        "end_time": "10:30:00", "duration": 30,
    }
    resp = client.post("/api/v1/appointments", json={**base, "has_lab": True, "lab_sent_on": "2026-08-25",
                                                       "lab_due_on": "2026-08-24"})
    assert resp.status_code == 422 and _err(resp)["details"]["code"] == "lab_date_order"
    resp = client.post("/api/v1/appointments", json={**base, "lab_vendor_id": lab_fixtures["lab"].id,
                                                       "lab_short_notice": True})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["has_lab"] is True  # derived from the vendor
    assert body["lab_vendor_name"] == "Creative Dental"
    assert body["lab_status"] == "not_sent"


# ── LAB-2 / LAB-11 — list filters ────────────────────────────────────────────
def _ids(resp):  # noqa: ANN001, ANN202
    return sorted(r["id"] for r in resp.json()["items"])


def test_has_lab_filter_is_honoured(client, lab_fixtures):
    assert _ids(client.get("/api/v1/appointments?has_lab=true&size=50")) == ["APPT-L1", "APPT-L2", "APPT-L3", "APPT-L4"]
    assert _ids(client.get("/api/v1/appointments?has_lab=false&size=50")) == ["APPT-L0"]


@pytest.mark.parametrize("status,expected", [
    ("not_sent", ["APPT-L1"]), ("sent", ["APPT-L2"]), ("overdue", ["APPT-L3"]),
    ("received", ["APPT-L4"]), ("not_received", ["APPT-L2", "APPT-L3"]),
])
def test_lab_status_filter(client, lab_fixtures, status, expected):
    assert _ids(client.get(f"/api/v1/appointments?lab_status={status}&size=50")) == expected


def test_lab_status_filter_rejects_unknown_values(client, lab_fixtures):
    resp = client.get("/api/v1/appointments?lab_status=lost")
    assert resp.status_code == 422
    assert _err(resp)["details"]["code"] == "invalid_lab_status"


def test_lab_date_range_and_vendor_filters(client, lab_fixtures):
    lab = lab_fixtures["lab"]
    assert _ids(client.get(f"/api/v1/appointments?lab_vendor_id={lab.id}&size=50")) == ["APPT-L2", "APPT-L3"]
    assert _ids(client.get("/api/v1/appointments?lab_short_notice=true&size=50")) == ["APPT-L3"]
    assert _ids(client.get("/api/v1/appointments?lab_received_on_from=2026-06-01&lab_received_on_to=2026-06-30")) == ["APPT-L4"]
    sent_to = (TODAY - timedelta(days=10)).isoformat()
    assert _ids(client.get(f"/api/v1/appointments?lab_sent_on_to={sent_to}&size=50")) == ["APPT-L3", "APPT-L4"]


def test_archived_appointments_leave_the_default_listing(client, lab_fixtures):
    assert client.delete("/api/v1/appointments/APPT-L2").status_code == 204
    assert "APPT-L2" not in _ids(client.get("/api/v1/appointments?size=50"))
    assert "APPT-L2" not in _ids(client.get("/api/v1/appointments?has_lab=true&size=50"))
    assert _ids(client.get("/api/v1/appointments?is_archived=true&size=50")) == ["APPT-L2"]
    # The lab data survives the archive, so a restore brings the case back whole.
    restored = client.post("/api/v1/appointments/APPT-L2/restore").json()
    assert restored["has_lab"] is True and restored["lab_vendor_id"] == lab_fixtures["lab"].id


# ── LAB-3 — scheduler feed ───────────────────────────────────────────────────
def test_scheduler_feed_carries_the_lab_block(client, lab_fixtures):
    rows = {r["id"]: r for r in client.get(
        "/api/v1/appointments/scheduler?date_from=2026-08-01&date_to=2026-08-31").json()}
    assert rows["APPT-L0"]["has_lab"] is False and rows["APPT-L0"]["lab_status"] is None
    l3 = rows["APPT-L3"]
    assert l3["has_lab"] is True
    assert l3["lab_vendor_name"] == "Creative Dental"
    assert l3["lab_short_notice"] is True
    assert l3["lab_status"] == "overdue"
    assert l3["lab_cost"] == "75.00"
    assert l3["lab_due_on"] == (TODAY - timedelta(days=3)).isoformat()


# ── LAB-5 — office-wide view ─────────────────────────────────────────────────
def test_lab_cases_view_is_denormalised_with_counts(client, lab_fixtures):
    body = client.get("/api/v1/appointments/lab-cases").json()
    assert body["meta"]["total"] == 4
    assert body["counts"] == {"all": 4, "not_sent": 1, "sent": 1, "overdue": 1, "received": 1,
                              "not_received": 2}
    assert body["total_cost"] == "425.00"
    assert body["as_of"] == TODAY.isoformat()
    by_id = {r["id"]: r for r in body["items"]}
    l3 = by_id["APPT-L3"]
    assert l3["patient_name"] == "Udayk, Paloju"
    assert l3["chart_no"] == "CH-L1"
    assert l3["patient_phone"] == "555-0100"
    assert l3["provider_name"] == "Dr. Crown"
    assert l3["office_name"] == "Lab Office"
    assert l3["lab_vendor_name"] == "Creative Dental"
    assert l3["lab_status"] == "overdue" and l3["days_overdue"] == 3
    assert by_id["APPT-L2"]["days_overdue"] == -5
    assert by_id["APPT-L1"]["days_overdue"] is None
    # Default sort: appointment date desc.
    assert [r["id"] for r in body["items"]][-1] == "APPT-L4"


def test_lab_cases_view_scopes_and_filters(client, lab_fixtures):
    office, office2, patient2 = lab_fixtures["office"], lab_fixtures["office2"], lab_fixtures["patient2"]
    body = client.get(f"/api/v1/appointments/lab-cases?office_id={office.id}").json()
    assert body["counts"]["all"] == 3 and body["counts"]["received"] == 0
    assert _ids_of(body) == ["APPT-L1", "APPT-L2", "APPT-L3"]
    assert _ids_of(client.get(f"/api/v1/appointments/lab-cases?office_id={office2.id}").json()) == ["APPT-L4"]
    assert _ids_of(client.get(f"/api/v1/appointments/lab-cases?patient_id={patient2.id}").json()) == ["APPT-L4"]
    # A status filter narrows items + total_cost but keeps the badges.
    body = client.get("/api/v1/appointments/lab-cases?lab_status=not_received").json()
    assert _ids_of(body) == ["APPT-L2", "APPT-L3"]
    assert body["meta"]["total"] == 2
    assert body["total_cost"] == "125.00"
    assert body["counts"]["all"] == 4
    # Search reaches the lab name, the DDS and the patient.
    assert _ids_of(client.get("/api/v1/appointments/lab-cases?search=creative").json()) == ["APPT-L2", "APPT-L3"]
    assert _ids_of(client.get("/api/v1/appointments/lab-cases?search=crown").json()) == ["APPT-L1"]
    assert _ids_of(client.get("/api/v1/appointments/lab-cases?search=other").json()) == ["APPT-L4"]
    # Sorting + paging.
    page = client.get("/api/v1/appointments/lab-cases?sort=lab_cost&order=desc&size=2&page=2").json()
    assert [r["id"] for r in page["items"]] == ["APPT-L3", "APPT-L2"]
    assert page["meta"]["pages"] == 2
    # as_of moves the status boundary.
    far = (TODAY + timedelta(days=30)).isoformat()
    assert client.get(f"/api/v1/appointments/lab-cases?as_of={far}").json()["counts"]["overdue"] == 2


def test_lab_cases_view_hides_archived_unless_asked(client, lab_fixtures):
    client.delete("/api/v1/appointments/APPT-L3")
    assert _ids_of(client.get("/api/v1/appointments/lab-cases").json()) == ["APPT-L1", "APPT-L2", "APPT-L4"]
    body = client.get("/api/v1/appointments/lab-cases?include_archived=true").json()
    assert _ids_of(body) == ["APPT-L1", "APPT-L2", "APPT-L3", "APPT-L4"]
    assert {r["id"]: r["is_archived"] for r in body["items"]}["APPT-L3"] is True


def _ids_of(body):  # noqa: ANN001, ANN202
    return sorted(r["id"] for r in body["items"])


# ── LAB-4 — reports / exports ────────────────────────────────────────────────
def test_lab_cost_report_groups(client, lab_fixtures):
    body = client.get("/api/v1/appointments/lab-cases/cost-report").json()
    assert body["group_by"] == "vendor" and body["date_basis"] == "appointment"
    assert body["case_count"] == 4 and body["total_cost"] == "425.00"
    rows = {r["label"]: r for r in body["rows"]}
    assert rows["Creative Dental"] == {"key": str(lab_fixtures["lab"].id), "label": "Creative Dental",
                                       "case_count": 2, "total_cost": "125.00"}
    assert rows["(no lab)"]["total_cost"] == "300.00"
    assert rows["(no lab)"]["key"] is None
    # Grouped by month on the received date: only APPT-L4 has one.
    body = client.get("/api/v1/appointments/lab-cases/cost-report?group_by=month&date_basis=received").json()
    assert body["rows"] == [{"key": "2026-06", "label": "Jun 2026", "case_count": 1, "total_cost": "200.00"}]
    # Date range on the appointment date.
    body = client.get("/api/v1/appointments/lab-cases/cost-report?date_from=2026-08-01&group_by=provider").json()
    assert body["case_count"] == 3 and body["rows"][0]["label"] == "Dr. Crown"
    body = client.get("/api/v1/appointments/lab-cases/cost-report?group_by=dds").json()
    assert {r["label"] for r in body["rows"]} == {"Dr. Crown", "(no DDS)"}


def test_lab_report_pdfs_and_csv(client, lab_fixtures):
    resp = client.get("/api/v1/appointments/lab-cases/report.pdf?lab_status=not_received")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    resp = client.get(f"/api/v1/appointments/lab-cases/cost-report.pdf?office_id={lab_fixtures['office'].id}")
    assert resp.status_code == 200 and resp.content.startswith(b"%PDF")
    resp = client.get("/api/v1/appointments/lab-cases/export.csv?lab_status=received")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.strip().splitlines()
    assert lines[0].startswith("id,office_name,patient_id,patient_name")
    assert len(lines) == 2 and lines[1].startswith("APPT-L4,Second Office")
    # Every print is audited (action=PRINT, resource_type=lab_report).
    logs = client.get("/api/v1/audit-logs?size=50").json()["items"]
    assert sum(1 for l in logs if l["action"] == "PRINT" and l["resource_type"] == "lab_report") == 3


# ── metadata ─────────────────────────────────────────────────────────────────
def test_lab_tracking_rules_are_published(client, lab_fixtures):
    body = client.get("/api/v1/metadata/lab-tracking-rules").json()
    assert body["statuses"] == ["not_sent", "sent", "overdue", "received"]
    assert "not_received" in body["status_filters"]
    assert "lab_date_order" in body["errors"] and "duplicate_lab_name" in body["errors"]
    assert body["fields"]["lab_dds"].startswith("the dentist")
