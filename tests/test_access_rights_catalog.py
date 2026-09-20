"""ACCESS-RIGHTS handover: catalog curation (A1/A2/A3 + C2), B1 resolution, C1 gates.

The curation *data* is asserted against the handover files so the module can never
silently drift from what the frontend shipped; the curation *behaviour* and the
server-side enforcement are exercised end-to-end.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import Request
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.core.security import hash_password
from app.db.models import (
    Permission,
    User,
    UserGroup,
    UserGroupMembership,
    UserGroupRight,
)
from app.main import app
from app.services import access_rights_catalog as arc
from scripts.seed_permissions import categorize, parse_groups_file, slugify

PREFIX = "/api/v1"
_HANDOVER = Path(__file__).resolve().parent.parent / "docs" / "setup" / "implement" / "handover"


# ── helpers (mirrors of the edit-insurance-plan suite) ───────────────────────
def _as(user: User) -> None:
    def _current(request: Request) -> User:
        request.state.token_payload = {"sub": str(user.id), "tenant_id": user.tenant_id}
        return user

    app.dependency_overrides[get_current_user] = _current


def _staff_user(db_session, username="staff") -> User:
    u = User(tenant_id=db_session._tenant_id, email=f"{username}@test.local", username=username,
             password_hash=hash_password("x" * 8), role="staff", is_active=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _grant(db_session, user: User, *codes: str, group_name="Front Desk") -> UserGroup:
    """Put ``user`` in a group holding exactly ``codes`` (perms created as needed)."""
    group = UserGroup(tenant_id=db_session._tenant_id, name=group_name, is_active=True)
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    db_session.add(UserGroupMembership(tenant_id=db_session._tenant_id, user_id=user.id,
                                       group_id=group.id))
    for code in codes:
        perm = db_session.query(Permission).filter_by(code=code).one_or_none()
        if perm is None:
            perm = Permission(code=code, label=code, category="Test", is_active=True)
            db_session.add(perm)
            db_session.commit()
            db_session.refresh(perm)
        db_session.add(UserGroupRight(tenant_id=db_session._tenant_id, group_id=group.id,
                                      permission_id=perm.id))
    db_session.commit()
    return group


def _make_patient(client) -> int:
    r = client.post(f"{PREFIX}/patients", json={"first_name": "Del", "last_name": "Ete"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _make_procedure(client, db_session, patient_id: int, fee=100) -> str:
    from app.db.models import Office, Provider
    office = Office(tenant_id=db_session._tenant_id, name="Main", office_code="MAIN", is_active=True)
    db_session.add(office)
    db_session.commit()
    db_session.refresh(office)
    prov = Provider(id="PRV-RBAC", tenant_id=db_session._tenant_id, office_id=office.id,
                    name="Dr Fee", short_id="FEE")
    db_session.add(prov)
    db_session.commit()
    client.post(f"{PREFIX}/procedure-codes",
                json={"code": "D2750", "description": "Crown", "category": "Restorative",
                      "default_fee": fee})
    r = client.post(f"{PREFIX}/patient-procedures", json={
        "id": "PP-RBAC-1", "patient_id": patient_id, "office_id": office.id,
        "provider_id": prov.id, "procedure_code": "D2750",
        "fee": fee, "date_of_service": "2026-09-13"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── A: the curation data matches the handover files exactly ──────────────────
def _read_codes(name: str) -> list[str]:
    out = []
    for line in (_HANDOVER / name).read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        out.append(line.split("\t")[0].strip())
    return out


def test_curation_data_matches_handover_files():
    remove = set(_read_codes("REMOVE_codes.txt"))
    keep = set(_read_codes("KEEP_codes.txt"))
    add = json.loads((_HANDOVER / "ADD_rights.json").read_text(encoding="utf-8"))
    add_codes = {d["code"] for d in add}

    assert len(remove) == 210 and arc.REMOVED_CODES == remove
    assert len(add) == 44 and arc.ADDED_CODES == add_codes
    # the added rows carry the handover's label + category verbatim
    by_code = {r["code"]: r for r in arc.ADDED_RIGHTS}
    for d in add:
        assert by_code[d["code"]]["label"] == d["label"]
        assert by_code[d["code"]]["category"] == d["category"]
    # no code is both removed and added / kept
    assert not (arc.REMOVED_CODES & arc.ADDED_CODES)
    assert not (arc.REMOVED_CODES & arc.ADDED_CODES & keep)
    # 319 kept + 44 added = the promised 363
    assert len(keep) + len(add) == arc.CURATED_TOTAL == 363
    # every rename targets a kept code (label change only, code preserved)
    assert {c for c, _, _ in arc.RENAMES} <= keep


def test_removed_rows_are_faithful_to_the_seeded_catalog():
    """The stored (label, category) restored on downgrade match what the seeder
    would have written from Groups.txt — so a downgrade is a true restore."""
    groups = parse_groups_file()
    label_by_code = {}
    for _, _, rights in groups:
        for label in rights:
            label_by_code.setdefault(slugify(label), label)
    for code, label, category in arc.REMOVED_ROWS:
        assert label_by_code[code] == label
        assert categorize(label) == category


# ── A1/A2/A3 + C2: apply_curation against a seeded catalog ────────────────────
@pytest.fixture
def seeded_catalog(db_session):
    """The full 529-row legacy catalog, exactly as the seeder builds it."""
    groups = parse_groups_file()
    labels: dict[str, str] = {}
    for _, _, rights in groups:
        for label in rights:
            labels.setdefault(slugify(label), label)
    db_session.add_all([
        Permission(code=c, label=lab, category=categorize(lab), is_active=True)
        for c, lab in labels.items()
    ])
    db_session.commit()
    return labels


def test_apply_curation_lands_on_363_and_cascades(client, db_session, seeded_catalog):
    assert db_session.scalar(select(func.count()).select_from(Permission)) == 529

    # a group holding a to-be-removed right and a to-be-kept right (C2 setup)
    group = UserGroup(tenant_id=db_session._tenant_id, name="Legacy", is_active=True)
    db_session.add(group)
    db_session.commit()
    dead = next(iter(arc.REMOVED_CODES))
    kept = "appointments_add_new_appointment"
    for code in (dead, kept):
        pid = db_session.scalar(select(Permission.id).where(Permission.code == code))
        db_session.add(UserGroupRight(tenant_id=db_session._tenant_id, group_id=group.id,
                                      permission_id=pid))
    db_session.commit()

    report = arc.apply_curation(db_session)
    assert report == {"permissions_removed": 210, "group_rights_cascaded": 1,
                      "added": 44, "reactivated": 0, "renamed": 4}

    # A1: catalog is exactly the curated set, served by the endpoint.
    rows = client.get(f"{PREFIX}/permissions").json()
    codes = {r["code"] for r in rows}
    assert len(rows) == 363
    assert not (codes & arc.REMOVED_CODES)          # A1
    assert arc.ADDED_CODES <= codes                 # A2
    # A2: the five new categories are present.
    cats = {r["category"] for r in rows}
    assert {"Charting", "Imaging", "AppointNow", "Messaging", "Dashboard"} <= cats
    # A3: rename applied.
    hub = next(r for r in rows if r["code"] == "patient_messaging_hub_view_only")
    assert hub["label"] == "Patient - SMS / Communication View Only"

    # C2: the dead code's group assignment is gone; the kept one survives.
    remaining = {
        db_session.scalar(select(Permission.code).where(Permission.id == r.permission_id))
        for r in db_session.query(UserGroupRight).filter_by(group_id=group.id)
    }
    assert remaining == {kept}

    # idempotent: a second pass changes nothing.
    assert arc.apply_curation(db_session) == {"permissions_removed": 0, "group_rights_cascaded": 0,
                                              "added": 0, "reactivated": 0, "renamed": 0}
    assert db_session.scalar(select(func.count()).select_from(Permission)) == 363


def test_revert_curation_restores_the_catalog(db_session, seeded_catalog):
    arc.apply_curation(db_session)
    arc.revert_curation(db_session)
    total = db_session.scalar(select(func.count()).select_from(Permission))
    assert total == 529
    assert db_session.scalar(
        select(func.count()).select_from(Permission).where(Permission.code.in_(arc.ADDED_CODES))
    ) == 0
    label = db_session.scalar(
        select(Permission.label).where(Permission.code == "patient_messaging_hub_view_only")
    )
    assert label == "Patient - Messaging Hub View Only"  # A3 rename reverted


# ── B1: me-full.permissions = union of the user's group rights ────────────────
def test_me_full_is_union_of_group_rights_with_super_admin_bypass(client, db_session):
    db_session.add(Permission(code="patient_add_progress_notes", label="x",
                              category="Patient", is_active=True))
    db_session.commit()

    # super_admin (the seeded client user): every active code, enforced.
    me = client.get(f"{PREFIX}/auth/me-full").json()
    assert me["permissions_enforced"] is True
    assert "patient_add_progress_notes" in me["permissions"]

    # a fresh staff user in no group: ungated (legacy role-only behaviour).
    staff = _staff_user(db_session)
    _as(staff)
    me = client.get(f"{PREFIX}/auth/me-full").json()
    assert me["permissions"] == [] and me["permissions_enforced"] is False and me["groups"] == []

    # once grouped: exactly the union of the group's right codes.
    _grant(db_session, staff, "patient_add_progress_notes",
           "reports_daily_reports_screen_view_only")
    me = client.get(f"{PREFIX}/auth/me-full").json()
    assert set(me["permissions"]) == {"patient_add_progress_notes",
                                      "reports_daily_reports_screen_view_only"}
    assert me["permissions_enforced"] is True and me["groups"] == ["Front Desk"]


# ── C1: server-side enforcement (403) on the gated endpoints ──────────────────
def test_delete_patient_is_gated_only_for_grouped_users(client, db_session):
    pid = _make_patient(client)
    staff = _staff_user(db_session)
    _as(staff)

    # Ungated (no group): legacy role-only behaviour — the delete goes through.
    assert client.delete(f"{PREFIX}/patients/{pid}").status_code == 204

    # In a group WITHOUT the delete right: refused, naming the right.
    pid2 = None
    _as(db_session._admin)
    pid2 = _make_patient(client)
    _as(staff)
    _grant(db_session, staff, "reports_daily_reports_screen_view_only")
    denied = client.delete(f"{PREFIX}/patients/{pid2}")
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "permission_denied"
    assert denied.json()["error"]["details"]["required_any_of"] == ["patient_delete_patient_information"]

    # create/update are NOT gated by the delete right — only DELETE is.
    assert client.patch(f"{PREFIX}/patients/{pid2}", json={"first_name": "Still"}).status_code == 200

    # With the delete right (added to the same user via a second group): allowed.
    _grant(db_session, staff, "patient_delete_patient_information", group_name="Managers")
    assert client.delete(f"{PREFIX}/patients/{pid2}").status_code == 204


def test_supplemental_routes_are_gated(client, db_session):
    """The post-to-ledger and AppointNow approve/decline dependencies run before
    the handler, so a grouped user lacking the right is 403 even on a missing id."""
    staff = _staff_user(db_session)
    _as(staff)
    _grant(db_session, staff, "reports_daily_reports_screen_view_only")

    r = client.post(f"{PREFIX}/treatment-plan-items/nope/post", json={})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == \
        ["transactions_treatment_plan_post_to_ledger"]

    r = client.post(f"{PREFIX}/appointnow/requests/nope/approve", json={})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["appointnow_approve_booking"]

    r = client.post(f"{PREFIX}/appointnow/requests/nope/decline", json={})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["appointnow_decline_booking"]


# ── RBAC-1/3: a *_view_only right grants read; writes stay admin-only ─────────
def test_view_only_right_grants_users_list_read(client, db_session):
    staff = _staff_user(db_session)
    _as(staff)

    # Ungated staff: the users list was admin-only, and stays refused (403) —
    # the read rule does NOT fall through to ungated the way writes do.
    assert client.get(f"{PREFIX}/users").status_code == 403

    # Grouped but without the view right: still refused.
    _grant(db_session, staff, "reports_daily_reports_screen_view_only")
    assert client.get(f"{PREFIX}/users").status_code == 403

    # Holding the screen's view-only right: the list reads (RBAC-3).
    _grant(db_session, staff, "setup_security_users_screen_view_only", group_name="QA View")
    r = client.get(f"{PREFIX}/users")
    assert r.status_code == 200, r.text
    assert r.json()["meta"]["total"] >= 1  # at least the seeded admin
    # …but a write still requires admin — view-only does not grant it.
    created = client.post(f"{PREFIX}/users", json={
        "email": "x@test.local", "username": "xx", "password": "pw123456"})
    assert created.status_code == 403


def test_view_only_right_grants_group_rights_read(client, db_session):
    group = UserGroup(tenant_id=db_session._tenant_id, name="Some Group", is_active=True)
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)

    staff = _staff_user(db_session)
    _as(staff)
    # Without the groups view right: RBAC-2 was a 403 on the rights panel.
    assert client.get(f"{PREFIX}/user-groups/{group.id}/rights").status_code == 403

    _grant(db_session, staff, "setup_security_groups_screen_view_only")
    r = client.get(f"{PREFIX}/user-groups/{group.id}/rights")
    assert r.status_code == 200, r.text
    assert r.json() == []


# ── RBAC-5: patient-procedure DELETE gated on transactions_delete_procedure ───
def test_delete_procedure_is_gated(client, db_session):
    staff = _staff_user(db_session)
    _as(staff)
    _grant(db_session, staff, "reports_daily_reports_screen_view_only")
    # The delete dependency runs before the handler, so a missing id still 403s.
    r = client.delete(f"{PREFIX}/patient-procedures/nope")
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["transactions_delete_procedure"]


# ── RBAC-4: editing a charge's fee is gated, but only when the fee moves ──────
def test_fee_edit_is_field_scoped(client, db_session):
    pid = _make_patient(client)
    proc_id = _make_procedure(client, db_session, pid, fee=100)

    staff = _staff_user(db_session)
    _as(staff)
    _grant(db_session, staff, "reports_daily_reports_screen_view_only")

    # A non-fee edit is not gated by the fee right.
    assert client.patch(f"{PREFIX}/patient-procedures/{proc_id}",
                        json={"tooth": "3"}).status_code == 200
    # Changing the fee without the right: 403.
    denied = client.patch(f"{PREFIX}/patient-procedures/{proc_id}", json={"fee": "250.00"})
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["details"]["required_any_of"] == ["transactions_edit_fee_ledger"]
    # Re-sending the same fee (no move) is not gated.
    assert client.patch(f"{PREFIX}/patient-procedures/{proc_id}",
                        json={"fee": "100.00"}).status_code == 200
    # With the right: the fee change goes through.
    _grant(db_session, staff, "transactions_edit_fee_ledger", group_name="Fee Editors")
    ok = client.patch(f"{PREFIX}/patient-procedures/{proc_id}", json={"fee": "250.00"})
    assert ok.status_code == 200, ok.text
    assert str(ok.json()["fee"]) in ("250.0", "250.00")


# ── RBAC-6: extended write coverage ──────────────────────────────────────────
def test_rbac6_write_gates(client, db_session):
    staff = _staff_user(db_session)
    _as(staff)
    _grant(db_session, staff, "reports_daily_reports_screen_view_only")

    # patient-payments POST → transactions_add_post_patient_payments
    r = client.post(f"{PREFIX}/patient-payments",
                    json={"id": "PAY-1", "patient_id": 1, "amount": "50.00"})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["transactions_add_post_patient_payments"]

    # perio-exams POST → charting_perio_full_control
    r = client.post(f"{PREFIX}/perio-exams", json={"patient_id": 1, "exam_date": "2026-09-13"})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["charting_perio_full_control"]

    # perio bulk-details PUT → charting_perio_full_control (dependency before handler)
    r = client.put(f"{PREFIX}/perio-exams/1/details", json={"items": []})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["charting_perio_full_control"]

    # treatment-plans DELETE → transactions_treatment_plan_delete
    r = client.delete(f"{PREFIX}/treatment-plans/nope")
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["transactions_treatment_plan_delete"]

    # insurance payment POST → transactions_add_post_insurance_payments
    r = client.post(f"{PREFIX}/ledger-insurance-details/payment",
                    json={"claim_id": "nope", "procedure_id": "nope", "primary_ins_paid": "10.00"})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["required_any_of"] == ["transactions_add_post_insurance_payments"]
