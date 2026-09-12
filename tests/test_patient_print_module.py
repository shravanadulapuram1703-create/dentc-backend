"""Patient print module (docs/print/patient_print_backend_devreport.md).

PRINT-1 the four server-rendered PDFs + the print audit row, PRINT-2 the
resolved letterhead on OfficeRead, PRINT-3 the lifted feed cap, PRINT-6 the
day-totals deductible, PRINT-7/8/9 the columns the Insurance / Ledger prints
now consume, and tenant isolation on every report.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.models import (
    AccountSettings,
    AuditLog,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    InsuranceSubscriber,
    Office,
    OfficeStatementSettings,
    OrthoPlan,
    Patient,
    PatientInsurance,
    Provider,
    ResponsibleParty,
    Tenant,
)

PREFIX = "/api/v1"
TODAY = date.today().isoformat()

# A 1x1 PNG so the logo / photo branches exercise reportlab's image path.
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc00000030101002ac6b34d0000000049454e44ae426082"
)


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="PR1", name="Print Office", short_id="PR1",
               address_line1="1 Main St", city="Austin", state="TX", zip="78701", phone="512-555-0100",
               timezone="America/Chicago")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def rp(db_session) -> ResponsibleParty:
    r = ResponsibleParty(tenant_id=db_session._tenant_id, first_name="Guar", last_name="Antor",
                         legacy_id="RP-LEG-1")
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


@pytest.fixture
def patient(db_session, office, rp) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Print", last_name="Patient", middle_initial="Q",
                chart_no="PR-001", home_office_id=office.id, dob=date(1990, 1, 2), gender="F",
                email="p@print.local", cell_phone="512-555-0199", responsible_party_id=str(rp.id),
                patient_notes="Prefers morning visits", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def sibling(db_session, office, rp) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Sib", last_name="Patient",
                chart_no="PR-002", home_office_id=office.id, responsible_party_id=str(rp.id), is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def provider(db_session, office) -> Provider:
    pr = Provider(id="PRPRV", tenant_id=db_session._tenant_id, office_id=office.id,
                  name="Dr Print", short_id="DRPR")
    db_session.add(pr)
    db_session.commit()
    return pr


@pytest.fixture
def proc_code(client):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D2750", "description": "Crown PFM", "category": "Restorative", "default_fee": 1000})
    assert r.status_code == 201, r.text
    return "D2750"


@pytest.fixture
def coverage(db_session, patient, office):
    """Primary dental slot: 80 % on D2750 with a $50 remaining deductible."""
    tid = db_session._tenant_id
    carrier = InsuranceCarrier(tenant_id=tid, name="Delta Print", carrier_type="dental", payer_id="PAY1",
                               phone="800-555-0000", legacy_id="CAR-9")
    db_session.add(carrier)
    db_session.flush()
    plan = InsurancePlan(tenant_id=tid, carrier_id=carrier.id, group_number="GRP-77", plan_type="PPO",
                         individual_max=1500, individual_deductible=50, family_max=3000,
                         anniversary_date=date(2026, 1, 1))
    db_session.add(plan)
    db_session.flush()
    db_session.add(InsuranceCoverageRule(ins_plan_id=plan.id, start_code="D2000", end_code="D2999",
                                         coverage_pct=80))
    sub = InsuranceSubscriber(tenant_id=tid, ins_plan_id=plan.id, sub_first_name="Sub", sub_last_name="Scriber",
                              sub_member_id="MEM-1", sub_dob=date(1985, 5, 5), sub_gender="M",
                              marital_status="Married", sub_phone="512-555-0111",
                              effective_date=date(2025, 1, 1), plan_effective_date=date(2024, 6, 1),
                              plan_term_date=date(2027, 6, 1), elig_status="Verified", notes="Sub notes")
    db_session.add(sub)
    db_session.flush()
    slot = PatientInsurance(patient_id=patient.id, ins_plan_id=plan.id, subscriber_id=sub.id,
                            legacy_plan_type="D", insurance_type="primary", relationship="Child",
                            sec_sub_rel_to_prim_sub="Spouse", deductible_remaining=50, max_remaining=1200,
                            is_active=True)
    db_session.add(slot)
    db_session.commit()
    return {"carrier": carrier, "plan": plan, "subscriber": sub, "slot": slot}


def _proc(client, patient_id, office_id, provider_id, code, fee, dos, item_id, **extra):
    body = {"id": item_id, "patient_id": patient_id, "office_id": office_id, "provider_id": provider_id,
            "procedure_code": code, "fee": fee, "date_of_service": dos, **extra}
    r = client.post(f"{PREFIX}/patient-procedures", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _pay(client, patient_id, amount, pay_id, office_id, pdate=TODAY):
    r = client.post(f"{PREFIX}/patient-payments", json={
        "id": pay_id, "patient_id": patient_id, "amount": amount, "payment_date": pdate,
        "payment_type": "patient", "office_id": office_id})
    assert r.status_code == 201, r.text
    return r.json()


def _assert_pdf(resp, name_part: str) -> None:
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"
    assert name_part in resp.headers["content-disposition"]


def _print_audits(db_session, patient_id):
    return db_session.execute(
        select(AuditLog).where(AuditLog.action == "PRINT", AuditLog.patient_id == patient_id)
    ).scalars().all()


# ── PRINT-1: the four reports ─────────────────────────────────────────────────
def test_overview_report_renders_and_audits(client, db_session, patient, sibling, office, provider, proc_code, coverage):
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, TODAY, "OV1", insurance_estimate=800)
    _pay(client, patient.id, 100, "OVP1", office.id)
    db_session.add(OrthoPlan(tenant_id=db_session._tenant_id, patient_id=patient.id, office_id=office.id,
                             pat_amt_financed=2400, pat_rem_amt=1200, pat_rem_payments=6,
                             treat_start_date=date(2026, 1, 15), is_active=True))
    db_session.commit()

    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/overview")
    _assert_pdf(r, f"patient-overview-{patient.id}.pdf")

    audits = _print_audits(db_session, patient.id)
    assert len(audits) == 1
    assert audits[0].resource_type == "patient_report"
    assert audits[0].resource_id == "overview"
    assert audits[0].method == "GET"
    assert audits[0].user_id == db_session._admin.id
    assert audits[0].details["report"] == "overview"


def test_ledger_report_account_scope_with_filters(client, db_session, patient, sibling, office, provider, proc_code):
    for i in range(12):
        _proc(client, patient.id, office.id, provider.id, proc_code, 100 + i, TODAY, f"LG{i}")
    _proc(client, sibling.id, office.id, provider.id, proc_code, 55, TODAY, "LGS")
    _pay(client, patient.id, 40, "LGP", office.id)

    r = client.get(
        f"{PREFIX}/patients/{patient.id}/reports/ledger",
        params={"scope": "account", "transaction_type": "charge", "sort_by": "amount", "order": "desc",
                "include_claims": "true", "date_from": "2020-01-01"},
    )
    _assert_pdf(r, f"account-ledger-{patient.id}.pdf")

    audit = _print_audits(db_session, patient.id)[0]
    assert audit.resource_id == "ledger"
    assert audit.details["params"]["scope"] == "account"
    assert audit.details["params"]["transaction_type"] == "charge"
    assert audit.details["params"]["sort_by"] == "amount"
    # Unset params are not recorded.
    assert "date_to" not in audit.details["params"]

    # Patient scope + no filters renders too (no rows on the sibling in this scope).
    r = client.get(f"{PREFIX}/patients/{sibling.id}/reports/ledger")
    _assert_pdf(r, f"patient-ledger-{sibling.id}.pdf")


def test_transactions_report_and_day_totals_deductible(client, db_session, patient, office, provider, proc_code, coverage):
    # The engine prices D2750 at its stored fee: $50 deductible consumed, 80 % of the rest.
    _proc(client, patient.id, office.id, provider.id, proc_code, 1000, TODAY, "TX1", insurance_estimate=760)
    # Over-pay so a refundable credit exists (the refund policy refuses otherwise).
    _pay(client, patient.id, 1200, "TXP1", office.id)
    r = client.post(f"{PREFIX}/patients/{patient.id}/refunds", json={
        "refund_amount": 25, "refund_method": "check", "reason": "overpayment", "refund_date": TODAY,
        "office_id": office.id})
    assert r.status_code in (200, 201), r.text

    totals = client.get(f"{PREFIX}/patients/{patient.id}/day-totals", params={"date": TODAY})
    assert totals.status_code == 200, totals.text
    body = totals.json()
    assert body["transaction_count"] == 1
    assert float(body["total_charges"]) == 1000.0
    assert float(body["insurance_estimate"]) == 760.0
    assert float(body["patient_estimate"]) == 240.0
    # PRINT-6: the deductible portion is no longer a hard-coded 0.00.
    assert float(body["estimated_deductible"]) == 50.0
    assert body["has_active_coverage"] is True

    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/transactions", params={"date": TODAY})
    _assert_pdf(r, f"transactions-{patient.id}-{TODAY}.pdf")
    # Defaults to today (in the office's timezone) when no date is sent.
    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/transactions")
    _assert_pdf(r, "-today.pdf")


def test_day_totals_without_charges(client, patient):
    r = client.get(f"{PREFIX}/patients/{patient.id}/day-totals", params={"date": "2001-01-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["transaction_count"] == 0
    assert float(body["estimated_deductible"]) == 0.0
    assert body["date"] == "2001-01-01"


def test_insurance_report_slot_resolution(client, db_session, patient, coverage):
    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/insurance", params={"category": "D", "order": "primary"})
    _assert_pdf(r, f"insurance-D-primary-{patient.id}.pdf")

    # No medical slot on file → a typed 404, not a blank report.
    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/insurance", params={"category": "M"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "insurance_slot_not_found"

    # Secondary dental: falls back positionally only when a second dental slot exists.
    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/insurance", params={"order": "secondary"})
    assert r.status_code == 404

    audit = _print_audits(db_session, patient.id)
    assert [a.resource_id for a in audit] == ["insurance"]
    assert audit[0].details["params"] == {"category": "D", "order": "primary"}


def test_reports_are_tenant_scoped(client, db_session, patient):
    other = Tenant(name="Other", code="other", is_active=True)
    db_session.add(other)
    db_session.commit()
    stranger = Patient(tenant_id=other.id, first_name="Not", last_name="Yours", is_active=True)
    db_session.add(stranger)
    db_session.commit()
    for report in ("overview", "ledger", "transactions", "insurance"):
        r = client.get(f"{PREFIX}/patients/{stranger.id}/reports/{report}")
        assert r.status_code == 404, report
    assert client.get(f"{PREFIX}/patients/{stranger.id}/day-totals").status_code == 404
    assert _print_audits(db_session, stranger.id) == []


def test_report_query_params_are_validated(client, patient):
    assert client.get(f"{PREFIX}/patients/{patient.id}/reports/ledger", params={"scope": "family"}).status_code == 422
    assert client.get(f"{PREFIX}/patients/{patient.id}/reports/insurance", params={"category": "X"}).status_code == 422
    assert client.get(f"{PREFIX}/patients/{patient.id}/reports/transactions", params={"date": "nope"}).status_code == 422


# ── PRINT-2: letterhead on OfficeRead + on the printed header ─────────────────
def test_office_read_letterhead_resolution(client, db_session, office, patient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    tid = db_session._tenant_id

    # Nothing configured: text-only letterhead from the office row.
    body = client.get(f"{PREFIX}/offices/{office.id}").json()
    assert body["logo_url"] is None
    assert body["letterhead"] == {
        "name": "Print Office", "address_line1": "1 Main St", "address_line2": None, "city": "Austin",
        "state": "TX", "zip": "78701", "phone": "512-555-0100", "logo_url": None, "logo_source": "none",
    }

    # Practice logo (Account Info) → logo_source=tenant.
    (tmp_path / "logos").mkdir()
    (tmp_path / "logos" / f"tenant_{tid}.png").write_bytes(_PNG)
    db_session.add(AccountSettings(tenant_id=tid, logo_url=f"/uploads/logos/tenant_{tid}.png"))
    db_session.commit()
    body = client.get(f"{PREFIX}/offices/{office.id}").json()
    assert body["logo_url"] == f"/uploads/logos/tenant_{tid}.png"
    assert body["letterhead"]["logo_source"] == "tenant"

    # Statement tab: custom logo + custom address + correspondence name win.
    (tmp_path / "office_logos").mkdir()
    (tmp_path / "office_logos" / f"office_{office.id}.png").write_bytes(_PNG)
    db_session.add(OfficeStatementSettings(
        tenant_id=tid, office_id=office.id, logo_option="custom",
        logo_url=f"/uploads/office_logos/office_{office.id}.png", address_source="custom",
        correspondence_name="Print Office Billing", statement_address_1="PO Box 9",
        statement_city="Dallas", statement_state="TX", statement_zip="75201", statement_phone="214-555-0100",
    ))
    db_session.commit()
    body = client.get(f"{PREFIX}/offices/{office.id}").json()
    assert body["logo_url"] == f"/uploads/office_logos/office_{office.id}.png"
    lh = body["letterhead"]
    assert lh["logo_source"] == "office"
    assert lh["name"] == "Print Office Billing"
    assert (lh["address_line1"], lh["city"], lh["state"], lh["zip"], lh["phone"]) == (
        "PO Box 9", "Dallas", "TX", "75201", "214-555-0100")
    # The list endpoint carries it too.
    listed = client.get(f"{PREFIX}/offices").json()["items"]
    assert listed[0]["letterhead"]["name"] == "Print Office Billing"

    # The PDF header embeds the resolved logo (the image branch must not fail).
    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/overview")
    _assert_pdf(r, "patient-overview")

    # Opting out removes the logo but keeps the text block.
    row = db_session.execute(select(OfficeStatementSettings).where(
        OfficeStatementSettings.office_id == office.id)).scalar_one()
    row.logo_option = "none"
    db_session.commit()
    body = client.get(f"{PREFIX}/offices/{office.id}").json()
    assert body["logo_url"] is None
    assert body["letterhead"]["logo_source"] == "none"
    assert body["letterhead"]["name"] == "Print Office Billing"


def test_letterhead_never_resolves_remote_logo_to_disk(db_session, office):
    from app.services.print_service import resolve_letterhead

    db_session.add(AccountSettings(tenant_id=db_session._tenant_id, logo_url="https://cdn.example/logo.png"))
    db_session.commit()
    lh = resolve_letterhead(db_session, office, db_session._tenant_id)
    assert lh["logo_url"] == "https://cdn.example/logo.png"
    assert lh["logo_source"] == "tenant"
    assert lh["logo_path"] is None


# ── PRINT-3: the feed cap ─────────────────────────────────────────────────────
def test_ledger_feed_accepts_larger_pages(client, patient):
    r = client.get(f"{PREFIX}/patients/{patient.id}/account-ledger", params={"size": 5000})
    assert r.status_code == 200, r.text
    assert r.json()["size"] == 5000
    r = client.get(f"{PREFIX}/patients/{patient.id}/ledger", params={"size": 5000})
    assert r.status_code == 200, r.text
    assert client.get(f"{PREFIX}/patients/{patient.id}/account-ledger", params={"size": 5001}).status_code == 422


# ── PRINT-10: patient photo embedded when it is a local image ─────────────────
def test_overview_embeds_local_patient_photo(client, db_session, patient, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    from app.db.models import PatientDocument
    from app.services.print_service import _photo_path

    (tmp_path / "photos").mkdir()
    (tmp_path / "photos" / "p.png").write_bytes(_PNG)
    doc = PatientDocument(tenant_id=db_session._tenant_id, patient_id=patient.id, document_type="PH",
                          file_name="p.png", content_type="image/png", file_path="photos/p.png",
                          file_url="/x", storage_backend="local")
    db_session.add(doc)
    db_session.flush()
    patient.photo_document_id = doc.id
    db_session.commit()
    assert Path(_photo_path(db_session, patient)) == tmp_path / "photos" / "p.png"

    r = client.get(f"{PREFIX}/patients/{patient.id}/reports/overview")
    _assert_pdf(r, "patient-overview")

    # A bucket-stored photo is skipped (no network fetch from a header decoration).
    doc.storage_backend = "gcs"
    db_session.commit()
    assert _photo_path(db_session, patient) is None
