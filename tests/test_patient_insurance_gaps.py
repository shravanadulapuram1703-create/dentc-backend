"""Patient-insurance consolidated dev-report gaps INS-PT-7..21.

INS-PT-1..6 are covered by ``tests/test_patient_insurance_module.py``. The gaps
here are the second pass: server-side duplicate authority, the per-field and
partial plan searches, batch id lookup, plan audit metadata and the Dental /
Medical discriminator.

INS-PT-15 (group-number backfill) and INS-PT-10 (the ``claim_type`` catalog) are
data tasks — ``scripts/backfill_insurance_source_fields.py`` and
``scripts/seed_account_definitions.py`` own them; INS-PT-17 is frontend routing.
"""

from __future__ import annotations

import pytest

from app.db.models import Employer, InsuranceCarrier, InsurancePlan

PREFIX = "/api/v1"


@pytest.fixture
def carrier(db_session) -> InsuranceCarrier:
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental",
                         carrier_type="True", payer_id="PAY-100", is_active=True)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


@pytest.fixture
def employer(db_session) -> Employer:
    e = Employer(tenant_id=db_session._tenant_id, name="Globex")
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    return e


def _plan(db_session, carrier, **kw) -> InsurancePlan:
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                         is_active=True, **kw)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


# ── INS-PT-19: the server is the duplicate authority ─────────────────────────
def test_duplicate_group_on_same_carrier_is_409(client, carrier):
    first = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-1000",
    })
    assert first.status_code == 201, first.text

    dup = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-1000",
    })
    assert dup.status_code == 409, dup.text
    err = dup.json()["error"]
    assert err["code"] == "duplicate_plan_group"
    # The dialog names the plan the user could adopt instead of the id alone.
    assert err["details"]["matches"][0]["id"] == first.json()["id"]
    assert err["details"]["matches"][0]["carrier_name"] == "Acme Dental"
    assert err["details"]["override_field"] == "allow_duplicate_group"


def test_duplicate_group_match_is_case_and_space_insensitive(client, carrier):
    assert client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "grp-2000",
    }).status_code == 201
    assert client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "  GRP-2000 ",
    }).status_code == 409


def test_duplicate_group_override_is_accepted(client, carrier):
    """Not a hard refusal: two offices can legitimately hold separate plans on
    one group, and legacy allows it — the server refuses the *accidental* one."""
    assert client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-3000",
    }).status_code == 201
    r = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-3000",
        "allow_duplicate_group": True,
    })
    assert r.status_code == 201, r.text


def test_duplicate_group_under_another_carrier_is_allowed(client, db_session, carrier):
    other = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Beta Dental",
                             carrier_type="True", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    assert client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "SHARED-1",
    }).status_code == 201
    # A group number identifies an employer group *to a carrier*; two carriers
    # reusing the digits is not a collision.
    assert client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": other.id, "group_number": "SHARED-1",
    }).status_code == 201


def test_blank_group_number_never_collides(client, carrier):
    """Every migrated plan is NULL (INS-PT-15) — "no group number" is not a
    duplicate of "no group number"."""
    blank = {"carrier_id": carrier.id}
    assert client.post(f"{PREFIX}/insurance-plans", json=blank).status_code == 201
    assert client.post(f"{PREFIX}/insurance-plans", json=blank).status_code == 201


def test_update_onto_taken_group_is_409_but_self_is_fine(client, carrier):
    keeper = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-4000",
    }).json()
    mover = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-4001",
    }).json()

    clash = client.patch(f"{PREFIX}/insurance-plans/{mover['id']}",
                         json={"group_number": "GRP-4000"})
    assert clash.status_code == 409

    # Re-saving a plan on its own group number must not conflict with itself.
    same = client.patch(f"{PREFIX}/insurance-plans/{keeper['id']}",
                        json={"group_number": "GRP-4000", "plan_type": "PPO"})
    assert same.status_code == 200, same.text


def test_existing_duplicate_stays_editable(client, db_session, carrier):
    """Backfilling the migrated group numbers (INS-PT-15) put 3,609 groups into a
    legitimate pre-existing collision. The guard fires on a *move*, not on the
    stored state, so repairing the data does not lock those plans."""
    a = _plan(db_session, carrier, group_number="GRP-DUP")
    _plan(db_session, carrier, group_number="GRP-DUP")

    edited = client.patch(f"{PREFIX}/insurance-plans/{a.id}", json={"plan_type": "PPO"})
    assert edited.status_code == 200, edited.text
    # Moving it onto a *different* taken group is still refused.
    _plan(db_session, carrier, group_number="GRP-TAKEN")
    assert client.patch(f"{PREFIX}/insurance-plans/{a.id}",
                        json={"group_number": "GRP-TAKEN"}).status_code == 409


