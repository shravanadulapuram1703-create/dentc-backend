"""The pricing vocabulary and the schema that enforces it (R1).

These tests pin the two things that have no other guard:

* the ``fee_vocab`` constants and the literals the Alembic revision duplicates
  (models and migrations in this repo never import from ``app.services``, so the
  same words exist in two files and could drift apart silently);
* the **precedence rule**, which is the one piece of the design that is easy to
  write in a way that looks right and inverts itself. Counting an assignment's set
  keys makes ``{carrier, office}`` (two keys) outrank ``{plan}`` (one key), and
  summing per-key weights makes ``{carrier, provider}`` outrank
  ``{plan, specialty}``. Both are wrong: a plan is the narrowest statement a
  practice can make about a price, so it must win outright.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.db.base import Base
from app.services import fee_vocab as v

REVISION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "d4f1a9c7b3e2_pricing_hierarchy_r1.py"
)


def _load_revision():
    spec = importlib.util.spec_from_file_location("pricing_r1", REVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Row:
    """A stand-in for a ``fee_schedule_assignments`` row."""

    def __init__(self, id: int, **keys):  # noqa: A002
        self.id = id
        for attr in v.ASSIGNMENT_KEYS:
            setattr(self, attr, None)
        for attr, value in keys.items():
            setattr(self, attr, value)


def _best(*rows):
    return sorted(rows, key=v.assignment_sort_key, reverse=True)[0]


# ── the vocabulary and the migration must agree ──────────────────────────────


def test_revision_literals_match_the_vocabulary():
    rev = _load_revision()
    assert rev._FEE_TYPES == v.FEE_TYPE_CODES
    assert rev._PRICING_MODELS == v.PRICING_MODEL_CODES
    assert rev._UNPRICED_POLICIES == v.UNPRICED_POLICY_CODES
    assert rev._RANK_KEYS == v.ASSIGNMENT_RANK_KEYS


def test_revision_fee_type_aliases_agree_with_canonical_fee_type():
    rev = _load_revision()
    for alias, canonical in rev._FEE_TYPE_ALIASES.items():
        assert v.canonical_fee_type(alias) == canonical


def test_every_check_the_revision_creates_names_its_table():
    rev = _load_revision()
    assert {name for name, _ in rev._CHECKS} == set(rev._CHECK_TABLES)
    # A CHECK whose name does not start with the convention prefix would be dropped
    # by a different name than it was created with.
    for name, _ in rev._CHECKS:
        assert name.startswith(f"ck_{rev._CHECK_TABLES[name]}_")


# ── precedence: the rule the design turns on ─────────────────────────────────


def test_plan_beats_carrier_even_when_the_carrier_row_sets_more_keys():
    plan = _Row(1, ins_plan_id=7)
    carrier_and_office = _Row(99, carrier_id=3, office_id=4)
    assert _best(plan, carrier_and_office) is plan


def test_rank_order_is_plan_then_carrier_then_provider_then_specialty():
    rows = [
        _Row(1, ins_plan_id=7),
        _Row(2, carrier_id=3),
        _Row(3, provider_id="PRV-1"),
        _Row(4, specialty_id="GP"),
    ]
    ranked = sorted(rows, key=v.assignment_sort_key, reverse=True)
    assert [r.id for r in ranked] == [1, 2, 3, 4]


def test_a_scope_key_narrows_among_equals_but_never_promotes():
    carrier = _Row(10, carrier_id=3)
    carrier_in_one_office = _Row(11, carrier_id=3, office_id=4)
    # Narrower wins when the rank vector ties ...
    assert _best(carrier, carrier_in_one_office) is carrier_in_one_office
    # ... but cannot lift a carrier row over a plan row.
    plan = _Row(12, ins_plan_id=7)
    assert _best(carrier_in_one_office, plan) is plan


def test_newest_row_wins_only_when_the_key_shape_is_identical():
    assert _best(_Row(5, carrier_id=3), _Row(9, carrier_id=3)).id == 9


@pytest.mark.parametrize(
    "row, expected",
    [
        (_Row(1, ins_plan_id=7), True),
        (_Row(2, carrier_id=3), True),
        (_Row(3, provider_id="PRV-1"), True),
        (_Row(4, specialty_id="GP"), True),
        # Scope-only rows are refused: an office-wide default has exactly one home,
        # the office pointer, and two mechanisms for it is the confusion this
        # design removes.
        (_Row(5, office_id=4), False),
        (_Row(6, office_group_id=2), False),
        (_Row(7), False),
    ],
)
def test_has_assignment_target(row, expected):
    assert v.has_assignment_target(row) is expected


def test_has_assignment_target_accepts_a_payload_dict():
    assert v.has_assignment_target({"carrier_id": 3}) is True
    assert v.has_assignment_target({"office_id": 3}) is False


@pytest.mark.parametrize(
    "row, expected",
    [
        (_Row(1, ins_plan_id=7, carrier_id=3), "assignment_plan"),
        (_Row(2, carrier_id=3, office_id=1), "assignment_carrier"),
        (_Row(3, provider_id="PRV-1"), "assignment_provider"),
        (_Row(4, specialty_id="GP"), "assignment_provider"),
    ],
)
def test_fee_source_reported_for_an_assignment_win(row, expected):
    assert v.fee_source_for_assignment(row) == expected
    assert expected in v.FEE_SOURCES


# ── plan-pays is a copay-list concept only ──────────────────────────────────


@pytest.mark.parametrize(
    "fee_type, pricing_model, allowed",
    [
        ("plan", "copay", True),
        ("carrier", "copay", True),
        # A percentage list's share comes from the plan's coverage rules, so a
        # "Plan Pays" dollar amount there has no meaning and no reader.
        ("plan", "percentage", False),
        ("ucr", "copay", False),
        ("standard", "copay", False),
    ],
)
def test_allows_plan_pays(fee_type, pricing_model, allowed):
    assert v.allows_plan_pays(fee_type, pricing_model) is allowed


def test_copay_capable_types_are_exactly_the_payer_bound_ones():
    assert v.COPAY_CAPABLE_FEE_TYPES == {"plan", "carrier"}


# ── published metadata ──────────────────────────────────────────────────────


def test_metadata_is_json_serialisable_and_self_consistent():
    meta = v.metadata()
    json.dumps(meta)  # the endpoint returns this verbatim
    assert [row["fee_source"] for row in v.PRECEDENCE_CARD][:3] == [
        "override", "assignment_plan", "assignment_carrier",
    ]
    # Every tier names a real fee_source, and every tier says who owns its input —
    # the card is the answer to "which of the three screens do I go to".
    for row in v.PRECEDENCE_CARD:
        assert row["fee_source"] in v.FEE_SOURCES
        assert row["owned_by"]
        assert row["source"]
    assert set(v.WARNING_CODE_KEYS) == {code for code, _ in v.WARNING_CODES}


def test_retired_fee_sources_are_not_also_current():
    assert not set(v.RETIRED_FEE_SOURCES) & set(v.FEE_SOURCES)


# ── schema invariants the engine relies on ──────────────────────────────────


def test_a_fee_list_can_hold_the_same_code_at_two_dates():
    """The uniqueness key must include the date, or dated pricing is impossible.

    The Denticon schema shipped a unique on ``(fee_schedule_id, procedure_code)``,
    so a second, later-dated fee for a code was refused by the database — which is
    why Setup had to overwrite prices in place and lose the old one.
    """
    entries = Base.metadata.tables["fee_schedule_entries"]
    uniques = [
        tuple(c.name for c in con.columns)
        for con in entries.constraints
        if con.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("fee_schedule_id", "procedure_code", "effective_date") in uniques
    assert ("fee_schedule_id", "procedure_code") not in uniques
    # Half of the key: a nullable column would let Postgres treat NULLs as
    # distinct and re-admit the duplicates the key exists to prevent.
    assert entries.c.effective_date.nullable is False


def test_fee_schedule_entries_are_tenant_scoped():
    """``CRUDBase`` only scopes models that carry ``tenant_id``; without it the
    per-id routes on this table were readable *and writable* across tenants."""
    assert "tenant_id" in Base.metadata.tables["fee_schedule_entries"].c


def test_priced_rows_carry_the_provenance_the_snapshot_needs():
    for table in ("patient_procedures", "treatment_plan_items"):
        columns = Base.metadata.tables[table].c
        for column in (
            "fee_schedule_id", "fee_source", "fee_effective_date", "ucr_fee",
            "coverage_pct", "estimated_deductible", "sec_insurance_estimate",
        ):
            assert column in columns, f"{table}.{column}"


def test_pricing_table_identifiers_fit_postgres():
    """Postgres caps identifiers at 63 characters and SQLAlchemy raises rather
    than truncating, so an over-long constraint name is a migration that cannot
    run. (The wider schema has pre-existing offenders; this pins the new tables.)"""
    for table_name in (
        "fee_schedules", "fee_schedule_entries", "fee_schedule_assignments",
        "procedure_fee_provenance",
    ):
        table = Base.metadata.tables[table_name]
        names = [str(c.name) for c in table.constraints if c.name]
        names += [str(i.name) for i in table.indexes]
        too_long = [n for n in names if len(n) > 63]
        assert not too_long, f"{table_name}: {too_long}"
