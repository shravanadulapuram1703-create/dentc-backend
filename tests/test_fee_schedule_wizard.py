"""New Fee Schedule Wizard backend (FSW-1..9).

FSW-1 atomic wizard · FSW-2 bulk assignments · FSW-3 office-default pointers ·
FSW-4 legacy schedule-type labels · FSW-5 taxonomy-code specialties · FSW-6
multi-office provider lookup · FSW-7 assignment filters · FSW-8 server import ·
FSW-9 scope read.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.core.config import settings
from app.db.models import (
    FeeSchedule,
    FeeScheduleAssignment,
    FeeScheduleEntry,
    Office,
    ProcedureCode,
    Provider,
    ProviderOffice,
)

PREFIX = "/api/v1"
D = Decimal
ORTHO = "1223X0400X"


@pytest.fixture
def codes(db_session) -> None:
    for code in ("D0120", "D1110", "D8080"):
        db_session.add(ProcedureCode(code=code, description=code, category="Diag"))
    db_session.commit()


def _office(db_session, code: str, **kw) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code=code, name=f"Office {code}", short_id=code, **kw)
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def offices(db_session) -> tuple[Office, Office, Office]:
    return _office(db_session, "W1"), _office(db_session, "W2"), _office(db_session, "W3")


def _provider(db_session, pid: str, office: Office, **kw) -> Provider:
    p = Provider(id=pid, tenant_id=db_session._tenant_id, office_id=office.id, name=pid, is_active=True, **kw)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def providers(db_session, offices):
    o1, o2, o3 = offices
    a = _provider(db_session, "PRV-A", o1)
    b = _provider(db_session, "PRV-B", o2, taxonomy_code=ORTHO)
    c = _provider(db_session, "PRV-C", o3, specialty="Orthodontist")
    # PRV-A also works at office 2 through the roster join.
    db_session.add(ProviderOffice(tenant_id=db_session._tenant_id, office_id=o2.id, provider_id="PRV-A"))
    db_session.commit()
    return a, b, c


def _schedule(db_session, name: str, **kw) -> FeeSchedule:
    fs = FeeSchedule(tenant_id=db_session._tenant_id, name=name, fee_type=kw.pop("fee_type", "standard"),
                     pricing_model=kw.pop("pricing_model", "percentage"), is_active=True, **kw)
    db_session.add(fs)
    db_session.commit()
    db_session.refresh(fs)
    return fs


def _schedules_named(db_session, name: str) -> list[FeeSchedule]:
    db_session.expire_all()
    return db_session.query(FeeSchedule).filter(FeeSchedule.name == name).all()


# ── FSW-1: the atomic wizard ─────────────────────────────────────────────────


def test_wizard_creates_everything_in_one_call(client, db_session, codes, offices, providers):
    o1, o2, _ = offices
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Wizard PPO", "fee_type": "standard", "effective_date": "2026-01-01"},
        "entries": [{"procedure_code": "D0120", "patient_fee": 55},
                    {"procedure_code": "d1110", "patient_fee": 95.5}],
        "assignments": [{"provider_id": "PRV-A", "office_id": o1.id},
                        {"provider_id": "PRV-A", "office_id": o2.id}],
        "office_defaults": {"office_ids": [o2.id], "set_default_fee_schedule": True},
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ok"] is True
    sid = body["fee_schedule"]["id"]
    assert body["entries"]["created"] == 2
    assert body["entries"]["effective_date"] == "2026-01-01"
    assert body["assignments"]["summary"]["created"] == 2
    assert body["office_defaults"]["results"][0]["previous_default_fee_schedule_id"] is None

    db_session.expire_all()
    entries = db_session.query(FeeScheduleEntry).filter_by(fee_schedule_id=sid).all()
    assert {e.procedure_code: e.patient_fee for e in entries} == {"D0120": D("55.00"), "D1110": D("95.50")}
    assert all(e.tenant_id == db_session._tenant_id for e in entries)
    assert db_session.query(FeeScheduleAssignment).filter_by(fee_schedule_id=sid).count() == 2
    assert db_session.get(Office, o2.id).default_fee_schedule_id == sid


def test_wizard_conflict_rolls_back_everything(client, db_session, codes, offices, providers):
    o1, _, _ = offices
    other = _schedule(db_session, "Existing")
    db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id, fee_schedule_id=other.id,
                                         provider_id="PRV-A", office_id=o1.id))
    db_session.commit()
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Wizard Rollback"},
        "entries": [{"procedure_code": "D0120", "patient_fee": 40}],
        "assignments": [{"provider_id": "PRV-A", "office_id": o1.id}],
    })
    assert r.status_code == 409, r.text
    details = r.json()["error"]["details"]
    assert details["code"] == "fee_schedule_wizard_failed"
    outcome = details["assignments"]["outcomes"][0]
    assert outcome["status"] == "conflict"
    assert outcome["previous_fee_schedule_name"] == "Existing"
    assert _schedules_named(db_session, "Wizard Rollback") == []
    assert db_session.query(FeeScheduleEntry).filter_by(procedure_code="D0120").count() == 0


def test_wizard_rebind_moves_the_existing_row(client, db_session, codes, offices, providers):
    o1, _, _ = offices
    other = _schedule(db_session, "Old")
    row = FeeScheduleAssignment(tenant_id=db_session._tenant_id, fee_schedule_id=other.id,
                                provider_id="PRV-A", office_id=o1.id)
    db_session.add(row)
    db_session.commit()
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Rebinder"}, "on_conflict": "rebind",
        "assignments": [{"provider_id": "PRV-A", "office_id": o1.id}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["assignments"]["outcomes"][0]["status"] == "rebound"
    db_session.expire_all()
    assert db_session.get(FeeScheduleAssignment, row.id).fee_schedule_id == r.json()["fee_schedule"]["id"]


def test_wizard_invalid_entry_is_422_and_writes_nothing(client, db_session, codes):
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Bad Entries"},
        "entries": [{"procedure_code": "D0120", "patient_fee": 10},
                    {"procedure_code": "ZZZZ", "patient_fee": 10},
                    {"procedure_code": "D1110", "patient_fee": -1}],
    })
    assert r.status_code == 422, r.text
    errs = r.json()["error"]["details"]["entries"]["errors"]
    assert {e["error_code"] for e in errs} == {"unknown_procedure_code", "fee_entry_negative"}
    assert _schedules_named(db_session, "Bad Entries") == []


def test_wizard_dry_run_reports_without_writing(client, db_session, codes, offices, providers):
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Dry"}, "dry_run": True,
        "entries": [{"procedure_code": "D0120", "patient_fee": 10}],
        "assignments": [{"provider_id": "PRV-A"}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["fee_schedule"]["id"] is None
    assert _schedules_named(db_session, "Dry") == []


def test_wizard_refuses_scope_only_assignment(client, db_session, offices):
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Scope Only"}, "assignments": [{"office_id": offices[0].id}],
    })
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["assignments"]["outcomes"][0]["error_code"] == "assignment_needs_target"


def test_wizard_office_default_reports_the_replaced_pointer(client, db_session, offices):
    o1 = offices[0]
    old = _schedule(db_session, "Old Default")
    o1.default_fee_schedule_id = old.id
    db_session.commit()
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "New Default"},
        "office_defaults": {"office_ids": [o1.id], "set_default_fee_schedule": True},
    })
    assert r.status_code == 201, r.text
    res = r.json()["office_defaults"]["results"][0]
    assert res["replaced_default"] is True
    assert res["previous_default_fee_schedule_id"] == old.id
    assert res["previous_default_fee_schedule_name"] == "Old Default"


def test_wizard_copy_from_existing_then_override(client, db_session, codes):
    src = _schedule(db_session, "Source")
    for code, fee in (("D0120", 50), ("D1110", 90)):
        db_session.add(FeeScheduleEntry(tenant_id=db_session._tenant_id, fee_schedule_id=src.id,
                                        procedure_code=code, patient_fee=D(str(fee)),
                                        effective_date=date(2025, 1, 1)))
    db_session.commit()
    r = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Copied", "effective_date": "2026-02-01"},
        "copy_from_schedule_id": src.id,
        "entries": [{"procedure_code": "D1110", "patient_fee": 99}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["entries"]["copied"] == 2
    sid = r.json()["fee_schedule"]["id"]
    db_session.expire_all()
    fees = {e.procedure_code: e.patient_fee
            for e in db_session.query(FeeScheduleEntry).filter_by(fee_schedule_id=sid)}
    assert fees == {"D0120": D("50.00"), "D1110": D("99.00")}


# ── FSW-4: legacy schedule-type labels ───────────────────────────────────────


@pytest.mark.parametrize("label, fee_type, model", [
    ("Ins-PPO", "carrier", "percentage"),
    ("Ins-Managed Care", "plan", "copay"),
    ("ins pat co-pay", "plan", "copay"),
    ("Office", "standard", "percentage"),
])
def test_legacy_label_sets_both_columns(client, label, fee_type, model):
    r = client.post(f"{PREFIX}/fee-schedules", json={"name": f"L {label}", "fee_type": label})
    assert r.status_code == 201, r.text
    assert (r.json()["fee_type"], r.json()["pricing_model"]) == (fee_type, model)


def test_metadata_publishes_legacy_schedule_types(client):
    body = client.get(f"{PREFIX}/fee-schedules/metadata").json()
    labels = {row["legacy_label"]: row for row in body["legacy_schedule_types"]}
    assert labels["Ins-PPO"]["fee_type"] == "carrier"
    assert labels["Ins-Smart Fee"]["provisional"] is True
    carrier = next(t for t in body["fee_types"] if t["code"] == "carrier")
    assert "Ins-PPO" in carrier["legacy_labels"]


# ── FSW-2: bulk assignments ──────────────────────────────────────────────────


def test_bulk_assign_created_then_unchanged_then_conflict(client, db_session, offices, providers):
    o1, o2, _ = offices
    fs = _schedule(db_session, "Bulk")
    rows = [{"fee_schedule_id": fs.id, "provider_id": "PRV-A", "office_id": o1.id},
            {"fee_schedule_id": fs.id, "provider_id": "PRV-B", "office_id": o2.id}]
    r = client.post(f"{PREFIX}/fee-schedule-assignments/bulk", json={"assignments": rows})
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["created"] == 2

    again = client.post(f"{PREFIX}/fee-schedule-assignments/bulk", json={"assignments": rows})
    assert again.json()["summary"]["unchanged"] == 2

    other = _schedule(db_session, "Bulk Other")
    moved = [dict(row, fee_schedule_id=other.id) for row in rows]
    probe = client.post(f"{PREFIX}/fee-schedule-assignments/bulk",
                        json={"assignments": moved, "dry_run": True})
    assert probe.status_code == 200
    assert probe.json()["summary"]["conflict"] == 2
    assert probe.json()["outcomes"][0]["previous_fee_schedule_name"] == "Bulk"

    refused = client.post(f"{PREFIX}/fee-schedule-assignments/bulk", json={"assignments": moved})
    assert refused.status_code == 409, refused.text

    skipped = client.post(f"{PREFIX}/fee-schedule-assignments/bulk",
                          json={"assignments": moved, "on_conflict": "skip"})
    assert skipped.json()["summary"]["skipped"] == 2

    rebound = client.post(f"{PREFIX}/fee-schedule-assignments/bulk",
                          json={"assignments": moved, "on_conflict": "rebind"})
    assert rebound.json()["summary"]["rebound"] == 2
    db_session.expire_all()
    assert db_session.query(FeeScheduleAssignment).filter_by(fee_schedule_id=other.id).count() == 2


def test_bulk_assign_invalid_row_rolls_back_the_batch(client, db_session, offices, providers):
    fs = _schedule(db_session, "Bulk Bad")
    r = client.post(f"{PREFIX}/fee-schedule-assignments/bulk", json={"assignments": [
        {"fee_schedule_id": fs.id, "provider_id": "PRV-A"},
        {"fee_schedule_id": fs.id, "provider_id": "PRV-NOPE"},
        {"fee_schedule_id": fs.id, "provider_id": "PRV-A"},
    ]})
    assert r.status_code == 422, r.text
    statuses = [o.get("error_code") or o["status"] for o in r.json()["error"]["details"]["outcomes"]]
    assert statuses == ["created", "assignment_provider_invalid", "assignment_duplicate_in_request"]
    db_session.expire_all()
    assert db_session.query(FeeScheduleAssignment).filter_by(fee_schedule_id=fs.id).count() == 0


# ── FSW-5: specialty = taxonomy code ─────────────────────────────────────────


def test_specialty_assignment_is_folded_onto_the_taxonomy_code(client, db_session):
    fs = _schedule(db_session, "Ortho List")
    r = client.post(f"{PREFIX}/fee-schedule-assignments",
                    json={"fee_schedule_id": fs.id, "specialty_id": "orthodontist"})
    assert r.status_code == 201, r.text
    assert r.json()["specialty_id"] == ORTHO
    bad = client.post(f"{PREFIX}/fee-schedule-assignments",
                      json={"fee_schedule_id": fs.id, "specialty_id": "Witch Doctor"})
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["details"]["code"] == "assignment_specialty_unknown"


@pytest.mark.parametrize("engine_v2", [False, True])
def test_specialty_assignment_prices_both_providers(client, db_session, codes, offices, providers,
                                                    monkeypatch, engine_v2):
    monkeypatch.setattr(settings, "PRICING_ENGINE_V2", engine_v2)
    fs = _schedule(db_session, "Ortho Prices")
    db_session.add(FeeScheduleEntry(tenant_id=db_session._tenant_id, fee_schedule_id=fs.id,
                                    procedure_code="D8080", patient_fee=D("4500"),
                                    effective_date=date(2020, 1, 1)))
    db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id, fee_schedule_id=fs.id,
                                         specialty_id=ORTHO))
    db_session.commit()
    # PRV-B carries the code; PRV-C only the free text "Orthodontist"; PRV-A neither.
    for pid, expected in (("PRV-B", fs.id), ("PRV-C", fs.id), ("PRV-A", None)):
        r = client.post(f"{PREFIX}/pricing/quote",
                        json={"provider_id": pid, "lines": [{"procedure_code": "D8080"}]})
        assert r.status_code == 200, r.text
        assert r.json()["lines"][0]["fee_schedule_id"] == expected, pid


def test_provider_specialties_catalog(client, providers):
    rows = client.get(f"{PREFIX}/provider-specialties").json()
    ortho = next(r for r in rows if r["specialty_id"] == ORTHO)
    assert ortho["provider_ids"] == ["PRV-B", "PRV-C"]
    assert next(r for r in rows if r["specialty_id"] is None)["provider_count"] == 1


# ── FSW-6: multi-office provider lookup ──────────────────────────────────────


def test_providers_office_ids_and_served_office_ids(client, offices, providers):
    o1, o2, o3 = offices
    r = client.get(f"{PREFIX}/providers", params={"office_ids": f"{o1.id},{o2.id}", "size": 50})
    assert r.status_code == 200, r.text
    items = {p["id"]: p for p in r.json()["items"]}
    assert set(items) == {"PRV-A", "PRV-B"}
    assert items["PRV-A"]["served_office_ids"] == sorted([o1.id, o2.id])
    assert items["PRV-B"]["specialty_code"] == ORTHO
    one = client.get(f"{PREFIX}/providers", params={"office_ids": str(o3.id)}).json()["items"]
    assert [p["id"] for p in one] == ["PRV-C"]
    assert one[0]["specialty_label"].startswith("Orthodontics")


# ── FSW-7: assignment filters ────────────────────────────────────────────────


def test_assignment_list_filters(client, db_session, offices, providers):
    o1 = offices[0]
    fs = _schedule(db_session, "Filters")
    t = db_session._tenant_id
    db_session.add_all([
        FeeScheduleAssignment(tenant_id=t, fee_schedule_id=fs.id, provider_id="PRV-A", office_id=o1.id),
        FeeScheduleAssignment(tenant_id=t, fee_schedule_id=fs.id, provider_id="PRV-B"),
        FeeScheduleAssignment(tenant_id=t, fee_schedule_id=fs.id, specialty_id=ORTHO),
    ])
    db_session.commit()

    def ids(**params):  # noqa: ANN202
        r = client.get(f"{PREFIX}/fee-schedule-assignments", params={"fee_schedule_id": fs.id, **params})
        assert r.status_code == 200, r.text
        return r.json()["items"]

    assert len(ids(has_provider=True)) == 2
    assert len(ids(has_provider=False)) == 1
    assert len(ids(has_specialty=True)) == 1
    assert len(ids(specialty_id="Orthodontics")) == 1
    assert [a["provider_id"] for a in ids(provider_ids="PRV-B,PRV-X")] == ["PRV-B"]
    assert len(ids(office_ids=str(o1.id))) == 1
    assert len(ids(has_payer=True)) == 0


# ── FSW-8: server import ─────────────────────────────────────────────────────


CSV = ("﻿procedure_code,description,fee,effective_date\r\n"
       "D0120,Exam,55.00,2026-01-01\r\n"
       "D1110,Prophy,\"$1,110.00\",\r\n"
       "ZZZ,Bad,1,\r\n"
       "D8080,Ortho,-5,\r\n"
       "D0120,Again,60,2026-01-01\r\n")


def _upload(client, sid, name, data, **form):  # noqa: ANN001, ANN202
    return client.post(f"{PREFIX}/fee-schedules/{sid}/entries/import",
                       files={"file": (name, data, "application/octet-stream")},
                       data={k: str(v).lower() if isinstance(v, bool) else v for k, v in form.items()})


def test_import_csv_reports_rows_and_writes_the_valid_ones(client, db_session, codes):
    fs = _schedule(db_session, "Import CSV", effective_date=date(2026, 3, 1))
    r = _upload(client, fs.id, "fees.csv", CSV.encode("utf-8"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["total_rows"], body["valid_rows"], body["created"]) == (5, 2, 2)
    assert {e["row"]: e["code"] for e in body["errors"]} == {
        3: "unknown_procedure_code", 4: "fee_entry_negative", 5: "duplicate_row"}
    db_session.expire_all()
    rows = {(e.procedure_code, e.effective_date): e.patient_fee
            for e in db_session.query(FeeScheduleEntry).filter_by(fee_schedule_id=fs.id)}
    # A blank effective_date takes the schedule's own date.
    assert rows == {("D0120", date(2026, 1, 1)): D("55.00"), ("D1110", date(2026, 3, 1)): D("1110.00")}


def test_import_dry_run_and_all_or_nothing_write_nothing(client, db_session, codes):
    fs = _schedule(db_session, "Import Dry")
    for form in ({"dry_run": True}, {"all_or_nothing": True}):
        r = _upload(client, fs.id, "fees.csv", CSV.encode("utf-8"), **form)
        assert r.status_code == 200, r.text
        assert r.json()["written"] is False
    db_session.expire_all()
    assert db_session.query(FeeScheduleEntry).filter_by(fee_schedule_id=fs.id).count() == 0


def test_import_native_xlsx_with_plan_pays(client, db_session, codes):
    fs = _schedule(db_session, "Import XLSX", fee_type="plan", pricing_model="copay")
    wb = Workbook()
    ws = wb.active
    ws.append(["Code", "Description", "Fee", "Plan Pays", "AMB Code", "Effective Date"])
    ws.append(["D0120", "Exam", 10, 45.5, "", date(2026, 1, 1)])
    buf = io.BytesIO()
    wb.save(buf)
    r = _upload(client, fs.id, "fees.xlsx", buf.getvalue())
    assert r.status_code == 200, r.text
    assert r.json()["file_type"] == "xlsx"
    assert r.json()["created"] == 1
    db_session.expire_all()
    entry = db_session.query(FeeScheduleEntry).filter_by(fee_schedule_id=fs.id).one()
    assert (entry.patient_fee, entry.insurance_fee) == (D("10.00"), D("45.50"))


def test_import_bad_header_is_422(client, db_session):
    fs = _schedule(db_session, "Import Header")
    r = _upload(client, fs.id, "fees.csv", b"foo,bar\n1,2\n")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["details"]["code"] == "import_header_invalid"


# ── FSW-9: scope read ────────────────────────────────────────────────────────


def test_scope_round_trips_the_wizard(client, db_session, codes, offices, providers):
    o1, o2, _ = offices
    created = client.post(f"{PREFIX}/fee-schedules/wizard", json={
        "schedule": {"name": "Scoped"},
        "assignments": [{"provider_id": "PRV-A", "office_id": o1.id},
                        {"provider_id": "PRV-A", "office_id": o2.id}],
        "office_defaults": {"office_ids": [o2.id], "set_default_fee_schedule": True},
    })
    sid = created.json()["fee_schedule"]["id"]
    r = client.get(f"{PREFIX}/fee-schedules/{sid}/scope")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["assignments"]) == 2
    assert body["assignments"][0]["provider_name"] == "PRV-A"
    assert body["office_pointers"] == [{"office_id": o2.id, "office_name": "Office W2",
                                        "is_default_fee_schedule": True, "is_ucr_fee_schedule": False}]
    assert body["wizard"] == {
        "offices": {"mode": "specific", "office_ids": sorted([o1.id, o2.id])},
        "providers": {"mode": "providers", "provider_ids": ["PRV-A"], "specialty_ids": []},
        "is_office_default": True,
    }
