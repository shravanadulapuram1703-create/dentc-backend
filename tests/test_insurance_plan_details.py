"""Insurance Plan Details wizard — PLAN-DTL-1 … PLAN-DTL-9.

The four-tab INSURANCE DETAILS dialog (PLAN · BENEFITS · COVERAGE &
LIMITATIONS · FREQ LIMITATION CODE GRP) and COPY FROM EXISTING.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import (
    Definition,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    InsurancePlanFrequencyGroup,
    Tenant,
)
from app.services.insurance_plan_service import (
    DEFAULT_COVERAGE_TABLE,
    FREQUENCY_LIMITATIONS,
    compose_age_limit,
    parse_age_limit,
)
from scripts.dedupe_definitions import dedupe as dedupe_definitions
from scripts.seed_insurance_plan_definitions import seed_for_tenant as seed_plan_defs

PREFIX = "/api/v1"


@pytest.fixture
def carrier(db_session) -> InsuranceCarrier:
    c = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Acme Dental",
                         carrier_type="True", payer_id="PAY-1", is_active=True)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def _plan(db_session, carrier, **kw) -> InsurancePlan:
    plan = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                         is_active=True, **kw)
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


def _other_tenant_plan(db_session) -> InsurancePlan:
    t = Tenant(name="Other", code="other", is_active=True)
    db_session.add(t)
    db_session.commit()
    c = InsuranceCarrier(tenant_id=t.id, name="Elsewhere", carrier_type="True")
    db_session.add(c)
    db_session.commit()
    p = InsurancePlan(tenant_id=t.id, carrier_id=c.id, group_number="FOREIGN", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


# ── PLAN-DTL-1: the nine plan-level fields round-trip ────────────────────────
def test_plan_extras_persist_and_read_back(client, carrier):
    body = {
        "carrier_id": carrier.id, "group_number": "QA-WIZ-1",
        "fees_to_print": "plan_fees", "claim_option": "submit", "form_to_print": "ADA2024",
        "reporting_subtype": "Delta", "network_type": "in_network", "noa_only": True,
        "per_visit_copay": "25.00", "lifetime_ortho_benefits": True,
        "plan_notes": "Ortho covered to age 19",
    }
    r = client.post(f"{PREFIX}/insurance-plans", json=body)
    assert r.status_code == 201, r.text
    plan = r.json()
    for k, v in body.items():
        if k in ("carrier_id", "group_number"):
            continue
        assert str(plan[k]) == str(v), k

    # Round-trips through GET and PATCH too.
    got = client.get(f"{PREFIX}/insurance-plans/{plan['id']}").json()
    assert got["plan_notes"] == "Ortho covered to age 19"
    patched = client.patch(f"{PREFIX}/insurance-plans/{plan['id']}",
                           json={"network_type": "out_of_network", "noa_only": False}).json()
    assert patched["network_type"] == "out_of_network"
    assert patched["noa_only"] is False
    assert patched["fees_to_print"] == "plan_fees"  # untouched


def test_plan_extras_default_to_legacy_dialog_values(client, carrier):
    """EDIT-PLAN-9: an omitted coded field stores the legacy default (never
    NULL), and ``lifetime_ortho_benefits`` defaults **on** like the legacy
    dialog — so the first edit of a new plan audits no phantom changes."""
    plan = client.post(f"{PREFIX}/insurance-plans", json={"carrier_id": carrier.id}).json()
    assert plan["noa_only"] is False
    assert plan["lifetime_ortho_benefits"] is True
    assert plan["plan_notes"] is None
    assert plan["fees_to_print"] == "office_ucr"
    assert plan["claim_option"] == "submit"
    assert plan["form_to_print"] == "ADA2024"
    assert plan["network_type"] == "unknown"


# ── PLAN-DTL-3: anniversary Month/Day ────────────────────────────────────────
def test_anniversary_month_day_writes_a_consistent_date(client, carrier):
    r = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "anniversary_month": 7, "anniversary_day": 1,
    })
    assert r.status_code == 201, r.text
    plan = r.json()
    assert (plan["anniversary_month"], plan["anniversary_day"]) == (7, 1)
    assert plan["anniversary_date"].endswith("-07-01")
    assert plan["anniversary_date"].startswith(str(date.today().year))


def test_anniversary_date_write_derives_month_and_day(client, carrier):
    plan = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "anniversary_date": "2022-01-01",
    }).json()
    assert (plan["anniversary_month"], plan["anniversary_day"]) == (1, 1)

    # A month/day PATCH keeps the stored year.
    patched = client.patch(f"{PREFIX}/insurance-plans/{plan['id']}",
                           json={"anniversary_month": 3, "anniversary_day": 15}).json()
    assert patched["anniversary_date"] == "2022-03-15"
    assert (patched["anniversary_month"], patched["anniversary_day"]) == (3, 15)


def test_anniversary_validation(client, carrier):
    r = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "anniversary_month": 2, "anniversary_day": 30,
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_anniversary"
    r = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "anniversary_month": 5,
    })
    assert r.status_code == 422


def test_anniversary_can_be_cleared(client, carrier):
    plan = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "anniversary_date": "2022-01-01",
    }).json()
    cleared = client.patch(f"{PREFIX}/insurance-plans/{plan['id']}",
                           json={"anniversary_month": None, "anniversary_day": None}).json()
    assert cleared["anniversary_date"] is None
    assert cleared["anniversary_month"] is None


# ── PLAN-DTL-5: typed limits on coverage rules ──────────────────────────────
def test_coverage_rule_typed_limits_and_mirrors(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G1")
    r = client.post(f"{PREFIX}/insurance-coverage-rules", json={
        "ins_plan_id": plan.id, "start_code": "02A", "end_code": "02A", "category": "0",
        "description": "Preventive: Sealants", "coverage_pct": 100,
        "freq_limit": 12, "age_min": 5, "age_max": 14, "wait_months": 6,
    })
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["freq_limit"] == 12
    assert (rule["age_min"], rule["age_max"]) == (5, 14)
    assert rule["age_limit"] == "5-14"           # derived mirror
    assert rule["wait_months"] == 6
    assert rule["wait_period"] == "6"
    # PLAN-DTL-9
    assert "updated_at" in rule and "updated_by" in rule and "created_by" in rule


def test_coverage_rule_legacy_strings_still_parse(client, db_session, carrier):
    """An older client sending only the string columns lands in the typed ones."""
    plan = _plan(db_session, carrier, group_number="G2")
    r = client.post(f"{PREFIX}/insurance-coverage-rules", json={
        "ins_plan_id": plan.id, "start_code": "01", "end_code": "01",
        "freq_limit": "6", "age_limit": "19", "wait_period": "12",
    })
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["freq_limit"] == 6
    assert (rule["age_min"], rule["age_max"]) == (19, None)   # wizard convention: lone = min
    assert rule["wait_months"] == 12

    # Typed fields win when both are sent; the mirror is re-derived.
    patched = client.patch(f"{PREFIX}/insurance-coverage-rules/{rule['id']}",
                           json={"age_max": 26, "age_limit": "stale"}).json()
    assert (patched["age_min"], patched["age_max"]) == (19, 26)
    assert patched["age_limit"] == "19-26"


def test_coverage_rule_rejects_bad_limits(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G3")
    base = {"ins_plan_id": plan.id, "start_code": "01", "end_code": "01"}
    r = client.post(f"{PREFIX}/insurance-coverage-rules", json={**base, "age_min": 20, "age_max": 5})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_age_limit"
    r = client.post(f"{PREFIX}/insurance-coverage-rules", json={**base, "freq_limit": "twice"})
    assert r.status_code == 422
    r = client.post(f"{PREFIX}/insurance-coverage-rules", json={**base, "wait_months": -1})
    assert r.status_code == 422


def test_age_limit_helpers():
    assert parse_age_limit("5-14") == (5, 14)
    assert parse_age_limit("19") == (19, None)
    assert parse_age_limit("0") == (None, None)
    assert parse_age_limit("WM") == (None, None)
    assert compose_age_limit(None, 14) == "0-14"
    assert compose_age_limit(19, None) == "19"
    assert compose_age_limit(None, None) is None


# ── tenancy: coverage rules are reachable only through the tenant's plans ────
def test_coverage_rules_are_tenant_scoped_through_the_plan(client, db_session, carrier):
    foreign = _other_tenant_plan(db_session)
    rule = InsuranceCoverageRule(ins_plan_id=foreign.id, start_code="01", end_code="01",
                                 coverage_pct=100)
    db_session.add(rule)
    db_session.commit()

    assert client.get(f"{PREFIX}/insurance-coverage-rules/{rule.id}").status_code == 404
    assert client.patch(f"{PREFIX}/insurance-coverage-rules/{rule.id}",
                        json={"coverage_pct": 0}).status_code == 404
    assert client.delete(f"{PREFIX}/insurance-coverage-rules/{rule.id}").status_code == 404
    listed = client.get(f"{PREFIX}/insurance-coverage-rules",
                        params={"ins_plan_id": foreign.id}).json()
    assert listed["meta"]["total"] == 0
    # …and a rule cannot be created on another tenant's plan.
    r = client.post(f"{PREFIX}/insurance-coverage-rules", json={
        "ins_plan_id": foreign.id, "start_code": "01", "end_code": "01",
    })
    assert r.status_code == 404


# ── PLAN-DTL-2: frequency code groups ────────────────────────────────────────
def test_frequency_group_resource(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G4")
    r = client.post(f"{PREFIX}/insurance-plan-frequency-groups", json={
        "ins_plan_id": plan.id, "code_group": "01", "freq_limit": 6,
        "whole_mouth": True, "per_day_quantity": 2,
    })
    assert r.status_code == 201, r.text
    g = r.json()
    assert g["description"] == "Diagnostic: Periodic Exam (D0120)"  # filled from the catalogue
    assert g["whole_mouth"] is True and g["per_day_quantity"] == 2

    # One row per code group per plan.
    dup = client.post(f"{PREFIX}/insurance-plan-frequency-groups", json={
        "ins_plan_id": plan.id, "code_group": "01", "freq_limit": 1,
    })
    assert dup.status_code == 409

    listed = client.get(f"{PREFIX}/insurance-plan-frequency-groups",
                        params={"ins_plan_id": plan.id}).json()
    assert listed["meta"]["total"] == 1


def test_frequency_group_shape_is_refused_as_a_coverage_rule(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G5")
    for body in (
        {"category": "FREQGRP", "start_code": "FQ01", "end_code": "FQ01"},
        {"category": "0", "start_code": "FQ02", "end_code": "FQ02"},
    ):
        r = client.post(f"{PREFIX}/insurance-coverage-rules", json={"ins_plan_id": plan.id, **body})
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "frequency_group_row_not_coverage"


# ── PLAN-DTL-8: the bulk replace ─────────────────────────────────────────────
def _default_rules():
    return [
        {"start_code": code, "category": "0", "description": label, "coverage_pct": pct}
        for code, label, pct in DEFAULT_COVERAGE_TABLE
    ]


def test_bulk_replace_creates_a_whole_table_atomically(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G6")
    body = {
        "rules": _default_rules() + [
            {"start_code": "D0120", "category": "01", "description": "Periodic exam",
             "coverage_pct": 90, "freq_limit": 4},
        ],
        "frequency_groups": [
            {"code_group": "01", "freq_limit": 6, "per_day_quantity": 2},
        ],
    }
    r = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["summary"]["rules"] == {"created": 29, "updated": 0, "deleted": 0}
    assert out["summary"]["frequency_groups"] == {"created": 1, "updated": 0, "deleted": 0}
    assert len(out["rules"]) == 29
    exc = next(x for x in out["rules"] if x["start_code"] == "D0120")
    assert exc["end_code"] == "D0120" and exc["category"] == "01" and exc["freq_limit"] == 4
    assert out["frequency_groups"][0]["description"] == "Diagnostic: Periodic Exam (D0120)"

    # GET mirrors it.
    got = client.get(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules").json()
    assert len(got["rules"]) == 29 and len(got["frequency_groups"]) == 1


def test_bulk_replace_keeps_ids_and_deletes_unmentioned(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G7")
    first = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [
            {"start_code": "01", "category": "0", "coverage_pct": 100},
            {"start_code": "02", "category": "0", "coverage_pct": 100},
            {"start_code": "03", "category": "0", "coverage_pct": 80},
        ],
    }).json()
    ids = {x["start_code"]: x["id"] for x in first["rules"]}

    second = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [
            {"id": ids["01"], "start_code": "01", "category": "0", "coverage_pct": 90},
            {"start_code": "04", "category": "0", "coverage_pct": 50},
        ],
        # frequency_groups omitted → untouched (none exist anyway)
    }).json()
    assert second["summary"]["rules"] == {"created": 1, "updated": 1, "deleted": 2}
    assert second["summary"]["frequency_groups"] is None
    by_code = {x["start_code"]: x for x in second["rules"]}
    assert by_code["01"]["id"] == ids["01"]
    assert str(by_code["01"]["coverage_pct"]).startswith("90")
    assert set(by_code) == {"01", "04"}


def test_bulk_replace_is_all_or_nothing(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G8")
    client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [{"start_code": "01", "category": "0", "coverage_pct": 100}],
    })
    bad = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "rules": [
            {"start_code": "02", "category": "0", "coverage_pct": 100},
            {"start_code": "FQ01", "category": "FREQGRP"},   # the refused shape
        ],
    })
    assert bad.status_code == 422, bad.text
    assert bad.json()["error"]["code"] == "frequency_group_row_not_coverage"
    still = client.get(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules").json()
    assert [x["start_code"] for x in still["rules"]] == ["01"]   # nothing changed


def test_bulk_replace_rejects_foreign_ids(client, db_session, carrier):
    a = _plan(db_session, carrier, group_number="G9")
    b = _plan(db_session, carrier, group_number="G10")
    rule_b = client.put(f"{PREFIX}/insurance-plans/{b.id}/coverage-rules", json={
        "rules": [{"start_code": "01", "category": "0"}],
    }).json()["rules"][0]
    r = client.put(f"{PREFIX}/insurance-plans/{a.id}/coverage-rules", json={
        "rules": [{"id": rule_b["id"], "start_code": "01", "category": "0"}],
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "rule_not_on_plan"


def test_bulk_replace_frequency_groups_repeated_code_is_422(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G11")
    r = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "frequency_groups": [{"code_group": "01"}, {"code_group": "01"}],
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "duplicate_code_group"


def test_bulk_replace_frequency_groups_adopts_same_code_without_id(client, db_session, carrier):
    """A re-PUT of the FREQ tab without ids must not 409 on the unique key."""
    plan = _plan(db_session, carrier, group_number="G12")
    client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "frequency_groups": [{"code_group": "01", "freq_limit": 6}],
    })
    r = client.put(f"{PREFIX}/insurance-plans/{plan.id}/coverage-rules", json={
        "frequency_groups": [{"code_group": "01", "freq_limit": 4, "whole_mouth": True}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["frequency_groups"] == {"created": 0, "updated": 1, "deleted": 0}
    assert r.json()["frequency_groups"][0]["whole_mouth"] is True


def test_bulk_replace_is_tenant_scoped(client, db_session):
    foreign = _other_tenant_plan(db_session)
    r = client.put(f"{PREFIX}/insurance-plans/{foreign.id}/coverage-rules", json={"rules": []})
    assert r.status_code == 404


# ── COPY FROM EXISTING ───────────────────────────────────────────────────────
def test_copy_from_existing_copies_table_and_optionally_plan_fields(client, db_session, carrier):
    source = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "SRC", "plan_type": "PPO",
        "individual_max": "1500.00", "fees_to_print": "carrier_fees", "plan_notes": "copied",
    }).json()
    client.put(f"{PREFIX}/insurance-plans/{source['id']}/coverage-rules", json={
        "rules": _default_rules(),
        "frequency_groups": [{"code_group": "02", "freq_limit": 4, "whole_mouth": True}],
    })
    target = client.post(f"{PREFIX}/insurance-plans", json={
        "carrier_id": carrier.id, "group_number": "TGT",
    }).json()

    r = client.post(f"{PREFIX}/insurance-plans/{target['id']}/copy-from/{source['id']}", json={})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["copied_from_plan_id"] == source["id"]
    assert len(out["rules"]) == len(DEFAULT_COVERAGE_TABLE)
    assert out["frequency_groups"][0]["code_group"] == "02"
    assert out["copied_plan_fields"] == []
    # Plan fields untouched unless asked.
    assert client.get(f"{PREFIX}/insurance-plans/{target['id']}").json()["plan_notes"] is None

    r = client.post(f"{PREFIX}/insurance-plans/{target['id']}/copy-from/{source['id']}",
                    json={"include_plan_fields": True, "include_rules": False,
                          "include_frequency_groups": False})
    assert r.status_code == 200
    plan = client.get(f"{PREFIX}/insurance-plans/{target['id']}").json()
    assert plan["plan_notes"] == "copied" and plan["fees_to_print"] == "carrier_fees"
    assert str(plan["individual_max"]).startswith("1500")
    # Identity never copies.
    assert plan["group_number"] == "TGT"
    # The table survived the fields-only copy.
    assert len(client.get(f"{PREFIX}/insurance-plans/{target['id']}/coverage-rules").json()["rules"]) \
        == len(DEFAULT_COVERAGE_TABLE)


def test_copy_onto_self_is_422(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="SELF")
    r = client.post(f"{PREFIX}/insurance-plans/{plan.id}/copy-from/{plan.id}")
    assert r.status_code == 422


# ── PLAN-DTL-1/4: the metadata endpoint ──────────────────────────────────────
def test_plan_metadata_builtin_fallback(client):
    meta = client.get(f"{PREFIX}/insurance-plans/metadata").json()
    freq = meta["frequency_limitations"]
    assert freq[0] == {"code": 0, "label": "No Limitation", "key1": None, "key2": None,
                       "definition_id": None, "legacy_id": None}
    assert [f["code"] for f in freq[1:]] == list(range(1, 14))
    assert freq[6]["label"] == "Once per Benefit Year"      # ordinal 6, as migrated rows store
    assert len(meta["default_coverage_rules"]) == 28
    diag = next(r for r in meta["default_coverage_rules"] if r["start_code"] == "01")
    assert diag["coverage_pct"] == 100 and diag["freq_limit"] == 1 and diag["category"] == "0"
    assert meta["plan_field_options"]["form_to_print"][0]["code"] == "ADA2024"
    assert meta["catalog_sources"]["frequency_limitations"] == "builtin"
    assert len(meta["code_groups"]) == 22


def test_plan_metadata_uses_tenant_definitions_once_seeded(client, db_session):
    counts = seed_plan_defs(db_session, db_session._tenant_id, apply=True, overwrite=False)
    assert counts["added"] > 0
    # Idempotent.
    assert seed_plan_defs(db_session, db_session._tenant_id, apply=True, overwrite=False) == {
        "added": 0, "patched": 0}

    meta = client.get(f"{PREFIX}/insurance-plans/metadata").json()
    assert meta["catalog_sources"] == {
        "frequency_limitations": "tenant", "default_coverage_rules": "tenant", "code_groups": "tenant"}
    assert all(f["definition_id"] for f in meta["frequency_limitations"][1:])

    # The seeded FREQUENCYLIMITATIONS rows carry the ordinal in sort_order.
    rows = client.get(f"{PREFIX}/definitions",
                      params={"group_code": "FREQUENCYLIMITATIONS", "size": 50}).json()["items"]
    by_label = {r["description"]: r["sort_order"] for r in rows}
    assert by_label["Once per Benefit Year"] == 6
    assert len(by_label) == len(FREQUENCY_LIMITATIONS)


def test_seeder_patches_ordinal_onto_migrated_rows(db_session):
    """A migrated tenant has the 13 rows with no sort_order — they get the ordinal, not a duplicate."""
    tid = db_session._tenant_id
    for _ordinal, label, key1, key2 in FREQUENCY_LIMITATIONS:
        db_session.add(Definition(tenant_id=tid, group_code="FREQUENCYLIMITATIONS",
                                  key1=key1, key2=key2, description=label))
    db_session.commit()
    counts = seed_plan_defs(db_session, tid, apply=True, overwrite=False)
    assert counts["patched"] == 13
    rows = db_session.query(Definition).filter_by(tenant_id=tid, group_code="FREQUENCYLIMITATIONS").all()
    assert len(rows) == 13
    assert {r.description: r.sort_order for r in rows}["Once per Lifetime"] == 12


# ── PLAN-DTL-6: duplicate definitions ────────────────────────────────────────
def test_definitions_unique_constraint_and_dedupe(db_session):
    tid = db_session._tenant_id
    # The dedupe script removes exact duplicates that predate the constraint
    # (insert them bypassing the ORM constraint is not possible on SQLite with
    # the constraint in place, so exercise the script on a clean table + the
    # constraint directly).
    db_session.add(Definition(tenant_id=tid, group_code="DEFCOVERAGE", key1="01",
                              key2="100", description="Diagnostic"))
    db_session.commit()
    removed, differing = dedupe_definitions(db_session, tid)
    assert (removed, differing) == (0, 0)

    from sqlalchemy.exc import IntegrityError
    db_session.add(Definition(tenant_id=tid, group_code="DEFCOVERAGE", key1="01",
                              key2="100", description="Diagnostic"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Same code with a different label is allowed (description is part of the key).
    db_session.add(Definition(tenant_id=tid, group_code="DEFCOVERAGE", key1="01",
                              key2="100", description="Diagnostic (custom)"))
    db_session.commit()


# ── PLAN-DTL-9: modified metadata on rules ───────────────────────────────────
def test_coverage_rule_update_stamps_updated_by(client, db_session, carrier):
    plan = _plan(db_session, carrier, group_number="G13")
    rule = client.post(f"{PREFIX}/insurance-coverage-rules", json={
        "ins_plan_id": plan.id, "start_code": "01", "end_code": "01", "coverage_pct": 100,
    }).json()
    assert rule["created_by"] == db_session._admin.id
    assert rule["updated_by"] is None
    patched = client.patch(f"{PREFIX}/insurance-coverage-rules/{rule['id']}",
                           json={"coverage_pct": 80}).json()
    assert patched["updated_by"] == db_session._admin.id
    assert patched["updated_at"] is not None


def test_frequency_groups_are_tenant_scoped(client, db_session):
    foreign = _other_tenant_plan(db_session)
    g = InsurancePlanFrequencyGroup(tenant_id=foreign.tenant_id, ins_plan_id=foreign.id,
                                    code_group="01")
    db_session.add(g)
    db_session.commit()
    assert client.get(f"{PREFIX}/insurance-plan-frequency-groups/{g.id}").status_code == 404
    r = client.post(f"{PREFIX}/insurance-plan-frequency-groups",
                    json={"ins_plan_id": foreign.id, "code_group": "02"})
    assert r.status_code == 404