def test_update_with_partial_payload_is_checked_against_stored_carrier(client, carrier):
    """A PATCH carrying only the group number is still evaluated against the
    plan's stored carrier — the merge, not the payload alone."""
    client.post(f"{PREFIX}/insurance-plans",
                json={"carrier_id": carrier.id, "group_number": "GRP-5000"})
    mover = client.post(f"{PREFIX}/insurance-plans",
                        json={"carrier_id": carrier.id, "group_number": "GRP-5001"}).json()
    assert client.patch(f"{PREFIX}/insurance-plans/{mover['id']}",
                        json={"group_number": "GRP-5000"}).status_code == 409


# ── INS-PT-21: a deactivated plan does not block the number ──────────────────
def test_soft_deleted_plan_does_not_block_but_is_reported(client, carrier):
    retired = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-6000",
    }).json()
    assert client.delete(f"{PREFIX}/insurance-plans/{retired['id']}").status_code == 204

    assert client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-6000",
    }).status_code == 201

    probe = client.get(f"{PREFIX}/insurance-plans/group-availability",
                       params={"group_number": "GRP-6000", "carrier_id": carrier.id}).json()
    assert [m["id"] for m in probe["inactive_matches"]] == [retired["id"]]


# ── INS-PT-20: the cheap "is this group taken" probe ─────────────────────────
def test_group_availability(client, carrier):
    free = client.get(f"{PREFIX}/insurance-plans/group-availability",
                      params={"group_number": "GRP-7000", "carrier_id": carrier.id})
    assert free.status_code == 200
    assert free.json()["taken"] is False

    plan = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-7000",
    }).json()

    taken = client.get(f"{PREFIX}/insurance-plans/group-availability",
                       params={"group_number": "GRP-7000", "carrier_id": carrier.id}).json()
    assert taken["taken"] is True
    assert [m["id"] for m in taken["matches"]] == [plan["id"]]

    # The plan being edited excludes itself, mirroring the save-path guard.
    excluded = client.get(f"{PREFIX}/insurance-plans/group-availability",
                          params={"group_number": "GRP-7000", "carrier_id": carrier.id,
                                  "exclude_plan_id": plan["id"]}).json()
    assert excluded["taken"] is False


def test_group_availability_without_carrier_is_tenant_wide(client, db_session, carrier):
    other = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Gamma", is_active=True)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    client.post(f"{PREFIX}/insurance-plans",
                json={"carrier_id": other.id, "group_number": "GRP-8000"})

    body = client.get(f"{PREFIX}/insurance-plans/group-availability",
                      params={"group_number": "GRP-8000"}).json()
    assert body["taken"] is True
    assert body["other_carrier_matches"] == []


# ── INS-PT-14: partial group-number match ────────────────────────────────────
def test_group_number_partial_filters(client, carrier):
    for group in ("ABC-1234", "XYZ-1234", "ABC-9999"):
        client.post(f"{PREFIX}/insurance-plans",
                    json={"carrier_id": carrier.id, "group_number": group})

    contains = client.get(f"{PREFIX}/insurance-plans",
                          params={"group_number_contains": "1234"}).json()
    assert contains["meta"]["total"] == 2

    starts = client.get(f"{PREFIX}/insurance-plans",
                        params={"group_number_startswith": "ABC"}).json()
    assert starts["meta"]["total"] == 2

    # The exact filter still means exact.
    exact = client.get(f"{PREFIX}/insurance-plans",
                       params={"group_number": "1234"}).json()
    assert exact["meta"]["total"] == 0


def test_group_number_partial_escapes_wildcards(client, carrier):
    client.post(f"{PREFIX}/insurance-plans",
                json={"carrier_id": carrier.id, "group_number": "PLAIN-1"})
    # '%' must search for itself, not match everything.
    body = client.get(f"{PREFIX}/insurance-plans",
                      params={"group_number_contains": "%"}).json()
    assert body["meta"]["total"] == 0


