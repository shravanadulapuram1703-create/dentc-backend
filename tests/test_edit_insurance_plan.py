"""Edit Insurance Plan from the patient screen — EDIT-PLAN-1 … EDIT-PLAN-9.

``docs/patient-insurance/edit_insurance_plan_backend_devreport.md``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import Request
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_user
from app.core.security import hash_password
from app.db.models import (
    InsuranceCarrier,
    InsuranceClaim,
    InsuranceCoverageRule,
    InsurancePlan,
    InsuranceSubscriber,
    Patient,
    PatientInsurance,
    Permission,
    User,
    UserGroup,
    UserGroupMembership,
    UserGroupRight,
)
from app.main import app
from app.services import audit_service
from app.services.permission_service import (
    INSURANCE_PLAN_EDIT_LOCKED,
    INSURANCE_PLAN_WRITE,
)

PREFIX = "/api/v1"
WRITE_CODE = INSURANCE_PLAN_WRITE[0]


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def carrier(db_session) -> InsuranceCarrier:
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental",
                         carrier_type="True", payer_id="PAY-1", is_active=True)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def plan(db_session, carrier) -> InsurancePlan:
    p = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                      group_number="GRP-100", individual_deductible=Decimal("0"),
                      individual_max=Decimal("1000"), is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _as(user: User):
    """Act as ``user``. The override also stamps the decoded-token payload the
    audit middleware keys on (the real dependency does it; the conftest
    override does not, which is why audit rows are absent from other suites)."""
    def _current(request: Request) -> User:
        request.state.token_payload = {"sub": str(user.id), "tenant_id": user.tenant_id}
        return user

    app.dependency_overrides[get_current_user] = _current


@pytest.fixture
def audit_to_test_db(monkeypatch, db_session):
    """The audit writer opens its own session on the app engine; point it at
    the in-memory test engine so ``/history`` can read what the middleware wrote."""
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    monkeypatch.setattr(audit_service, "SessionLocal", factory)
    _as(db_session._admin)
    return factory


def _patient(db_session, first: str, last: str) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name=first, last_name=last, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _link(db_session, patient: Patient, plan: InsurancePlan, slot="primary", ptype="D", active=True):
    row = PatientInsurance(patient_id=patient.id, ins_plan_id=plan.id, insurance_type=slot,
                           legacy_plan_type=ptype, is_active=active)
    db_session.add(row)
    db_session.commit()
    return row


def _subscriber(db_session, plan: InsurancePlan, group: str | None) -> InsuranceSubscriber:
    s = InsuranceSubscriber(tenant_id=db_session._tenant_id, ins_plan_id=plan.id,
                            sub_first_name="Sub", sub_last_name="Scriber",
                            group_number=group, is_active=True)
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _claim(db_session, patient: Patient, plan: InsurancePlan, cid: str, status: str, other=False):
    db_session.add(InsuranceClaim(
        id=cid, patient_id=patient.id, claim_number=cid, status=status, claim_type="primary",
        ins_plan_id=None if other else plan.id, other_ins_plan_id=plan.id if other else None,
        is_active=True,
    ))
    db_session.commit()


def _staff_user(db_session, username="staff") -> User:
    u = User(tenant_id=db_session._tenant_id, email=f"{username}@test.local", username=username,
             password_hash=hash_password("x" * 8), role="staff", is_active=True,
             first_name="Front", last_name="Desk")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _grant(db_session, user: User, *codes: str, group_name="Billing") -> UserGroup:
    """Put ``user`` in a group holding exactly ``codes`` (created as needed)."""
    group = UserGroup(tenant_id=db_session._tenant_id, name=group_name, is_active=True)
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    db_session.add(UserGroupMembership(tenant_id=db_session._tenant_id, user_id=user.id, group_id=group.id))
    for code in codes:
        perm = db_session.query(Permission).filter_by(code=code).one_or_none()
        if perm is None:
            perm = Permission(code=code, label=code, category="Setup", is_active=True)
            db_session.add(perm)
            db_session.commit()
            db_session.refresh(perm)
        db_session.add(UserGroupRight(tenant_id=db_session._tenant_id, group_id=group.id,
                                      permission_id=perm.id))
    db_session.commit()
    return group


def _proc(client, code="D1110"):
    r = client.post(f"{PREFIX}/procedure-codes", json={
        "code": code, "description": "Prophylaxis", "category": "Preventive", "default_fee": 100,
    })
    assert r.status_code == 201, r.text
    return code


def _tp(client, patient_id: int, tp_id: str, proc: str, fee=100) -> str:
    r = client.post(f"{PREFIX}/treatment-plans", json={"id": tp_id, "patient_id": patient_id, "name": tp_id})
    assert r.status_code == 201, r.text
    r = client.post(f"{PREFIX}/treatment-plan-items",
                    json={"id": f"{tp_id}-I1", "plan_id": tp_id, "procedure_code": proc, "fee": fee})
    assert r.status_code == 201, r.text
    return tp_id


# ── EDIT-PLAN-1: optimistic concurrency ──────────────────────────────────────
def test_stale_expected_updated_at_is_412_with_current_version(client, plan):
    first = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "v1"})
    assert first.status_code == 200, first.text
    read_version = first.json()["updated_at"]

    # A second editor saves; the first editor's copy is now stale.
    second = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"individual_max": "1500.00"})
    assert second.status_code == 200
    assert second.json()["updated_at"] != read_version

    stale = client.patch(f"{PREFIX}/insurance-plans/{plan.id}",
                         json={"plan_notes": "v2", "expected_updated_at": read_version})
    assert stale.status_code == 412, stale.text
    err = stale.json()["error"]
    assert err["code"] == "precondition_failed"
    assert err["details"]["precondition"] == "expected_updated_at"
    assert err["details"]["current"]["updated_at"] is not None
    assert err["details"]["current"]["etag"].startswith('W/"')
    # Nothing was written.
    assert client.get(f"{PREFIX}/insurance-plans/{plan.id}").json()["plan_notes"] == "v1"

    fresh = client.patch(f"{PREFIX}/insurance-plans/{plan.id}",
                         json={"plan_notes": "v2", "expected_updated_at": second.json()["updated_at"]})
    assert fresh.status_code == 200, fresh.text


def test_explicit_null_asserts_never_updated(client, plan):
    ok = client.patch(f"{PREFIX}/insurance-plans/{plan.id}",
                      json={"plan_notes": "first", "expected_updated_at": None})
    assert ok.status_code == 200, ok.text
    stale = client.patch(f"{PREFIX}/insurance-plans/{plan.id}",
                         json={"plan_notes": "second", "expected_updated_at": None})
    assert stale.status_code == 412


def test_if_match_etag_round_trip_and_if_unmodified_since(client, plan):
    got = client.get(f"{PREFIX}/insurance-plans/{plan.id}")
    etag = got.headers.get("etag")
    assert etag and etag.startswith('W/"')
    assert got.json()["version"] == etag[3:-1]

    ok = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "a"},
                      headers={"If-Match": etag})
    assert ok.status_code == 200, ok.text
    assert ok.headers.get("etag") != etag  # the version moved

    stale = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "b"},
                         headers={"If-Match": etag})
    assert stale.status_code == 412
    assert stale.json()["error"]["details"]["precondition"] == "if_match"

    long_ago = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    stale2 = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "c"},
                          headers={"If-Unmodified-Since": long_ago})
    assert stale2.status_code == 412
    assert stale2.json()["error"]["details"]["precondition"] == "if_unmodified_since"

    star = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "d"},
                        headers={"If-Match": "*"})
    assert star.status_code == 200


def test_coverage_put_honours_precondition_and_moves_plan_version(client, plan):
    before = client.get(f"{PREFIX}/insurance-plans/{plan.id}").json()
    r = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [{"start_code": "01", "category": "0", "coverage_pct": 100}],
        "expected_updated_at": before["updated_at"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["plan_updated_at"] is not None
    assert r.json()["version"]
    after = client.get(f"{PREFIX}/insurance-plans/{plan.id}").json()
    # A coverage write is a plan-document write: the plan's version moved.
    assert after["updated_at"] != before["updated_at"]

    stale = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [{"start_code": "02", "category": "0", "coverage_pct": 80}],
        "expected_updated_at": before["updated_at"],
    })
    assert stale.status_code == 412, stale.text
    # And the table is untouched.
    rules = client.get(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules").json()["rules"]
    assert [x["start_code"] for x in rules] == ["01"]


def test_single_rule_write_moves_the_plan_version(client, plan):
    before = client.get(f"{PREFIX}/insurance-plans/{plan.id}").json()["updated_at"]
    r = client.post(f"{PREFIX}/insurance-coverage-rules", json={
        "ins_plan_id": plan.id, "start_code": "03A", "end_code": "03A", "category": "0", "coverage_pct": 50,
    })
    assert r.status_code == 201, r.text
    after = client.get(f"{PREFIX}/insurance-plans/{plan.id}").json()["updated_at"]
    assert after != before


# ── EDIT-PLAN-2: usage ───────────────────────────────────────────────────────
def test_usage_counts_distinct_patients_open_claims_and_pending_plans(client, db_session, plan):
    a = _patient(db_session, "Ann", "A")
    b = _patient(db_session, "Bob", "B")
    c = _patient(db_session, "Cid", "C")
    _link(db_session, a, plan, "primary", "D")
    _link(db_session, a, plan, "secondary", "M")   # same patient, second slot
    _link(db_session, b, plan, "primary", "D")
    _link(db_session, c, plan, "primary", "D", active=False)  # inactive slot: not counted
    _subscriber(db_session, plan, "GRP-100")
    _claim(db_session, a, plan, "C-1", "submitted")
    _claim(db_session, a, plan, "C-2", "closed")
    _claim(db_session, b, plan, "C-3", "other", other=True)
    proc = _proc(client)
    _tp(client, a.id, "TP-A", proc)

    r = client.get(f"{PREFIX}/insurance-plans/{plan.id}/usage")
    assert r.status_code == 200, r.text
    u = r.json()
    assert u["patients"] == 2
    assert u["patient_links"] == 3
    assert u["subscribers"] == 1
    assert u["claims_total"] == 2
    assert u["claims_open"] == 1
    assert u["claims_by_status"] == {"submitted": 1, "closed": 1}
    assert u["claims_as_other_coverage"] == 1
    assert u["treatment_plans"] == 1
    assert u["treatment_plan_items_pending"] == 1
    assert u["shared"] is True
    assert u["last_used_at"] is not None


# ── EDIT-PLAN-3: the re-estimate cascade ─────────────────────────────────────
def test_affected_plans_and_re_estimate_cascade(client, db_session, plan):
    a = _patient(db_session, "Ann", "A")
    b = _patient(db_session, "Bob", "B")
    _link(db_session, a, plan)
    proc = _proc(client)
    _tp(client, a.id, "TP-A", proc)
    _tp(client, b.id, "TP-B", proc)  # uninsured patient — not affected

    listed = client.get(f"{PREFIX}/insurance-plans/{plan.id}/affected-treatment-plans")
    assert listed.status_code == 200, listed.text
    assert [x["id"] for x in listed.json()["items"]] == ["TP-A"]
    assert listed.json()["items"][0]["coverage_source"] == "active_slot"
    assert listed.json()["items"][0]["patient_name"] == "A, Ann"

    # The same set through the generic list filter.
    via_filter = client.get(f"{PREFIX}/treatment-plans", params={"ins_plan_id": plan.id})
    assert [x["id"] for x in via_filter.json()["items"]] == ["TP-A"]

    # Coverage change: 50 % on every code.
    put = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [{"start_code": "D0000", "end_code": "D9999", "coverage_pct": 50}],
    })
    assert put.status_code == 200, put.text

    dry = client.post(f"{PREFIX}/insurance-plans/{plan.id}/re-estimate", json={"dry_run": True})
    assert dry.status_code == 200, dry.text
    assert dry.json()["affected"] == 1
    assert dry.json()["treatment_plans"][0]["status"] == "planned"
    item = client.get(f"{PREFIX}/treatment-plan-items/TP-A-I1").json()
    assert Decimal(str(item["insurance_estimate"])) == Decimal("0")  # dry run wrote nothing

    run = client.post(f"{PREFIX}/insurance-plans/{plan.id}/re-estimate", json={})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["re_estimated"] == 1 and body["failed"] == 0
    line = body["treatment_plans"][0]
    assert Decimal(str(line["insurance_estimate_after"])) == Decimal("50.00")
    item = client.get(f"{PREFIX}/treatment-plan-items/TP-A-I1").json()
    assert Decimal(str(item["insurance_estimate"])) == Decimal("50.00")

    bad = client.post(f"{PREFIX}/insurance-plans/{plan.id}/re-estimate",
                      json={"treatment_plan_ids": ["TP-B"]})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "treatment_plan_not_affected"


# ── EDIT-PLAN-4: subscriber group number follows the plan when it still matched ──
def test_group_number_change_cascades_to_matching_subscribers_only(client, db_session, plan):
    follows = _subscriber(db_session, plan, "grp-100 ")   # equal after trim/case-fold
    blank = _subscriber(db_session, plan, None)
    card = _subscriber(db_session, plan, "GRP-100-PA")     # a per-card suffix: kept

    r = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"group_number": "GRP-200"})
    assert r.status_code == 200, r.text
    cascade = r.json()["group_number_cascade"]
    assert cascade["previous_group_number"] == "GRP-100"
    assert cascade["new_group_number"] == "GRP-200"
    assert cascade["subscribers_updated"] == 2
    assert cascade["subscribers_kept"] == 1
    assert cascade["kept_subscriber_ids"] == [card.id]

    for sid in (follows.id, blank.id):
        sub = client.get(f"{PREFIX}/insurance-subscribers/{sid}").json()
        assert sub["group_number"] == "GRP-200"
        assert sub["plan_group_number"] == "GRP-200"
        assert sub["group_number_matches_plan"] is True
    kept = client.get(f"{PREFIX}/insurance-subscribers/{card.id}").json()
    assert kept["group_number"] == "GRP-100-PA"
    assert kept["plan_group_number"] == "GRP-200"
    assert kept["group_number_matches_plan"] is False

    # A PATCH that does not touch the group number reports no cascade.
    r2 = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "x"})
    assert r2.json()["group_number_cascade"] is None


# ── EDIT-PLAN-5: effective permissions + the lock ────────────────────────────
def test_me_full_exposes_effective_permissions(client, db_session):
    db_session.add(Permission(code=WRITE_CODE, label="x", category="Setup", is_active=True))
    db_session.commit()
    me = client.get(f"{PREFIX}/auth/me-full").json()
    # super_admin: every active code, enforced.
    assert WRITE_CODE in me["permissions"]
    assert me["permissions_enforced"] is True

    staff = _staff_user(db_session)
    _as(staff)
    me = client.get(f"{PREFIX}/auth/me-full").json()
    assert me["permissions"] == [] and me["permissions_enforced"] is False and me["groups"] == []

    _grant(db_session, staff, WRITE_CODE)
    me = client.get(f"{PREFIX}/auth/me-full").json()
    assert me["permissions"] == [WRITE_CODE]
    assert me["permissions_enforced"] is True
    assert me["groups"] == ["Billing"]


def test_plan_writes_are_gated_for_grouped_users_only(client, db_session, plan):
    staff = _staff_user(db_session)
    _as(staff)
    # Ungated (no group): the legacy role-only behaviour — allowed.
    assert client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "a"}).status_code == 200

    # In a group without the right: refused, naming the codes that would satisfy it.
    _grant(db_session, staff, "reports_daily_reports_screen_view_only")
    denied = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "b"})
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "permission_denied"
    assert set(denied.json()["error"]["details"]["required_any_of"]) == set(INSURANCE_PLAN_WRITE)
    # Reads are never gated.
    assert client.get(f"{PREFIX}/insurance-plans/{plan.id}").status_code == 200
    # Nor is the coverage read; the coverage write is.
    assert client.get(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules").status_code == 200
    assert client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules",
                      json={"rules": []}).status_code == 403
    assert client.post(f"{PREFIX}/insurance-coverage-rules", json={
        "ins_plan_id": plan.id, "start_code": "01", "end_code": "01", "coverage_pct": 100,
    }).status_code == 403

    # With the patient-screen full-control right: allowed.
    _grant(db_session, staff, INSURANCE_PLAN_WRITE[1], group_name="Front Desk")
    assert client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "c"}).status_code == 200


def test_locked_plan_requires_the_edit_locked_right(client, db_session, plan):
    admin = db_session._admin
    lock = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"is_locked": True})
    assert lock.status_code == 200, lock.text
    assert lock.json()["is_locked"] is True
    assert lock.json()["locked_at"] is not None
    assert lock.json()["locked_by"] == admin.id

    staff = _staff_user(db_session)
    _grant(db_session, staff, WRITE_CODE)   # may edit plans, but not locked ones
    _as(staff)
    refused = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "x"})
    assert refused.status_code == 423, refused.text
    assert refused.json()["error"]["code"] == "plan_locked"
    assert refused.json()["error"]["details"]["required_any_of"] == [INSURANCE_PLAN_EDIT_LOCKED]
    # The coverage document and the per-row resources are locked with it.
    assert client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules",
                      json={"rules": []}).status_code == 423
    assert client.post(f"{PREFIX}/insurance-coverage-rules", json={
        "ins_plan_id": plan.id, "start_code": "01", "end_code": "01", "coverage_pct": 100,
    }).status_code == 423
    # Unlocking is itself a locked-plan edit.
    assert client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"is_locked": False}).status_code == 423
    # An ungated user does not get the lock right for free.
    loner = _staff_user(db_session, "loner")
    _as(loner)
    assert client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "y"}).status_code == 423

    # Holding the right: allowed; unlock clears the stamp.
    _grant(db_session, staff, INSURANCE_PLAN_EDIT_LOCKED, group_name="Managers")
    _as(staff)
    ok = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"plan_notes": "z", "is_locked": False})
    assert ok.status_code == 200, ok.text
    assert ok.json()["is_locked"] is False and ok.json()["locked_at"] is None

    # A locked plan cannot be created by someone without the right.
    plain = _staff_user(db_session, "plain")
    _grant(db_session, plain, WRITE_CODE, group_name="Plain")
    _as(plain)
    assert client.post(f"{PREFIX}/insurance-plans",
                       json={"carrier_id": plan.carrier_id, "is_locked": True}).status_code == 423


def test_metadata_publishes_permissions_defaults_and_concurrency(client):
    meta = client.get(f"{PREFIX}/insurance-plans/metadata").json()
    assert meta["permissions"]["write_any_of"] == list(INSURANCE_PLAN_WRITE)
    assert meta["permissions"]["edit_locked"] == INSURANCE_PLAN_EDIT_LOCKED
    assert meta["plan_field_defaults"]["fees_to_print"] == "office_ucr"
    assert meta["plan_field_defaults"]["lifetime_ortho_benefits"] is True
    assert meta["concurrency"]["body_field"] == "expected_updated_at"
    assert meta["concurrency"]["status_code"] == 412


# ── EDIT-PLAN-6: per-plan history ────────────────────────────────────────────
def test_history_aggregates_plan_rule_and_bulk_changes_with_names(client, db_session, plan, audit_to_test_db):
    admin = db_session._admin
    admin.first_name, admin.last_name = "Ada", "Admin"
    db_session.commit()

    assert client.patch(f"{PREFIX}/insurance-plans/{plan.id}",
                        json={"individual_max": "1500.00"}).status_code == 200
    put = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [{"start_code": "01", "category": "0", "description": "Diagnostic", "coverage_pct": 100},
                  {"start_code": "03A", "category": "0", "description": "Crowns", "coverage_pct": 50}],
        "frequency_groups": [{"code_group": "01", "freq_limit": 6}],
    })
    assert put.status_code == 200, put.text
    rule_id = put.json()["rules"][1]["id"]
    assert client.patch(f"{PREFIX}/insurance-coverage-rules/{rule_id}",
                        json={"coverage_pct": 60}).status_code == 200
    assert client.delete(f"{PREFIX}/insurance-coverage-rules/{rule_id}").status_code == 204

    r = client.get(f"{PREFIX}/insurance-plans/{plan.id}/history")
    assert r.status_code == 200, r.text
    body = r.json()
    sources = [e["source"] for e in body["items"]]
    # Newest first: the rule delete, the rule patch, the bulk PUT, the plan PATCH.
    assert sources == ["coverage_rule", "coverage_rule", "coverage_bulk", "plan"]
    assert all(e["user_name"] == "Ada Admin" for e in body["items"])

    plan_entry = body["items"][-1]
    assert plan_entry["after"]["individual_max"] == "1500.00"
    assert plan_entry["summary"] == "Updated plan: individual_max"

    bulk = body["items"][-2]
    actions = sorted(c["action"] for c in bulk["changes"])
    assert actions == ["create", "create", "create"]
    assert {c["resource_type"] for c in bulk["changes"]} == {
        "insurance-coverage-rules", "insurance-plan-frequency-groups"}
    assert bulk["summary"].startswith("Replaced coverage")

    patch_entry = body["items"][1]
    assert Decimal(patch_entry["before"]["coverage_pct"]) == Decimal("50")
    assert Decimal(patch_entry["after"]["coverage_pct"]) == Decimal("60")
    assert "coverage rule 03A" in patch_entry["summary"]
    # The deleted rule is no longer on the plan — found through the scope tag.
    delete_entry = body["items"][0]
    assert delete_entry["action"] == "DELETE" and delete_entry["resource_id"] == str(rule_id)

    # The "Modified by / on" strip.
    assert body["updated_by_name"] == "Ada Admin"
    assert body["updated_at"] is not None and body["version"]
    assert body["meta"]["total"] == 4


# ── EDIT-PLAN-8: unknown keys are refused ────────────────────────────────────
def test_unknown_plan_fields_are_422(client, plan, carrier):
    r = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"bogus_field": 1})
    assert r.status_code == 422, r.text
    r = client.post(f"{PREFIX}/insurance-plans", json={"carrier_id": carrier.id, "bogus": True})
    assert r.status_code == 422, r.text
    # The stamp columns are server-owned, so they count as unknown on a write.
    r = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={"locked_at": "2026-01-01T00:00:00Z"})
    assert r.status_code == 422


# ── EDIT-PLAN-9: NULL never leaks a phantom diff ─────────────────────────────
def test_first_edit_of_a_new_plan_audits_only_what_changed(client, db_session, plan, audit_to_test_db):
    # The fixture plan was inserted by the ORM with the model defaults, like a
    # backfilled migrated row; re-sending the defaults is a no-op.
    r = client.patch(f"{PREFIX}/insurance-plans/{plan.id}", json={
        "fees_to_print": "office_ucr", "claim_option": "submit", "form_to_print": "ADA2024",
        "network_type": "unknown", "plan_notes": "only this",
    })
    assert r.status_code == 200, r.text
    history = client.get(f"{PREFIX}/insurance-plans/{plan.id}/history").json()
    assert history["meta"]["total"] == 1
    assert set(history["items"][0]["after"]) == {"plan_notes"}
