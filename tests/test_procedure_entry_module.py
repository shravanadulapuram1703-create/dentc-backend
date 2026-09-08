"""Procedure entry — one path for four screens (PROC-INT-1..9).

Backs ``docs/procedures/procedure_entry_integration.md`` § Backend gaps.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models import Office, Patient, Provider, TreatmentPlanItem
from app.services import messaging_events, procedure_events
from app.services.procedure_rules_service import (
    normalise_surface,
    parse_tooth,
    surface_tokens,
)

PREFIX = "/api/v1"


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, name="Main", office_code="MAIN", is_active=True)
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def provider(db_session, office) -> Provider:
    p = Provider(id="DR-1", tenant_id=db_session._tenant_id, office_id=office.id,
                 name="Ann Drill", first_name="Ann", last_name="Drill", is_active=True)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture
def patient(db_session, office) -> Patient:
    p = Patient(tenant_id=db_session._tenant_id, first_name="Proc", last_name="Entry",
                chart_no="PE-1", home_office_id=office.id, is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def codes(client):
    """A two-surface posterior composite (tooth+surface, exactly 2), a quadrant
    SRP, a plain exam, and an anterior-only composite."""
    rows = [
        {"code": "D2392", "description": "Resin two surface posterior", "category": "Restorative",
         "requires_tooth": True, "requires_surface": True, "min_surfaces": 2, "max_surfaces": 2,
         "tooth_area": "posterior", "surface_rules": {"min": 2, "max": 2, "allowed": ["M", "O", "D", "B", "L"]}},
        {"code": "D4341", "description": "SRP per quadrant", "category": "Perio",
         "requires_quadrant": True,
         "anatomy_rules": {"mode": "quadrant", "allowed_quadrants": ["UR", "UL", "LL", "LR"]}},
        {"code": "D0120", "description": "Periodic exam", "category": "Diagnostic"},
        {"code": "D2330", "description": "Resin one surface anterior", "category": "Restorative",
         "requires_tooth": True, "requires_surface": True, "tooth_area": "anterior",
         "valid_teeth": ["6", "7", "8", "9", "10", "11", "22", "23", "24", "25", "26", "27"]},
        {"code": "D2740", "description": "Crown", "category": "Restorative",
         "requires_tooth": True, "requires_lab": True},
    ]
    for row in rows:
        r = client.post(f"{PREFIX}/procedure-codes", json={"default_fee": 100, **row})
        assert r.status_code == 201, r.text
    return rows


def _plan(client, patient_id: int, pid: str = "TP-1") -> str:
    r = client.post(f"{PREFIX}/treatment-plans",
                    json={"id": pid, "patient_id": patient_id, "name": "Plan 1"})
    assert r.status_code == 201, r.text
    return pid


def _item(client, plan_id: str, code: str, item_id: str, **extra) -> dict:
    body = {"id": item_id, "plan_id": plan_id, "procedure_code": code, "fee": 150, **extra}
    r = client.post(f"{PREFIX}/treatment-plan-items", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _charge_body(patient, provider, office, code, **extra) -> dict:
    return {
        "id": extra.pop("id", f"PP-{code}-{extra.get('tooth', 'x')}"),
        "patient_id": patient.id, "procedure_code": code, "date_of_service": "2026-09-06",
        "provider_id": provider.id, "office_id": office.id, "fee": 120, **extra,
    }


@pytest.fixture
def events(monkeypatch):
    """Capture procedures.changed envelopes instead of pushing to sockets."""
    captured: list[tuple[int, dict]] = []
    monkeypatch.setattr(messaging_events, "publish_tenant",
                        lambda tenant_id, envelope: captured.append((tenant_id, envelope)))
    return captured


# ── PROC-INT-6: surface vocabulary ────────────────────────────────────────────
def test_surface_normalisation_is_canonical_order_and_arch_aware():
    assert normalise_surface("d,o m") == "MOD"
    assert normalise_surface("dom") == "MOD"
    assert normalise_surface("FML") == "MFL"
    # arch spelling: O/B on posterior, I/F on anterior
    assert normalise_surface("MOD", parse_tooth("8")) == "MID"
    assert normalise_surface("MIF", parse_tooth("30")) == "MOB"
    assert normalise_surface("OI") == "OI"  # unknown tooth: both kept as given
    assert normalise_surface("OI", parse_tooth("19")) == "O"  # same surface, collapsed
    # Class V is a qualifier on B/F/L, stored as a suffix and counted once
    assert normalise_surface("L B5") == "B5L"
    assert surface_tokens("B5L") == ["B5", "L"]
    assert normalise_surface("B B5") == "B5"  # the qualified spelling wins
    assert normalise_surface("") is None and normalise_surface(None) is None


def test_surface_rejects_unknown_letters_and_misplaced_class_v(client):
    for bad in ("MOX", "O5", "MOD5"):
        with pytest.raises(Exception) as exc:
            normalise_surface(bad)
        assert exc.value.details["code"] == "invalid_surface"


def test_tooth_parsing_universal_supernumerary_and_legacy_quadrant():
    assert parse_tooth("8").anterior is True and parse_tooth("30").anterior is False
    assert parse_tooth("a").kind == "primary" and parse_tooth("A").raw == "A"
    t = parse_tooth("58")  # supernumerary of 8
    assert (t.base, t.supernumerary, t.anterior) == ("8", True, True)
    assert parse_tooth("KS").supernumerary is True
    q = parse_tooth("UR")
    assert q.is_quadrant and q.anterior is None
    with pytest.raises(Exception) as exc:
        parse_tooth("99")
    assert exc.value.details["code"] == "invalid_tooth"


def test_metadata_publishes_vocabulary_and_enforcement_contract(client):
    r = client.get(f"{PREFIX}/metadata/procedure-entry-rules")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [s["code"] for s in body["surfaces"]] == ["M", "O", "I", "D", "B", "F", "L"]
    assert body["class_v"]["kind"] == "qualifier"
    assert [q["code"] for q in body["quadrants"]] == ["UR", "UL", "LL", "LR", "UA", "LA", "FM"]
    assert "8" in body["teeth"]["anterior"] and "30" in body["teeth"]["posterior"]
    assert body["enforced"]["requires_surface"] is True
    assert body["enforced"]["requires_lab"] is False
    assert "surface_count" in body["error_codes"]


# ── PROC-INT-8: server-side validation on charges ─────────────────────────────
def test_charge_without_required_tooth_and_surface_is_422(client, patient, provider, office, codes):
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2392"))
    assert r.status_code == 422, r.text
    err = r.json()["error"]["details"]
    assert (err["code"], err["field"]) == ("tooth_required", "tooth")

    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2392", tooth="30"))
    assert r.json()["error"]["details"]["code"] == "surface_required"

    # wrong count for a "two surface" code
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2392", tooth="30", surface="MOD"))
    d = r.json()["error"]["details"]
    assert (d["code"], d["field"], d["count"]) == ("surface_count", "surface", 3)

    # anterior tooth on a posterior-only code
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2392", tooth="8", surface="MO"))
    assert r.json()["error"]["details"]["code"] == "tooth_not_allowed"

    # valid_teeth list on the anterior code
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2330", tooth="30", surface="F"))
    assert r.json()["error"]["details"]["code"] == "tooth_not_allowed"


def test_valid_charge_is_stored_canonicalised(client, patient, provider, office, codes):
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2392", tooth="30", surface="o, d"))
    assert r.status_code == 201, r.text
    assert r.json()["surface"] == "OD"

    # anterior spelling is applied when the tooth says so
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2330", tooth="8", surface="B"))
    assert r.status_code == 201, r.text
    assert r.json()["surface"] == "F"


def test_quadrant_required_and_legacy_quadrant_in_tooth(client, patient, provider, office, codes):
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D4341"))
    assert r.json()["error"]["details"]["code"] == "quadrant_required"

    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D4341", quadrant="ua"))
    assert r.json()["error"]["details"]["code"] == "quadrant_not_allowed"

    # the migrated shape: quadrant code in the tooth column → accepted + mirrored
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D4341", tooth="ur"))
    assert r.status_code == 201, r.text
    assert (r.json()["tooth"], r.json()["quadrant"]) == ("UR", "UR")


def test_requires_lab_is_advisory_and_exam_needs_nothing(client, patient, provider, office, codes):
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D2740", tooth="19"))
    assert r.status_code == 201, r.text  # no material_id, still accepted
    r = client.post(f"{PREFIX}/patient-procedures",
                    json=_charge_body(patient, provider, office, "D0120"))
    assert r.status_code == 201, r.text


def test_patch_that_does_not_touch_clinical_fields_skips_rules(client, db_session, patient, provider, office, codes):
    # A migrated-shaped charge: required tooth missing. Re-pricing it must work.
    from app.db.models import PatientProcedure
    row = PatientProcedure(id="PP-legacy", patient_id=patient.id, procedure_code="D2392",
                           date_of_service=date(2026, 1, 1), provider_id=provider.id,
                           office_id=office.id, fee=50)
    db_session.add(row)
    db_session.commit()
    r = client.patch(f"{PREFIX}/patient-procedures/PP-legacy", json={"fee": 75})
    assert r.status_code == 200, r.text
    # …but touching the surface re-evaluates the merge (tooth still missing)
    r = client.patch(f"{PREFIX}/patient-procedures/PP-legacy", json={"surface": "MO"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "tooth_required"


# ── PROC-INT-8 on planned items + PROC-INT-5 columns ──────────────────────────
def test_plan_item_rules_and_new_columns(client, patient, codes):
    plan = _plan(client, patient.id)
    r = client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "I-bad", "plan_id": plan, "procedure_code": "D2392", "fee": 100, "tooth": "30",
        "surface": "M",
    })
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "surface_count"

    item = _item(client, plan, "D4341", "I-q", quadrant="lr", material_id=None)
    assert item["quadrant"] == "LR"
    item = _item(client, plan, "D2392", "I-1", tooth="30", surface="do")
    assert item["surface"] == "OD" and item["procedure_id"] is None


# ── PROC-INT-1/2: the item ↔ charge link and the completed status ─────────────
def test_charge_with_item_id_completes_the_item_atomically(client, patient, provider, office, codes, events):
    plan = _plan(client, patient.id)
    _item(client, plan, "D2392", "I-1", tooth="30", surface="MO", status="accepted")
    events.clear()

    # The charge inherits tooth/surface from the item and needs no treatment_plan_id.
    r = client.post(f"{PREFIX}/patient-procedures", json=_charge_body(
        patient, provider, office, "D2392", id="PP-1", treatment_plan_item_id="I-1"))
    assert r.status_code == 201, r.text
    charge = r.json()
    assert (charge["tooth"], charge["surface"]) == ("30", "MO")
    assert charge["treatment_plan_id"] == plan
    assert charge["treatment_plan_item_id"] == "I-1"

    item = client.get(f"{PREFIX}/treatment-plan-items/I-1").json()
    assert item["status"] == "completed"
    assert item["end_date"] == "2026-09-06"
    assert item["provider_id"] == provider.id
    assert item["procedure_id"] == "PP-1"

    # one push for the charge, tagged as a post against the item
    kinds = [(e["source"], e["action"]) for _, e in events]
    assert ("patient_procedures", "posted") in kinds
    assert all(e["patient_id"] == str(patient.id) for _, e in events)

    # filter by the new FK
    listed = client.get(f"{PREFIX}/patient-procedures?treatment_plan_item_id=I-1").json()
    assert [p["id"] for p in listed["items"]] == ["PP-1"]


def test_item_of_another_patient_or_plan_is_rejected(client, db_session, patient, provider, office, codes):
    plan = _plan(client, patient.id)
    _item(client, plan, "D0120", "I-1")
    other = Patient(tenant_id=db_session._tenant_id, first_name="Other", last_name="One")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    r = client.post(f"{PREFIX}/patient-procedures", json={
        **_charge_body(other, provider, office, "D0120"), "treatment_plan_item_id": "I-1"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "plan_item_patient_mismatch"

    plan_b = _plan(client, patient.id, "TP-B")
    r = client.post(f"{PREFIX}/patient-procedures", json={
        **_charge_body(patient, provider, office, "D0120"),
        "treatment_plan_item_id": "I-1", "treatment_plan_id": plan_b})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "plan_item_plan_mismatch"

    r = client.post(f"{PREFIX}/patient-procedures", json={
        **_charge_body(patient, provider, office, "D0120"), "treatment_plan_item_id": "nope"})
    assert r.json()["error"]["details"]["code"] == "plan_item_not_found"


def test_voiding_the_charge_releases_the_item_and_unvoiding_rebinds(client, patient, provider, office, codes):
    plan = _plan(client, patient.id)
    _item(client, plan, "D0120", "I-1", status="accepted")
    r = client.post(f"{PREFIX}/patient-procedures", json=_charge_body(
        patient, provider, office, "D0120", id="PP-1", treatment_plan_item_id="I-1"))
    assert r.status_code == 201, r.text
    assert client.get(f"{PREFIX}/treatment-plan-items/I-1").json()["status"] == "completed"

    # DELETE is a void → item reopens
    assert client.delete(f"{PREFIX}/patient-procedures/PP-1").status_code == 204
    item = client.get(f"{PREFIX}/treatment-plan-items/I-1").json()
    assert (item["status"], item["end_date"], item["procedure_id"]) == ("accepted", None, None)

    # un-void → completed again
    r = client.patch(f"{PREFIX}/patient-procedures/PP-1", json={"is_void": False})
    assert r.status_code == 200, r.text
    assert client.get(f"{PREFIX}/treatment-plan-items/I-1").json()["status"] == "completed"

    # a second live charge keeps it completed when the first is voided
    r = client.post(f"{PREFIX}/patient-procedures", json=_charge_body(
        patient, provider, office, "D0120", id="PP-2", treatment_plan_item_id="I-1"))
    assert r.status_code == 201, r.text
    client.patch(f"{PREFIX}/patient-procedures/PP-1", json={"is_void": True})
    item = client.get(f"{PREFIX}/treatment-plan-items/I-1").json()
    assert (item["status"], item["procedure_id"]) == ("completed", "PP-2")


def test_repointing_a_charge_moves_the_completion(client, patient, provider, office, codes):
    plan = _plan(client, patient.id)
    _item(client, plan, "D0120", "I-1")
    _item(client, plan, "D0120", "I-2")
    r = client.post(f"{PREFIX}/patient-procedures", json=_charge_body(
        patient, provider, office, "D0120", id="PP-1", treatment_plan_item_id="I-1"))
    assert r.status_code == 201, r.text
    r = client.patch(f"{PREFIX}/patient-procedures/PP-1", json={"treatment_plan_item_id": "I-2"})
    assert r.status_code == 200, r.text
    assert client.get(f"{PREFIX}/treatment-plan-items/I-1").json()["status"] == "accepted"
    assert client.get(f"{PREFIX}/treatment-plan-items/I-2").json()["status"] == "completed"


def test_completed_status_cannot_be_written_by_hand(client, patient, provider, office, codes):
    plan = _plan(client, patient.id)
    r = client.post(f"{PREFIX}/treatment-plan-items", json={
        "id": "I-c", "plan_id": plan, "procedure_code": "D0120", "fee": 1, "status": "completed"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "status_requires_charge"

    _item(client, plan, "D0120", "I-1")
    r = client.patch(f"{PREFIX}/treatment-plan-items/I-1", json={"status": "completed"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "status_requires_charge"

    # once a live charge backs it, un-completing is refused …
    client.post(f"{PREFIX}/patient-procedures", json=_charge_body(
        patient, provider, office, "D0120", id="PP-1", treatment_plan_item_id="I-1"))
    r = client.patch(f"{PREFIX}/treatment-plan-items/I-1", json={"status": "accepted"})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "item_has_posted_charge"
    # … but non-status edits still work, and `scheduled` is a legal value elsewhere
    assert client.patch(f"{PREFIX}/treatment-plan-items/I-1", json={"fee": 99}).status_code == 200
    _item(client, plan, "D0120", "I-s", status="scheduled")


def test_migrated_completed_item_can_be_reopened_by_hand(client, db_session, patient, codes):
    """A migrated 'completed' row has no linked charge; Change Status must still work."""
    plan = _plan(client, patient.id)
    db_session.add(TreatmentPlanItem(id="I-m", plan_id=plan, procedure_code="D0120", fee=10,
                                     status="completed"))
    db_session.commit()
    r = client.patch(f"{PREFIX}/treatment-plan-items/I-m", json={"status": "accepted"})
    assert r.status_code == 200, r.text


# ── Post to Ledger, server-side ───────────────────────────────────────────────
def test_post_item_to_ledger_is_one_call(client, patient, provider, office, codes, events):
    plan = _plan(client, patient.id)
    _item(client, plan, "D2392", "I-1", tooth="30", surface="MO", provider_id=provider.id,
          insurance_estimate=60)
    events.clear()
    r = client.post(f"{PREFIX}/treatment-plan-items/I-1/post", json={"date_of_service": "2026-09-02"})
    assert r.status_code == 201, r.text
    charge = r.json()
    assert charge["procedure_code"] == "D2392"
    assert (charge["tooth"], charge["surface"]) == ("30", "MO")
    assert float(charge["fee"]) == 150 and float(charge["insurance_estimate"]) == 60
    assert float(charge["patient_estimate"]) == 90
    assert charge["office_id"] == office.id  # from the patient's home office
    assert charge["treatment_plan_item_id"] == "I-1" and charge["treatment_plan_id"] == plan
    item = client.get(f"{PREFIX}/treatment-plan-items/I-1").json()
    assert (item["status"], item["end_date"], item["procedure_id"]) == ("completed", "2026-09-02", charge["id"])
    assert any(e["action"] == "posted" for _, e in events)

    # posting twice is a 409, not a duplicate charge
    r = client.post(f"{PREFIX}/treatment-plan-items/I-1/post", json={})
    assert r.status_code == 409
    assert r.json()["error"]["details"]["code"] == "item_already_posted"


def test_post_item_requires_a_provider(client, patient, codes):
    plan = _plan(client, patient.id)
    _item(client, plan, "D0120", "I-1")
    r = client.post(f"{PREFIX}/treatment-plan-items/I-1/post")
    assert r.status_code == 422
    assert r.json()["error"]["details"]["code"] == "provider_required"


# ── PROC-INT-4: paged patient items with filters ──────────────────────────────
def test_patient_items_envelope_paging_and_filters(client, patient, provider, office, codes):
    plan = _plan(client, patient.id)
    for n in range(3):
        _item(client, plan, "D0120", f"I-{n}")
    client.post(f"{PREFIX}/patient-procedures", json=_charge_body(
        patient, provider, office, "D0120", id="PP-1", treatment_plan_item_id="I-0"))

    r = client.get(f"{PREFIX}/patients/{patient.id}/treatment-plan-items?size=2")
    body = r.json()
    assert body["meta"] == {"page": 1, "size": 2, "total": 3, "pages": 2}
    assert len(body["items"]) == 2
    r = client.get(f"{PREFIX}/patients/{patient.id}/treatment-plan-items?size=2&page=2")
    assert len(r.json()["items"]) == 1

    open_only = client.get(f"{PREFIX}/patients/{patient.id}/treatment-plan-items?include_completed=false").json()
    assert {i["id"] for i in open_only["items"]} == {"I-1", "I-2"}
    done = client.get(f"{PREFIX}/patients/{patient.id}/treatment-plan-items?status=completed").json()
    assert [i["id"] for i in done["items"]] == ["I-0"]
    assert done["items"][0]["procedure_id"] == "PP-1"


# ── PROC-INT-3: push ──────────────────────────────────────────────────────────
def test_item_writes_announce_and_envelope_shape(client, patient, codes, events):
    plan = _plan(client, patient.id)
    events.clear()
    _item(client, plan, "D0120", "I-1")
    client.patch(f"{PREFIX}/treatment-plan-items/I-1", json={"fee": 5})
    client.delete(f"{PREFIX}/treatment-plan-items/I-1")
    actions = [e["action"] for _, e in events]
    assert actions == ["created", "updated", "deleted"]
    env = events[0][1]
    assert env["type"] == procedure_events.EVENT_TYPE
    assert env["source"] == "treatment_plan_items"
    assert env["patient_id"] == str(patient.id) and env["treatment_plan_id"] == plan
    assert env["treatment_plan_item_id"] == "I-1" and isinstance(env["id"], str)
    assert env["at"].endswith("+00:00")


def test_tenant_channel_parsing_and_hub_delivery():
    from app.services.messaging_events import _parse_channel, tenant_channel_for

    assert _parse_channel(tenant_channel_for(7)) == (7, None)
    assert _parse_channel("msg:7:42") == (7, 42)
    assert _parse_channel("msg:x:tenant") is None


@pytest.mark.anyio
async def test_hub_delivers_tenant_topic_to_every_socket_of_the_tenant(monkeypatch):
    from app.integrations import redis_pubsub

    async def _noop(*_a, **_k):
        return None

    monkeypatch.setattr(redis_pubsub.fanout, "subscribe", _noop)
    monkeypatch.setattr(redis_pubsub.fanout, "unsubscribe", _noop)

    class Sock:
        def __init__(self):
            self.sent = []

        async def send_text(self, text):
            self.sent.append(text)

    hub = messaging_events.ConnectionHub()
    a, b, other = Sock(), Sock(), Sock()
    await hub.register(1, 10, a)
    await hub.register(1, 11, b)
    await hub.register(2, 20, other)
    await hub.on_fanout_message(messaging_events.tenant_channel_for(1), '{"type":"procedures.changed"}')
    assert len(a.sent) == 1 and len(b.sent) == 1 and other.sent == []
    await hub.unregister(1, 10, a)
    assert hub.local_tenant_connection_count(1) == 1
    await hub.unregister(1, 11, b)
    assert hub.local_tenant_connection_count(1) == 0


# ── PROC-INT-9: template tables carry surface + quadrant, normalised ──────────
def test_code_bundle_items_carry_surface_and_quadrant(client, codes):
    r = client.post(f"{PREFIX}/code-bundles", json={"name": "Posterior fill", "display_code": "PF"})
    assert r.status_code == 201, r.text
    bundle_id = r.json()["id"]
    r = client.post(f"{PREFIX}/code-bundle-items", json={
        "bundle_id": bundle_id, "procedure_code": "D2392", "tooth": "30", "surface": "d o",
        "quadrant": "lr"})
    assert r.status_code == 201, r.text
    assert (r.json()["surface"], r.json()["quadrant"]) == ("OD", "LR")
    # a template may leave the tooth out even though the code requires one
    r = client.post(f"{PREFIX}/code-bundle-items", json={
        "bundle_id": bundle_id, "procedure_code": "D2392", "surface": "MO"})
    assert r.status_code == 201, r.text


def test_explosion_code_items_carry_quadrant(client, codes):
    r = client.post(f"{PREFIX}/explosion-codes", json={"code": "SRP4", "description": "Full SRP"})
    assert r.status_code == 201, r.text
    r = client.post(f"{PREFIX}/explosion-code-items", json={
        "explosion_code_id": r.json()["id"], "procedure_code": "D4341", "quadrant": "ul"})
    assert r.status_code == 201, r.text
    assert r.json()["quadrant"] == "UL"


# ── PROC-INT-7: the structured-column derivation behind the seeder ───────────
def test_seeder_derives_structured_columns():
    from scripts.seed_procedure_code_rules import (
        _anatomy_rules,
        _surface_rules,
        tooth_area,
        valid_teeth_for,
    )

    assert _surface_rules("D2150") == {"min": 2, "max": 2, "allowed": ["M", "O", "I", "D", "B", "F", "L"]}
    assert _surface_rules("D2393")["allowed"] == ["M", "O", "D", "B", "L"]  # posterior composite
    assert _surface_rules("D2331")["allowed"] == ["M", "I", "D", "F", "L"]  # anterior composite
    assert _surface_rules("D2544") == {"min": 4, "max": 5, "allowed": ["M", "O", "I", "D", "B", "F", "L"]}
    assert _surface_rules("D2740") is None
    assert tooth_area("D2335") == "anterior" and tooth_area("D2394") == "posterior"
    assert tooth_area("D2150") is None
    ant = valid_teeth_for("anterior")
    assert "8" in ant and "30" not in ant and "E" in ant and "A" not in ant
    post = valid_teeth_for("posterior")
    assert "30" in post and "8" not in post and "K" in post
    assert _anatomy_rules(True) == {"mode": "quadrant", "allowed_quadrants": ["UR", "UL", "LL", "LR"]}
    assert _anatomy_rules(False) is None


def test_seeder_fills_structured_columns_and_clears_junk_area(client, db_session):
    from app.db.models import ProcedureCode
    from scripts.seed_procedure_code_rules import seed

    db_session.add_all([
        ProcedureCode(code="D2392", description="two surface posterior", category="Restorative",
                      tooth_area="Crown"),
        ProcedureCode(code="D4341", description="SRP", category="Perio"),
        ProcedureCode(code="D0150", description="Comp exam", category="Diagnostic", tooth_area="1"),
    ])
    db_session.commit()
    counts = seed(db_session, apply_changes=True)
    assert counts["tooth_area_cleared"] == 2
    d2392 = db_session.get(ProcedureCode, "D2392")
    assert (d2392.min_surfaces, d2392.max_surfaces) == (2, 2)
    assert d2392.tooth_area == "posterior"
    assert "30" in d2392.valid_teeth and "8" not in d2392.valid_teeth
    assert d2392.surface_rules["allowed"] == ["M", "O", "D", "B", "L"]
    d4341 = db_session.get(ProcedureCode, "D4341")
    assert d4341.requires_quadrant is True
    assert d4341.anatomy_rules["allowed_quadrants"] == ["UR", "UL", "LL", "LR"]
    assert db_session.get(ProcedureCode, "D0150").tooth_area is None