# ── INS-PT-7: per-field plan search ──────────────────────────────────────────
def test_carrier_name_and_payer_id_are_separate_searches(client, db_session, carrier):
    numeric = InsuranceCarrier(tenant_id=db_session._tenant_id, name="12345 Dental",
                               payer_id="ZZ-9", is_active=True)
    db_session.add(numeric)
    db_session.commit()
    db_session.refresh(numeric)

    client.post(f"{PREFIX}/insurance-plans",
                json={"carrier_id": carrier.id, "group_number": "12345"})
    client.post(f"{PREFIX}/insurance-plans",
                json={"carrier_id": numeric.id, "group_number": "OTHER"})

    # Free-text search spans group + carrier name + payer id, so it matches both.
    assert client.get(f"{PREFIX}/insurance-plans",
                      params={"search": "12345"}).json()["meta"]["total"] == 2
    # The named field reaches exactly one column.
    by_name = client.get(f"{PREFIX}/insurance-plans",
                         params={"carrier_name": "12345"}).json()
    assert by_name["meta"]["total"] == 1
    assert by_name["items"][0]["group_number"] == "OTHER"

    by_payer = client.get(f"{PREFIX}/insurance-plans", params={"payer_id": "PAY-100"}).json()
    assert by_payer["meta"]["total"] == 1
    assert by_payer["items"][0]["group_number"] == "12345"


# ── INS-PT-9/18: names on the plan read + batch id lookup ────────────────────
def test_plan_read_carries_carrier_and_employer_names(client, carrier, employer):
    created = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "employer_id": employer.id, "group_number": "GRP-NAME",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["carrier_name"] == "Acme Dental"
    assert body["employer_name"] == "Globex"
    assert body["payer_id"] == "PAY-100"
    # The Dental/Medical selector is re-derived from the carrier, so the plan
    # form no longer fetches the carrier just to preselect its first field.
    assert body["is_dental"] is True

    listed = client.get(f"{PREFIX}/insurance-plans").json()["items"][0]
    assert listed["carrier_name"] == "Acme Dental"
    assert listed["employer_name"] == "Globex"


def test_batch_id_lookup_on_carriers_and_employers(client, db_session, carrier, employer):
    second = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Delta", is_active=True)
    third = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Epsilon", is_active=True)
    db_session.add_all([second, third])
    db_session.commit()
    db_session.refresh(second)
    db_session.refresh(third)

    body = client.get(f"{PREFIX}/insurance-carriers",
                      params={"ids": f"{carrier.id},{third.id}"}).json()
    assert {c["id"] for c in body["items"]} == {carrier.id, third.id}

    emps = client.get(f"{PREFIX}/employers", params={"ids": str(employer.id)}).json()
    assert [e["id"] for e in emps["items"]] == [employer.id]

    # A junk id is dropped rather than 422'ing the whole grid page.
    mixed = client.get(f"{PREFIX}/insurance-carriers",
                       params={"ids": f"{carrier.id},abc,"}).json()
    assert [c["id"] for c in mixed["items"]] == [carrier.id]


# ── INS-PT-8: plan created/modified metadata ─────────────────────────────────
def test_plan_carries_modified_metadata(client, carrier):
    created = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-AUDIT",
    }).json()
    assert created["updated_at"] is None  # never edited yet

    updated = client.patch(f"{PREFIX}/insurance-plans/{created['id']}",
                           json={"plan_type": "PPO"}).json()
    assert updated["updated_at"] is not None
    assert updated["updated_by"] is not None
    # The grid renders "date + user", not an id.
    assert updated["updated_by_name"]


def test_plan_created_by_name_falls_back_to_the_legacy_login(client, db_session, carrier):
    """A migrated plan names a Denticon login that has no ``users`` row."""
    plan = _plan(db_session, carrier, group_number="GRP-LEGACY",
                 created_by="PDDS73", modified_by="Support")
    body = client.get(f"{PREFIX}/insurance-plans/{plan.id}").json()
    assert body["created_by_name"] == "PDDS73"
    assert body["updated_by_name"] == "Support"


# ── INS-PT-12: carrier_type is no longer stringly typed on the way in ────────
def test_is_dental_is_writable_and_canonicalised(client):
    dental = client.post(f"{PREFIX}/insurance-carriers",
                         json={"name": "Writable Dental", "is_dental": True})
    assert dental.status_code == 201, dental.text
    assert dental.json()["carrier_type"] == "True"
    assert dental.json()["is_dental"] is True

    medical = client.post(f"{PREFIX}/insurance-carriers",
                          json={"name": "Writable Medical", "is_dental": False})
    assert medical.json()["carrier_type"] == "False"
    assert medical.json()["is_dental"] is False

    # A written carrier_type is normalised to the canonical token.
    typed = client.post(f"{PREFIX}/insurance-carriers",
                        json={"name": "Typed", "carrier_type": "dental"})
    assert typed.json()["carrier_type"] == "True"

    flipped = client.patch(f"{PREFIX}/insurance-carriers/{typed.json()['id']}",
                           json={"is_dental": False})
    assert flipped.json()["carrier_type"] == "False"


