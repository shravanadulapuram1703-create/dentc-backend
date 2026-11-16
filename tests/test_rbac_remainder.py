"""RBAC-6 remainder + PWD-RBAC-1..3.

RBAC-6: prescription strike-off, treatment-plan discount / edit-fee /
change-status-or-ids (field-scoped, on a *move* only), medical-history writes,
imaging capture, adjustment posting, progress-note add/edit.
PWD-RBAC: admin-only reset of *another* user's password, ``MeFull.
can_reset_user_passwords``, server-side complexity policy.
"""

from __future__ import annotations

from app.api.deps import get_current_user
from app.core import password_policy
from app.db.models import User
from app.main import app
from tests.test_access_rights_catalog import PREFIX, _as, _grant, _make_patient, _staff_user

STRONG = "Str0ng!Pass"


def _denied(r, code: str) -> None:
    assert r.status_code == 403, r.text
    assert code in r.json()["error"]["details"]["required_any_of"]


def _restore_admin(db_session) -> None:
    app.dependency_overrides.pop(get_current_user, None)


# ── RBAC-6: prescription strike-off ──────────────────────────────────────────
def test_prescription_strike_off_is_field_scoped(client, db_session):
    pid = _make_patient(client)
    rx = client.post(f"{PREFIX}/prescriptions", json={"patient_id": pid, "drug_name": "Ibuprofen 600"})
    assert rx.status_code == 201, rx.text
    rx_id = rx.json()["id"]

    staff = _staff_user(db_session)
    _as(staff)
    _grant(db_session, staff, "patient_prescription_screen_full_control")

    # A non-strike edit is not gated.
    assert client.patch(f"{PREFIX}/prescriptions/{rx_id}", json={"notes": "x"}).status_code == 200
    _denied(client.patch(f"{PREFIX}/prescriptions/{rx_id}", json={"is_active": False}),
            "patient_prescription_strike_off")
    _denied(client.delete(f"{PREFIX}/prescriptions/{rx_id}"), "patient_prescription_strike_off")

    _grant(db_session, staff, "patient_prescription_strike_off", group_name="Rx")
    ok = client.patch(f"{PREFIX}/prescriptions/{rx_id}", json={"is_active": False})
    assert ok.status_code == 200, ok.text
    assert ok.json()["is_active"] is False


# ── RBAC-6: treatment-plan item discount / fee / status ──────────────────────
def test_treatment_plan_item_fields_are_gated_on_a_move(client, db_session):
    pid = _make_patient(client)
    client.post(f"{PREFIX}/procedure-codes", json={
        "code": "D1110", "description": "Prophy", "category": "Preventive", "default_fee": 200})
    assert client.post(f"{PREFIX}/treatment-plans",
                       json={"id": "TP-R", "patient_id": pid, "name": "P"}).status_code == 201
    item = client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "I-R", "plan_id": "TP-R", "procedure_code": "D1110", "fee": 200,
        "status": "diagnosed"})
    assert item.status_code == 201, item.text

    staff = _staff_user(db_session)
    _as(staff)
    _grant(db_session, staff, "transactions_treatment_plan_screen_full_control")

    url = f"{PREFIX}/treatment-plan-items/I-R"
    # Re-sending the stored values (what the Edit Treatment form does) passes.
    same = client.patch(url, json={"fee": "200.00", "status": "diagnosed", "notes": "n"})
    assert same.status_code == 200, same.text
    _denied(client.patch(url, json={"fee": "150.00"}), "transactions_treatment_plan_edit_fee")
    _denied(client.patch(url, json={"discount": "10.00"}), "transactions_treatment_plan_discount")
    _denied(client.patch(url, json={"status": "accepted"}),
            "transactions_treatment_plan_change_status_or_ids")
    _denied(client.patch(url, json={"phase_id": 3}),
            "transactions_treatment_plan_change_status_or_ids")
    # A discount on a new item is applying a discount too.
    _denied(client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "I-R2", "plan_id": "TP-R", "procedure_code": "D1110", "fee": 200, "discount": 5}),
        "transactions_treatment_plan_discount")

    _grant(db_session, staff, "transactions_treatment_plan_edit_fee",
           "transactions_treatment_plan_discount",
           "transactions_treatment_plan_change_status_or_ids", group_name="TP")
    ok = client.patch(url, json={"fee": "150.00", "discount": "10.00", "status": "accepted"})
    assert ok.status_code == 200, ok.text


