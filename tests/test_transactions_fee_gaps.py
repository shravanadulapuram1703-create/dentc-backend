"""Third-pass Transactions gaps: FEE-1, FEE-2, FEE-3, CHG-10, PROV-3.

Backs the fee-schedule / metadata sections of
``docs/transactions/transactions_backend_devreport.md``:

- FEE-1  ADA -> coverage-category mapping, so a coverage band expressed as
         ``01A``/``03`` can price a charge that carries ``D0330``/``D2393``.
         Before this the engine matched nothing and quoted 0 % on real coverage.
- FEE-2  the office -> fee-schedule linkage reconstructed from posting history.
- FEE-3  server-side fee resolution: the quote endpoint, the estimate engine and
         the charge write path all agree because they call one resolver.
- CHG-10 ``key2`` (payment type / adjustment group) on the two pickers.
- PROV-3 ``providers.role`` canonicalised on write + the derived provider_kind.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.db.models import (
    Definition,
    FeeSchedule,
    FeeScheduleAssignment,
    FeeScheduleEntry,
    InsuranceCarrier,
    InsuranceCoverageRule,
    InsurancePlan,
    Office,
    Patient,
    PatientInsurance,
    ProcedureCode,
    Provider,
)
from app.services import coverage_category_service as covcat
from app.services import pricing_service
from app.services.provider_directory_service import canonical_role, provider_kind
from scripts.backfill_office_fee_schedules import run as backfill_office_schedules
from scripts.normalize_provider_roles import run as normalize_roles
from scripts.seed_coverage_categories import run as seed_categories
from scripts.seed_transaction_definitions import seed_for_tenant as seed_txn_defs

PREFIX = "/api/v1"
TODAY = date.today()


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def office(db_session) -> Office:
    o = Office(tenant_id=db_session._tenant_id, office_code="FEE1", name="Fee Office",
               short_id="FEE1")
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


@pytest.fixture
def codes(db_session) -> None:
    """A slice of the catalog spanning several coverage categories."""
    rows = [
        ("D0120", "Periodic exam", "Diagnostic"),
        ("D0330", "Panoramic film", "Diagnostic"),
        ("D2393", "Resin composite", "Restorative"),
        ("D2740", "Crown - porcelain", "Restorative"),
        ("21050", "Condylectomy", "Medical"),
    ]
    for code, desc, cat in rows:
        db_session.add(ProcedureCode(code=code, description=desc, category=cat,
                                     default_fee=Decimal("10.00")))
    db_session.commit()


@pytest.fixture
def plan(db_session) -> InsurancePlan:
    carrier = InsuranceCarrier(tenant_id=db_session._tenant_id, name="Test Carrier")
    db_session.add(carrier)
    db_session.commit()
    db_session.refresh(carrier)
    p = InsurancePlan(tenant_id=db_session._tenant_id, carrier_id=carrier.id,
                      group_number="G1", is_active=True)
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture
def patient(db_session, office, plan) -> Patient:
    pat = Patient(tenant_id=db_session._tenant_id, first_name="Fee", last_name="Payer",
                  chart_no="FEE-1", home_office_id=office.id, is_active=True)
    db_session.add(pat)
    db_session.commit()
    db_session.refresh(pat)
    db_session.add(PatientInsurance(patient_id=pat.id, ins_plan_id=plan.id,
                                    insurance_type="primary", is_active=True))
    db_session.commit()
    return pat


def _schedule(db_session, name, entries, **kw) -> FeeSchedule:
    sched = FeeSchedule(tenant_id=db_session._tenant_id, name=name, is_active=True, **kw)
    db_session.add(sched)
    db_session.commit()
    db_session.refresh(sched)
    for code, fee in entries.items():
        db_session.add(FeeScheduleEntry(fee_schedule_id=sched.id, procedure_code=code,
                                        patient_fee=Decimal(str(fee))))
    db_session.commit()
    return sched


# ── FEE-1: the ADA -> coverage-category mapping ─────────────────────────────


class TestCoverageCategoryMapping:
    def test_cdt_families_map_to_their_categories(self):
        assert covcat.derive_category("D0120") == "01"      # Diagnostic
        assert covcat.derive_category("D0330") == "01B"     # Panoramic, not just 01
        assert covcat.derive_category("D0272") == "01D"     # Bitewings
        assert covcat.derive_category("D1351") == "02A"     # Sealants
        assert covcat.derive_category("D2393") == "03"      # Restorative
        assert covcat.derive_category("D2740") == "03A"     # Crowns beat Restorative
        assert covcat.derive_category("D2542") == "07"      # Onlays band with prosth
        assert covcat.derive_category("D3330") == "04A"     # Molar endo
        assert covcat.derive_category("D4381") == "05B"     # Arestin
        assert covcat.derive_category("D7220") == "06A"     # Impactions
        assert covcat.derive_category("D8080") == "10"      # Ortho
        assert covcat.derive_category("D9944") == "11B"     # Nightguard

    def test_unmapped_codes_are_null_not_non_covered(self):
        """A medical/CPT code is *unclassified*, not *denied*. Filing it under
        "12 Non-covered Services" would make the engine refuse it as confidently
        as it approves a prophy."""
        assert covcat.derive_category("21050") is None
        assert covcat.derive_category("Z0100") is None

    def test_parent_band_covers_a_subcategory_code_but_not_the_reverse(self):
        # A plan that only bands "Restorative" still pays for a crown…
        assert covcat.category_matches("03", "03A") == 1
        # …and an exact band outranks it.
        assert covcat.category_matches("03A", "03A") == 2
        # But a "Restorative: Crowns" percentage must never price an amalgam.
        assert covcat.category_matches("03A", "03") is None

    def test_ada_range_test_stays_inside_the_letter_family(self):
        assert covcat.in_range("D0330", "D0100", "D0999")
        assert not covcat.in_range("D2740", "D0100", "D0999")
        assert not covcat.is_ada_code("01A")
        assert covcat.is_ada_code("D0120")

    def test_seed_script_populates_the_column_and_leaves_medical_null(
        self, db_session, codes
    ):
        changed = seed_categories(db_session, apply=True, overwrite=False, overrides={})
        assert changed == 4  # the four D-codes; the CPT code is unmapped
        assert db_session.get(ProcedureCode, "D2740").coverage_category == "03A"
        assert db_session.get(ProcedureCode, "21050").coverage_category is None

    def test_a_practice_override_survives_a_reseed(self, db_session, codes):
        seed_categories(db_session, apply=True, overwrite=False, overrides={})
        proc = db_session.get(ProcedureCode, "D2393")
        proc.coverage_category = "03B"
        db_session.commit()
        seed_categories(db_session, apply=True, overwrite=False, overrides={})
        assert db_session.get(ProcedureCode, "D2393").coverage_category == "03B"
        assert covcat.category_for(db_session, "D2393") == "03B"

    def test_metadata_endpoint_publishes_the_table(self, client, codes):
        r = client.get(f"{PREFIX}/metadata/coverage-categories")
        assert r.status_code == 200, r.text
        by_code = {row["code"]: row for row in r.json()}
        assert by_code["03A"]["description"] == "Restorative: Crowns"
        assert by_code["03A"]["parent_code"] == "03"
        assert {"start_code": "D2710", "end_code": "D2799"} in by_code["03A"]["cdt_ranges"]


class TestEstimateUsesCoverageCategories:
    """The FEE-1 blocker itself: a category-banded plan must price an ADA code."""

    @pytest.fixture
    def banded_plan(self, db_session, plan):
        for start, pct, desc in (("01", 100, "Diagnostic"),
                                 ("03", 80, "Restorative"),
                                 ("03A", 50, "Restorative: Crowns")):
            db_session.add(InsuranceCoverageRule(
                ins_plan_id=plan.id, start_code=start, end_code=start,
                description=desc, coverage_pct=Decimal(pct), ded_waived=True,
            ))
        db_session.commit()
        return plan

    def test_category_banded_plan_prices_an_ada_code(
        self, client, db_session, codes, patient, banded_plan
    ):
        seed_categories(db_session, apply=True, overwrite=False, overrides={})
        r = client.post(f"{PREFIX}/patients/{patient.id}/estimate", json={
            "lines": [{"procedure_code": "D2393", "fee": "131.00"}]
        })
        assert r.status_code == 200, r.text
        line = r.json()["lines"][0]
        # The exact case the dev report cites: 131.00 at 80 % -> 104.80.
        assert Decimal(line["insurance_estimate"]) == Decimal("104.80")
        assert Decimal(line["patient_estimate"]) == Decimal("26.20")
        assert line["coverage_category"] == "03"
        assert line["coverage_category_description"] == "Restorative"

    def test_subcategory_band_beats_its_parent(
        self, client, db_session, codes, patient, banded_plan
    ):
        seed_categories(db_session, apply=True, overwrite=False, overrides={})
        r = client.post(f"{PREFIX}/patients/{patient.id}/estimate", json={
            "lines": [{"procedure_code": "D2740", "fee": "800.00"}]
        })
        line = r.json()["lines"][0]
        # 03A "Crowns" at 50 %, not 03 "Restorative" at 80 %.
        assert Decimal(line["coverage_pct"]) == Decimal("50.00")
        assert Decimal(line["insurance_estimate"]) == Decimal("400.00")
        assert line["coverage_category"] == "03A"

    def test_ada_ranged_plan_still_works(self, client, db_session, codes, patient, plan):
        """The minority of plans banded on real ADA ranges must not regress."""
        db_session.add(InsuranceCoverageRule(
            ins_plan_id=plan.id, start_code="D2000", end_code="D2999",
            description="RESTORATIVE", coverage_pct=Decimal(70), ded_waived=True,
        ))
        db_session.commit()
        r = client.post(f"{PREFIX}/patients/{patient.id}/estimate", json={
            "lines": [{"procedure_code": "D2393", "fee": "100.00"}]
        })
        assert Decimal(r.json()["lines"][0]["insurance_estimate"]) == Decimal("70.00")

    def test_unclassified_code_gets_no_coverage_rather_than_a_wrong_band(
        self, client, db_session, codes, patient, banded_plan
    ):
        seed_categories(db_session, apply=True, overwrite=False, overrides={})
        r = client.post(f"{PREFIX}/patients/{patient.id}/estimate", json={
            "lines": [{"procedure_code": "21050", "fee": "500.00"}]
        })
        line = r.json()["lines"][0]
        assert Decimal(line["coverage_pct"]) == Decimal("0")
        assert Decimal(line["patient_estimate"]) == Decimal("500.00")


# ── FEE-3: server-side fee resolution ───────────────────────────────────────


class TestFeeResolution:
    def test_most_specific_assignment_wins(self, db_session, office, patient, plan, codes):
        wide = _schedule(db_session, "Practice wide", {"D0120": "145.00"})
        narrow = _schedule(db_session, "Office rate", {"D0120": "47.00"})
        db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                             fee_schedule_id=wide.id))
        db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                             office_id=office.id,
                                             fee_schedule_id=narrow.id))
        db_session.commit()

        quote = pricing_service.resolve_procedure_fee(
            db_session, db_session._tenant_id, "D0120",
            patient_id=patient.id, office_id=office.id,
        )
        assert quote["fee"] == Decimal("47.00")
        assert quote["fee_schedule_id"] == narrow.id
        assert quote["fee_source"] == "assignment"
        assert quote["specificity"] == 1

    def test_an_assignment_whose_keys_do_not_match_is_not_a_candidate(
        self, db_session, office, patient, codes
    ):
        other = Office(tenant_id=db_session._tenant_id, office_code="FEE2", name="Other")
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)
        sched = _schedule(db_session, "Other office", {"D0120": "999.00"})
        db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                             office_id=other.id, fee_schedule_id=sched.id))
        db_session.commit()

        quote = pricing_service.resolve_procedure_fee(
            db_session, db_session._tenant_id, "D0120",
            patient_id=patient.id, office_id=office.id,
        )
        assert quote["fee_source"] == "code_default"
        assert quote["fee"] == Decimal("10.00")

    def test_equally_specific_disagreement_is_reported_not_hidden(
        self, db_session, office, patient, codes
    ):
        a = _schedule(db_session, "Sched A", {"D0120": "28.00"})
        b = _schedule(db_session, "Sched B", {"D0120": "145.00"})
        for sched in (a, b):
            db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                                 fee_schedule_id=sched.id))
        db_session.commit()

        quote = pricing_service.resolve_procedure_fee(
            db_session, db_session._tenant_id, "D0120",
            patient_id=patient.id, office_id=office.id,
        )
        assert quote["conflicts"], "a rival at the same specificity must be surfaced"
        assert quote["conflicts"][0]["fee"] != quote["fee"]

    def test_inactive_schedule_is_skipped(self, db_session, office, patient, codes):
        sched = _schedule(db_session, "Retired", {"D0120": "60.00"})
        sched.is_active = False
        db_session.add(FeeScheduleAssignment(tenant_id=db_session._tenant_id,
                                             office_id=office.id, fee_schedule_id=sched.id))
        db_session.commit()
        quote = pricing_service.resolve_procedure_fee(
            db_session, db_session._tenant_id, "D0120",
            patient_id=patient.id, office_id=office.id,
        )
        assert quote["fee_source"] == "code_default"

    def test_office_default_and_ucr(self, db_session, office, patient, codes):
        contracted = _schedule(db_session, "Contracted", {"D0120": "44.00"})
        ucr = _schedule(db_session, "UCR", {"D0120": "150.00"})
        office.default_fee_schedule_id = contracted.id
        office.default_ucr_fee_schedule_id = ucr.id
        db_session.commit()

        quote = pricing_service.resolve_procedure_fee(
            db_session, db_session._tenant_id, "D0120",
            patient_id=patient.id, office_id=office.id,
        )
        assert quote["fee"] == Decimal("44.00")
        assert quote["fee_source"] == "office_default"
        assert quote["ucr_fee"] == Decimal("150.00")

    def test_quote_endpoint(self, client, db_session, office, patient, codes):
        sched = _schedule(db_session, "Office rate", {"D0120": "47.00"})
        office.default_fee_schedule_id = sched.id
        db_session.commit()
        r = client.get(f"{PREFIX}/patients/{patient.id}/fee",
                       params={"procedure_code": "D0120", "office_id": office.id})
        assert r.status_code == 200, r.text
        body = r.json()
        assert Decimal(body["fee"]) == Decimal("47.00")
        assert body["fee_schedule_name"] == "Office rate"
        assert body["context"]["office_id"] == office.id

    def test_quote_404s_on_an_unknown_code(self, client, patient, codes):
        r = client.get(f"{PREFIX}/patients/{patient.id}/fee",
                       params={"procedure_code": "D9999999"})
        assert r.status_code == 404


class TestChargeIsPricedServerSide:
    """A charge posted with no fee used to be impossible; a client that fell back
    to ``default_fee`` posted 0.00 on every migrated code."""

    def test_omitted_fee_is_resolved_from_the_schedule(
        self, client, db_session, office, patient, codes
    ):
        sched = _schedule(db_session, "Office rate", {"D0120": "47.00"})
        office.default_fee_schedule_id = sched.id
        db_session.commit()

        provider = Provider(id="FEEPRV", tenant_id=db_session._tenant_id,
                            office_id=office.id, name="Dr Fee")
        db_session.add(provider)
        db_session.commit()

        r = client.post(f"{PREFIX}/patient-procedures", json={
            "id": "PP-FEE-1", "patient_id": patient.id, "procedure_code": "D0120",
            "date_of_service": TODAY.isoformat(), "provider_id": provider.id,
            "office_id": office.id,
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert Decimal(body["fee"]) == Decimal("47.00")
        assert body["fee_schedule_id"] == sched.id

    def test_an_explicit_fee_always_wins(
        self, client, db_session, office, patient, codes
    ):
        sched = _schedule(db_session, "Office rate", {"D0120": "47.00"})
        office.default_fee_schedule_id = sched.id
        provider = Provider(id="FEEPRV2", tenant_id=db_session._tenant_id,
                            office_id=office.id, name="Dr Fee")
        db_session.add(provider)
        db_session.commit()

        r = client.post(f"{PREFIX}/patient-procedures", json={
            "id": "PP-FEE-2", "patient_id": patient.id, "procedure_code": "D0120",
            "date_of_service": TODAY.isoformat(), "provider_id": provider.id,
            "office_id": office.id, "fee": "0.00",
        })
        assert r.status_code == 201, r.text
        # The office is allowed to charge what it decides to charge — including 0.
        assert Decimal(r.json()["fee"]) == Decimal("0.00")


# ── FEE-2: reconstructing the office -> schedule linkage ────────────────────


class TestOfficeFeeScheduleBackfill:
    def _post_history(self, db_session, office, patient, code, fee, n):
        provider = db_session.get(Provider, "HISTPRV")
        if provider is None:
            provider = Provider(id="HISTPRV", tenant_id=db_session._tenant_id,
                                office_id=office.id, name="Dr Hist")
            db_session.add(provider)
            db_session.commit()
        from app.db.models import PatientProcedure
        for i in range(n):
            db_session.add(PatientProcedure(
                id=f"HP-{code}-{fee}-{i}", patient_id=patient.id, procedure_code=code,
                date_of_service=TODAY, provider_id=provider.id, office_id=office.id,
                fee=Decimal(str(fee)), is_archived=False,
            ))
        db_session.commit()

    def test_the_schedule_that_priced_the_charges_is_proposed(
        self, db_session, office, patient, codes, capsys
    ):
        used = _schedule(db_session, "The real one", {"D0120": "44.00"})
        _schedule(db_session, "A decoy", {"D0120": "145.00"})
        self._post_history(db_session, office, patient, "D0120", "44.00", 30)

        backfill_office_schedules(db_session, apply=True, overwrite=False,
                                  office_id=None, min_share=0.6, min_charges=25, top=3)
        db_session.refresh(office)
        assert office.default_fee_schedule_id == used.id

    def test_thin_evidence_is_left_alone_rather_than_guessed(
        self, db_session, office, patient, codes, capsys
    ):
        _schedule(db_session, "The real one", {"D0120": "44.00"})
        self._post_history(db_session, office, patient, "D0120", "44.00", 3)

        backfill_office_schedules(db_session, apply=True, overwrite=False,
                                  office_id=None, min_share=0.6, min_charges=25, top=3)
        db_session.refresh(office)
        assert office.default_fee_schedule_id is None
        assert "inconclusive" in capsys.readouterr().out

    def test_an_existing_default_is_not_overwritten_without_the_flag(
        self, db_session, office, patient, codes, capsys
    ):
        chosen = _schedule(db_session, "Set by a human", {"D0120": "1.00"})
        _schedule(db_session, "History says this", {"D0120": "44.00"})
        office.default_fee_schedule_id = chosen.id
        db_session.commit()
        self._post_history(db_session, office, patient, "D0120", "44.00", 30)

        backfill_office_schedules(db_session, apply=True, overwrite=False,
                                  office_id=None, min_share=0.6, min_charges=25, top=3)
        db_session.refresh(office)
        assert office.default_fee_schedule_id == chosen.id


# ── CHG-10: key2 on the payment / adjustment pickers ────────────────────────


class TestTransactionDefinitionKey2:
    def test_key2_is_set_on_both_groups(self, db_session):
        added, patched = seed_txn_defs(db_session, db_session._tenant_id,
                                       apply=True, overwrite=False)
        assert added > 0 and patched == 0
        rows = db_session.query(Definition).filter(
            Definition.group_code == "payment_method").all()
        assert {r.key2 for r in rows} == {"patient", "insurance"}
        rows = db_session.query(Definition).filter(
            Definition.group_code == "adjustment").all()
        assert {r.key2 for r in rows} == {"production", "collection"}

    def test_it_patches_an_existing_row_that_has_no_key2(self, db_session):
        """The whole point: the add-only seeder could never fix these rows."""
        db_session.add(Definition(tenant_id=db_session._tenant_id,
                                  group_code="adjustment", key1="write_off",
                                  description="Write Off", is_active=True))
        db_session.commit()
        _added, patched = seed_txn_defs(db_session, db_session._tenant_id,
                                        apply=True, overwrite=False)
        assert patched == 1
        row = db_session.query(Definition).filter(
            Definition.group_code == "adjustment", Definition.key1 == "write_off").one()
        assert row.key2 == "production"

    def test_a_practice_edited_label_is_never_overwritten(self, db_session):
        db_session.add(Definition(tenant_id=db_session._tenant_id,
                                  group_code="adjustment", key1="courtesy",
                                  description="Our house discount", is_active=True))
        db_session.commit()
        seed_txn_defs(db_session, db_session._tenant_id, apply=True, overwrite=False)
        row = db_session.query(Definition).filter(
            Definition.group_code == "adjustment", Definition.key1 == "courtesy").one()
        assert row.description == "Our house discount"
        assert row.key2 == "production"

    def test_dry_run_writes_nothing(self, db_session):
        added, _ = seed_txn_defs(db_session, db_session._tenant_id,
                                 apply=False, overwrite=False)
        assert added > 0
        assert db_session.query(Definition).count() == 0

    def test_the_pickers_expose_key2(self, client, db_session):
        seed_txn_defs(db_session, db_session._tenant_id, apply=True, overwrite=False)
        r = client.get(f"{PREFIX}/definitions", params={"group_code": "payment_method"})
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert all(row["key2"] for row in items)


# ── PROV-3: provider role normalisation ─────────────────────────────────────


class TestProviderRole:
    def test_canonical_role_fixes_casing_and_the_known_misspelling(self):
        assert canonical_role("Dentist") == "dentist"
        assert canonical_role("Hygenist") == "hygienist"
        assert canonical_role("  RDH ") == "hygienist"
        assert canonical_role("") is None

    def test_an_unknown_role_is_preserved_not_forced(self):
        """A practice may use a title this list has never heard of; relabelling
        it silently is worse than an unfamiliar string."""
        assert canonical_role("Anesthesiologist") == "anesthesiologist"

    def test_provider_kind_falls_back_to_the_licence_title(self):
        assert provider_kind("staff", "RDH") == "hygienist"
        assert provider_kind("dentist", None) == "dentist"

    def test_role_is_canonicalised_on_write(self, client, db_session, office):
        r = client.post(f"{PREFIX}/providers", json={
            "id": "ROLE1", "tenant_id": db_session._tenant_id, "office_id": office.id,
            "name": "Dr Typo", "role": "Hygenist",
        })
        assert r.status_code == 201, r.text
        assert r.json()["role"] == "hygienist"
        assert r.json()["provider_kind"] == "hygienist"

    def test_patch_canonicalises_too(self, client, db_session, office):
        client.post(f"{PREFIX}/providers", json={
            "id": "ROLE2", "tenant_id": db_session._tenant_id, "office_id": office.id,
            "name": "Dr Case", "role": "dentist"})
        r = client.patch(f"{PREFIX}/providers/ROLE2", json={"role": "Dentist"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "dentist"

    def test_backfill_repairs_migrated_rows(self, db_session, office, capsys):
        for pid, role in (("MIG1", "Dentist"), ("MIG2", "Hygenist"), ("MIG3", "dentist")):
            db_session.add(Provider(id=pid, tenant_id=db_session._tenant_id,
                                    office_id=office.id, name=pid, role=role))
        db_session.commit()

        normalize_roles(db_session, apply=True, tenant_id=db_session._tenant_id)
        assert db_session.get(Provider, "MIG1").role == "dentist"
        assert db_session.get(Provider, "MIG2").role == "hygienist"

    def test_backfill_dry_run_writes_nothing(self, db_session, office, capsys):
        db_session.add(Provider(id="MIG4", tenant_id=db_session._tenant_id,
                                office_id=office.id, name="MIG4", role="Hygenist"))
        db_session.commit()
        normalize_roles(db_session, apply=False, tenant_id=db_session._tenant_id)
        assert db_session.get(Provider, "MIG4").role == "Hygenist"

    def test_providers_are_filterable_by_role(self, client, db_session, office):
        for pid, role in (("F1", "dentist"), ("F2", "hygienist")):
            db_session.add(Provider(id=pid, tenant_id=db_session._tenant_id,
                                    office_id=office.id, name=pid, role=role))
        db_session.commit()
        r = client.get(f"{PREFIX}/providers", params={"role": "hygienist"})
        assert r.status_code == 200, r.text
        assert [p["id"] for p in r.json()["items"]] == ["F2"]