def test_is_dental_filter_shares_the_read_vocabulary(client, db_session):
    """The point of INS-PT-12: a carrier that *reads* as dental must also
    *filter* as dental, even when carrier_type holds an unrecognised string."""
    typo = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Typo Co",
                            carrier_type="Trrue", is_active=True)
    medical = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Med Co",
                               carrier_type="False", is_active=True)
    db_session.add_all([typo, medical])
    db_session.commit()

    def _ids(is_dental: bool) -> set[int]:
        body = client.get(f"{PREFIX}/insurance-carriers",
                          params={"is_dental": is_dental}).json()
        return {c["id"] for c in body["items"]}

    dental_ids, medical_ids = _ids(True), _ids(False)
    assert typo.id in dental_ids
    assert medical.id in medical_ids
    assert typo.id not in medical_ids

    typo_read = client.get(f"{PREFIX}/insurance-carriers/{typo.id}").json()
    assert typo_read["is_dental"] is True          # read and filter agree
    assert typo_read["carrier_type"] == "Trrue"    # stored as written, not coerced


# ── INS-PT-13: quick-add name collisions ─────────────────────────────────────
def test_duplicate_carrier_name_is_409_with_override(client):
    created = client.post(f"{PREFIX}/insurance-carriers", json={"name": "Unique Co"})
    assert created.status_code == 201

    dup = client.post(f"{PREFIX}/insurance-carriers", json={"name": " unique co "})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_carrier_name"

    forced = client.post(f"{PREFIX}/insurance-carriers",
                         json={"name": "Unique Co", "allow_duplicate_name": True})
    assert forced.status_code == 201


def test_duplicate_employer_name_is_409_with_override(client):
    assert client.post(f"{PREFIX}/employers", json={"name": "Initech"}).status_code == 201
    dup = client.post(f"{PREFIX}/employers", json={"name": "INITECH"})
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_employer_name"
    assert client.post(f"{PREFIX}/employers",
                       json={"name": "Initech", "allow_duplicate_name": True}).status_code == 201


def test_rename_onto_a_taken_name_is_allowed(client):
    """Only create is guarded — a rename onto an existing name is far more often
    a deliberate merge than a slip, and blocking it strands the row."""
    client.post(f"{PREFIX}/insurance-carriers", json={"name": "Keeper"})
    mover = client.post(f"{PREFIX}/insurance-carriers", json={"name": "Mover"}).json()
    assert client.patch(f"{PREFIX}/insurance-carriers/{mover['id']}",
                        json={"name": "Keeper"}).status_code == 200


def test_name_availability_probes(client, employer):
    carrier_probe = client.get(f"{PREFIX}/insurance-carriers/name-availability",
                               params={"name": "Nobody Inc"})
    assert carrier_probe.status_code == 200
    assert carrier_probe.json()["taken"] is False

    taken = client.get(f"{PREFIX}/employers/name-availability", params={"name": " globex "}).json()
    assert taken["taken"] is True
    assert [m["id"] for m in taken["matches"]] == [employer.id]

    excluded = client.get(f"{PREFIX}/employers/name-availability",
                          params={"name": "Globex", "exclude_id": employer.id}).json()
    assert excluded["taken"] is False


# ── INS-PT-11: second employer address line ──────────────────────────────────
def test_employer_address2_persists(client):
    r = client.post(f"{PREFIX}/employers", json={
        "name": "Two Lines Ltd", "address": "1 Main St", "address2": "Suite 400",
    })
    assert r.status_code == 201, r.text
    assert r.json()["address2"] == "Suite 400"


# ── tenancy: the new lookups never leak across tenants ───────────────────────
def test_group_availability_is_tenant_scoped(client, db_session, carrier):
    from app.db.models import Tenant

    other_tenant = Tenant(name="Other Practice", code="other", is_active=True)
    db_session.add(other_tenant)
    db_session.commit()
    db_session.refresh(other_tenant)
    db_session.add(InsurancePlan(tenant_id=other_tenant.id, carrier_id=carrier.id,
                                 group_number="GRP-FOREIGN", is_active=True))
    db_session.commit()

    body = client.get(f"{PREFIX}/insurance-plans/group-availability",
                      params={"group_number": "GRP-FOREIGN"}).json()
    assert body["taken"] is False
    # …and the save path agrees.
    assert client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "GRP-FOREIGN",
    }).status_code == 201