# ── RBAC-6: medical history / imaging / adjustments / progress notes ─────────
def test_route_level_write_gates(client, db_session):
    pid = _make_patient(client)
    staff = _staff_user(db_session)
    _as(staff)
    _grant(db_session, staff, "patient_medical_history_view_only")

    mh = "patient_medical_history_full_control"
    _denied(client.put(f"{PREFIX}/patients/{pid}/medical-history", json={}), mh)
    _denied(client.post(f"{PREFIX}/patients/{pid}/medical-history/copy-from/{pid}", json={}), mh)
    _denied(client.post(f"{PREFIX}/patients/{pid}/medical-history/sign", json={}), mh)
    _denied(client.post(f"{PREFIX}/patient-medical-alerts/bulk",
                        json={"patient_id": pid, "items": []}), mh)
    _denied(client.post(f"{PREFIX}/patient-questionnaire-responses/bulk",
                        json={"patient_id": pid, "items": []}), mh)
    _denied(client.post(f"{PREFIX}/patient-medical-alerts",
                        json={"patient_id": pid, "alert_code": "aspirin", "response": "yes"}), mh)
    # Reads stay open.
    assert client.get(f"{PREFIX}/patients/{pid}/medical-history").status_code == 200

    _denied(client.post(f"{PREFIX}/patients/{pid}/imaging/captures",
                        files={"file": ("a.png", b"\x89PNG", "image/png")}),
            "imaging_capture_acquire")
    _denied(client.post(f"{PREFIX}/patient-adjustments",
                        json={"id": "ADJ-R", "patient_id": pid, "amount": "5.00"}),
            "transactions_add_post_adjustments")
    _denied(client.post(f"{PREFIX}/progress-notes", json={"patient_id": pid, "notes": "hi"}),
            "patient_add_progress_notes")
    _denied(client.patch(f"{PREFIX}/progress-notes/1", json={"notes": "x"}),
            "patient_edit_progress_notes")


def test_ungated_user_still_falls_through(client, db_session):
    """B2: a non-admin in no group is never 403'd by these write gates."""
    pid = _make_patient(client)
    _as(_staff_user(db_session))
    r = client.put(f"{PREFIX}/patients/{pid}/medical-history", json={})
    assert r.status_code == 200, r.text


# ── PWD-RBAC-1/2 ─────────────────────────────────────────────────────────────
def test_admin_reset_rules(client, db_session):
    target = client.post(f"{PREFIX}/users/complete", json={
        "email": "t@example.com", "username": "target", "password": STRONG, "role": "staff"})
    assert target.status_code == 201, target.text
    tid = target.json()["id"]

    # Admin resets another user's password: OK (both admin write paths).
    assert client.put(f"{PREFIX}/users/{tid}/complete",
                      json={"password": "An0ther!Pass"}).status_code == 200
    assert client.patch(f"{PREFIX}/users/{tid}", json={"password": "Th1rd!Pass"}).status_code == 200

    # …but never their own password through the admin path.
    me = client.get(f"{PREFIX}/auth/me-full").json()
    assert me["can_reset_user_passwords"] is True
    my_id = me["user"]["id"]
    for r in (client.put(f"{PREFIX}/users/{my_id}/complete", json={"password": STRONG}),
              client.patch(f"{PREFIX}/users/{my_id}", json={"password": STRONG})):
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "own_password_self_service"
    # Editing your own non-password fields is still fine.
    assert client.put(f"{PREFIX}/users/{my_id}/complete",
                      json={"first_name": "Me"}).status_code == 200

    # A non-admin cannot reach the reset and is told so on me-full.
    staff = _staff_user(db_session)
    _as(staff)
    assert client.get(f"{PREFIX}/auth/me-full").json()["can_reset_user_passwords"] is False
    assert client.put(f"{PREFIX}/users/{tid}/complete",
                      json={"password": STRONG}).status_code == 403


def test_assert_can_set_password_refuses_non_admin_actor(db_session):
    """The rule itself, independent of the route's role gate."""
    import pytest

    from app.core.exceptions import ForbiddenError
    from app.services.user_admin_service import assert_can_set_password

    staff = _staff_user(db_session, username="s2")
    other = _staff_user(db_session, username="s3")
    with pytest.raises(ForbiddenError) as exc:
        assert_can_set_password(db_session, staff.id, other.id)
    assert exc.value.code == "password_reset_not_permitted"
    assert_can_set_password(db_session, None, other.id)  # actorless/internal passes


# ── PWD-RBAC-3 ───────────────────────────────────────────────────────────────
def test_password_policy(client, db_session):
    assert password_policy.failed_rules("weakpass") == ["uppercase", "number", "symbol"]
    assert password_policy.failed_rules(STRONG) == []

    pol = client.get(f"{PREFIX}/auth/password-policy").json()
    assert pol["min_length"] == 8 and [r["code"] for r in pol["rules"]][0] == "min_length"

    weak = client.post(f"{PREFIX}/users/complete", json={
        "email": "w@example.com", "username": "weak", "password": "weakpass1", "role": "staff"})
    assert weak.status_code == 422, weak.text
    err = weak.json()["error"]
    assert err["code"] == "password_too_weak"
    assert err["details"]["failed_rules"] == ["uppercase", "symbol"]

    assert client.post(f"{PREFIX}/users", json={
        "email": "w2@example.com", "username": "weak2", "password": "weakpass1",
        "role": "staff"}).status_code == 422

    # Self-service change: current password verified first, then the policy.
    u = User(tenant_id=db_session._tenant_id, email="cp@test.local", username="cp",
             password_hash=__import__("app.core.security", fromlist=["x"]).hash_password(STRONG),
             role="staff", is_active=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    _as(u)
    r = client.post(f"{PREFIX}/users/me/change-password",
                    json={"current_password": STRONG, "new_password": "alllowercase"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "password_too_weak"
    assert client.post(f"{PREFIX}/users/me/change-password",
                       json={"current_password": STRONG,
                             "new_password": "N3w!Password"}).status_code == 204
