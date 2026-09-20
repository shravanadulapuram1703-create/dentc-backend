"""The pricing vocabulary — one home for every word the fee hierarchy uses.

Why this module exists
----------------------
Before it, ``fee_schedules.fee_type`` was a free ``String(50)`` with **three
incompatible vocabularies** writing to it: the Denticon migration wrote
``ucr``/``plan``/``carrier`` (``s09``), Fee Schedule Setup's datalist suggested
``carrier``/``plan``/``office``/``provider``/``specialty``, and Office Setup wrote
``STANDARD``/``UCR`` in caps — and nothing validated any of them. ``fee_source``
was likewise a set of bare string literals scattered across ``pricing_service``
and ``estimate_service``. A vocabulary that lives in one place is what lets the
seeder, the resolver, the CRUD guards, the tests and
``GET /fee-schedules/metadata`` agree by construction.

What the words mean (settled from the Denticon export, not invented)
--------------------------------------------------------------------
``FEETYPE`` in ``FeeScheH.txt`` is an **assignment mode**, not a price kind: the
DESCR column is self-documenting — ``0`` = "UCR -Excel Dental" (unbound, chosen by
an office or a patient), ``2`` = "EXAMPLE -- Medicaid - Assign To Plan (SAMPLE)",
``3`` = "EXAMPLE -- PPO - Assign To Carrier (SAMPLE)". There is no ``FEETYPE=1``
in the data at all, which is why ``s09``'s ``{"1": "ucr", ...}`` map left 12 of 13
schedules mislabelled ``ucr``.

``INSAMT`` (``fee_schedule_entries.insurance_fee``) is a **fixed dollar amount the
plan pays for the code**, and it exists only on assign-to-plan (Medicaid / DHMO /
capitation) lists: it is non-zero on 356 of 13,488 legacy detail rows and 354 of
those sit on the two ``FEETYPE=2`` schedules, where ``PATAMT`` is blank. It is
never a percentage — percentages live only in ``insurance_coverage_rules`` — which
is why :data:`PRICING_MODELS` is a property of the *schedule*, and why the entry
CRUD refuses ``insurance_fee`` on a percentage list.

Nothing here reads the database. :mod:`app.services.pricing_service` owns the
walk, :mod:`app.services.estimate_service` owns the arithmetic, and this module
owns only the names they both use.
"""

from __future__ import annotations

from typing import Literal

# ── Fee schedule kind (``fee_schedules.fee_type``) ───────────────────────────
#: The four kinds a price list can be, in the legacy words staff already read.
#: **Advisory, not a capability**: it drives picker filters, the "Plan Pays"
#: column and the labels — it does *not* gate which pointer may reference the
#: schedule. One list is legitimately both an office's UCR list and the list its
#: patients are registered on (legacy 109 is exactly that for 12 offices and
#: 50,604 patients), so requiring a separate "standard" twin would mean
#: maintaining two copies of the same 936 prices forever.
FEE_TYPES: tuple[tuple[str, str], ...] = (
    ("ucr", "Office UCR list (what the practice normally charges)"),
    ("standard", "Practice / patient price list"),
    ("plan", "Assign to Plan (a specific insurance plan prices from this)"),
    ("carrier", "Assign to Carrier (a carrier's contracted / PPO fees)"),
)
FEE_TYPE_CODES: tuple[str, ...] = tuple(code for code, _ in FEE_TYPES)
FeeType = Literal["ucr", "standard", "plan", "carrier"]
DEFAULT_FEE_TYPE = "standard"

#: Denticon ``FeeScheH.FEETYPE`` to our ``fee_type``. ``0`` is *unbound*, which is
#: a practice/patient list unless the schedule is some office's ``Office.FEEID``
#: (the backfill promotes those to ``ucr`` by office membership, not by FEETYPE —
#: FEETYPE carries no UCR information).
LEGACY_FEETYPE_MAP: dict[str, str] = {"0": "standard", "2": "plan", "3": "carrier"}

#: Values the un-validated API and the two frontends actually wrote, mapped onto
#: the enum. Used by the normalisation step of the Alembic revision and by the
#: backfill script, so a re-run is idempotent.
LEGACY_FEE_TYPE_ALIASES: dict[str, str] = {
    "ucr": "ucr",
    "standard": "standard",
    "plan": "plan",
    "carrier": "carrier",
    # Office Setup wrote these in caps; Fee Schedule Setup's datalist offered the
    # rest. None of them describe a distinct kind of list.
    "office": "standard",
    "provider": "standard",
    "specialty": "standard",
    "": "standard",
}


def canonical_fee_type(value: str | None) -> str:
    """Fold any historical spelling onto the enum. Unknown becomes ``standard``."""
    key = (value or "").strip().lower()
    return LEGACY_FEE_TYPE_ALIASES.get(key, DEFAULT_FEE_TYPE)


# ── How a payer pays (``fee_schedules.pricing_model``) ───────────────────────
#: ``percentage`` — the list states an allowed amount and the *plan's* coverage
#: percentage splits it (PPO / indemnity / Premier: every migrated plan).
#: ``copay`` — the list itself states both dollar parts: ``patient_fee`` is the
#: patient's copay and ``insurance_fee`` is what the plan pays (Medicaid / DHMO /
#: capitation, Denticon "Assign To Plan"). A copay list is only reachable through
#: a payer tier, which the DB CHECK enforces as
#: ``pricing_model = 'percentage' OR fee_type IN ('plan', 'carrier')``.
PRICING_MODELS: tuple[tuple[str, str], ...] = (
    ("percentage", "Plan pays a percentage of this fee"),
    ("copay", "Plan pays a fixed amount per code (patient owes a fixed copay)"),
)
PRICING_MODEL_CODES: tuple[str, ...] = tuple(code for code, _ in PRICING_MODELS)
PricingModel = Literal["percentage", "copay"]
DEFAULT_PRICING_MODEL = "percentage"
#: Only these kinds may carry ``pricing_model='copay'`` (mirrors the CHECK).
COPAY_CAPABLE_FEE_TYPES: frozenset[str] = frozenset({"plan", "carrier"})


def canonical_pricing_model(value: str | None) -> str:
    key = (value or "").strip().lower()
    return key if key in PRICING_MODEL_CODES else DEFAULT_PRICING_MODEL


def allows_plan_pays(fee_type: str | None, pricing_model: str | None) -> bool:
    """May an entry on this schedule carry ``insurance_fee`` ("Plan Pays")?"""
    return (
        canonical_pricing_model(pricing_model) == "copay"
        and canonical_fee_type(fee_type) in COPAY_CAPABLE_FEE_TYPES
    )


# ── Where a resolved fee came from (``*.fee_source``) ────────────────────────
#: Stamped on every priced row so "why is this charge 44.00?" is answerable
#: forever. ``migrated`` is the 1.37M rows the Denticon import wrote;
#: ``client_legacy`` is the compatibility window in which a browser-computed fee
#: is still accepted (recorded and counted, never silently trusted).
FEE_SOURCES: tuple[str, ...] = (
    "override",
    "client_legacy",
    "assignment_plan",
    "assignment_carrier",
    "patient_schedule",
    "assignment_provider",
    "office_default",
    "office_ucr",
    "plan_item",
    "unpriced",
    "migrated",
)
#: Retired spellings the old resolver emitted, kept so a reader of historical
#: rows (or a stale client) is not surprised. ``plan_schedule`` was the
#: ``fee_schedules.ins_plan_id`` tier (NULL on every row ever) and
#: ``code_default`` was ``procedure_codes.default_fee`` (>0 on 3 of 1,122 codes).
RETIRED_FEE_SOURCES: tuple[str, ...] = ("assignment", "plan_schedule", "code_default")


# ── Assignment precedence ────────────────────────────────────────────────────
#: The keys that make an assignment *apply to a payer or a person*, most
#: significant first. Candidates are compared **lexicographically on this
#: vector**, never on a count of set keys and never on a weight sum: a row keyed
#: on the plan alone must beat a row keyed on carrier + office, because the plan
#: is the narrower statement. (Counting keys inverted that, and summing weights
#: made ``carrier+provider`` outrank ``plan+specialty`` — both silently wrong.)
ASSIGNMENT_RANK_KEYS: tuple[str, ...] = ("ins_plan_id", "carrier_id", "provider_id", "specialty_id")
#: These only *narrow* who a row applies to; they never raise its priority and
#: they cannot stand alone. A practice-wide default is an office pointer
#: (Office Setup), not an assignment row — that is what the eight all-NULL rows
#: in the migrated tenant taught us.
ASSIGNMENT_SCOPE_KEYS: tuple[str, ...] = ("office_id", "office_group_id")
ASSIGNMENT_KEYS: tuple[str, ...] = ASSIGNMENT_RANK_KEYS + ASSIGNMENT_SCOPE_KEYS


def _key_is_set(row: object, attr: str) -> int:
    value = row.get(attr) if isinstance(row, dict) else getattr(row, attr, None)
    return 0 if value is None or value == "" else 1


def assignment_sort_key(row: object) -> tuple:
    """Sort key for one assignment row; best first when sorted ``reverse=True``.

    ``(plan?, carrier?, provider?, specialty?, scope-count, id)`` — the rank
    vector dominates, then a more narrowly scoped row wins among equals, then the
    newest row. Two rows can only tie on the whole vector if they set an identical
    key tuple, which the unique index refuses at authoring time.
    """
    return (
        *(_key_is_set(row, key) for key in ASSIGNMENT_RANK_KEYS),
        sum(_key_is_set(row, key) for key in ASSIGNMENT_SCOPE_KEYS),
        (row.get("id") if isinstance(row, dict) else getattr(row, "id", 0)) or 0,
    )


def fee_source_for_assignment(row: object) -> str:
    """Which ``fee_source`` an assignment win is reported as."""
    if _key_is_set(row, "ins_plan_id"):
        return "assignment_plan"
    if _key_is_set(row, "carrier_id"):
        return "assignment_carrier"
    return "assignment_provider"


def has_assignment_target(row_or_payload: object) -> bool:
    """True when at least one *payer or person* key is set.

    Scope-only rows (office / office group) are refused: they would be a second
    way to say "the default for this office", competing with the office pointer
    that a different operator maintains on a different screen.
    """
    return any(_key_is_set(row_or_payload, key) for key in ASSIGNMENT_RANK_KEYS)


# ── Coverage tiers ───────────────────────────────────────────────────────────
#: ``patient_insurance.insurance_type`` values, in coordination-of-benefits
#: order. The fee is always the **primary** payer's allowed amount; secondary and
#: tertiary plans change only the split.
COVERAGE_TIERS: tuple[str, ...] = ("primary", "secondary", "tertiary", "quaternary")
#: ``treatment_plan_insurance_details.billing_order`` and the ledger's per-tier
#: columns, keyed by position in :data:`COVERAGE_TIERS`. The legacy migration
#: mis-keyed that table because this vocabulary was never written down.
TIER_KEYS: tuple[str, ...] = ("1", "2", "3", "4")
#: ``legacy_plan_type`` that is *not* dental. A medical slot never prices dental.
MEDICAL_PLAN_TYPE = "M"


# ── What to do with a code no reachable list prices ──────────────────────────
#: Per office (``offices.unpriced_charge_policy``). ``flag`` is the default for a
#: migrated tenant: 206 codes that appear on real historical charges have no entry
#: with ``patient_fee > 0`` on *any* of the 47 schedules, so refusing on day one
#: would be a chair-side outage. An office flips to ``refuse`` once its "codes
#: needing a price" queue in the pricing-health report is empty.
UNPRICED_POLICIES: tuple[tuple[str, str], ...] = (
    ("flag", "Post at 0.00, mark it unpriced and list it for Setup"),
    ("refuse", "Refuse the charge until the code is priced"),
)
UNPRICED_POLICY_CODES: tuple[str, ...] = tuple(code for code, _ in UNPRICED_POLICIES)
DEFAULT_UNPRICED_POLICY = "flag"


# ── Machine-readable signals (never invent these at a call site) ─────────────
#: Non-fatal facts about how a price was reached. Every one of these is something
#: an operator can fix in Setup, so each is also a pricing-health finding.
WARNING_CODES: tuple[tuple[str, str], ...] = (
    ("entry_predates_service_date",
     "Priced from the earliest dated fee; none was in force on the service date"),
    ("entry_not_yet_effective",
     "The only fees on this list start after the service date"),
    ("code_missing_on_bound_schedule",
     "The plan/carrier list that applies does not price this code"),
    ("zero_fee_entry_skipped", "A list priced this code at 0.00 and was skipped"),
    ("office_without_ucr",
     "The office has no UCR list, so no UCR fee or write-off can be shown"),
    ("ucr_unpriced", "The office UCR list does not price this code"),
    ("patient_schedule_inactive", "The patient's fee schedule is inactive and was skipped"),
    ("payer_schedule_without_coverage",
     "Priced from a payer list although the patient has no active coverage"),
    ("assignment_conflict", "Two assignments of equal precedence price this code differently"),
    ("assignment_ignored_no_target",
     "An assignment with no plan/carrier/provider/specialty key was ignored"),
    ("capitation_plan_without_copay_binding",
     "This plan expects a copay list but none is bound to it"),
    ("unpriced", "No reachable fee schedule prices this code"),
    ("frequency_limit_unverified",
     "A frequency limitation applies but history was not checked"),
    ("secondary_not_estimated",
     "The patient has a secondary plan that was not included in this estimate"),
)
WARNING_CODE_KEYS: tuple[str, ...] = tuple(code for code, _ in WARNING_CODES)

#: ``details.code`` on the 4xx responses the pricing surfaces raise, so the
#: frontend can branch without string-matching a message.
ERROR_CODES: dict[str, str] = {
    "procedure_unpriced": "No reachable fee schedule prices this code (office policy: refuse)",
    "fee_not_accepted": "A fee may not be supplied; use fee_override with a reason",
    "fee_override_forbidden": "This user may not override a resolved fee",
    "fee_override_reason_required": "An override needs a reason",
    "insurance_fee_not_allowed": "Plan Pays is only valid on a copay price list",
    "pricing_model_requires_payer_type":
        "A copay price list must be an Assign-to-Plan or Assign-to-Carrier type",
    "fee_entry_needs_amount":
        "A fee entry needs a patient fee, a Plan Pays amount, or the no-charge flag",
    "fee_entry_negative": "Fees may not be negative",
    "fee_entry_duplicate": "This list already prices that code from that date",
    "assignment_needs_target": "An assignment needs a plan, carrier, provider or specialty",
    "assignment_duplicate_target": "Another assignment already binds that exact target",
    "assignment_schedule_invalid": "The fee schedule is inactive or belongs to another tenant",
    "fee_schedule_in_use": "The fee schedule is still referenced; re-point those first",
    "fee_type_has_plan_pays": "Entries on this list carry Plan Pays amounts; clear them first",
    "office_schedule_invalid": "The fee schedule is inactive or belongs to another tenant",
    "patient_schedule_invalid": "The fee schedule is inactive or belongs to another tenant",
    "office_not_configured_for_pricing": "The office has no UCR fee schedule",
    "server_owned_field": "This field is computed by the server and may not be sent",
}


# ── The precedence card (published, so the UI cannot paraphrase it wrong) ────
#: One row per tier of ``pricing_service.resolve_procedure_fee``, in order, with
#: the screen that owns the input. ``GET /fee-schedules/metadata`` serves this
#: verbatim and the Setup landing page renders it, so a front-desk trainer and the
#: engine can never drift.
PRECEDENCE_CARD: tuple[dict[str, str], ...] = (
    {"tier": "0", "fee_source": "override",
     "source": "An explicit, reasoned override on the line",
     "owned_by": "Charge entry (permission required)"},
    {"tier": "1", "fee_source": "assignment_plan",
     "source": "A fee schedule assigned to the patient's primary plan",
     "owned_by": "Setup - Fee Schedules - Assignments"},
    {"tier": "2", "fee_source": "assignment_carrier",
     "source": "A fee schedule assigned to that plan's carrier",
     "owned_by": "Setup - Fee Schedules - Assignments"},
    {"tier": "3", "fee_source": "patient_schedule",
     "source": "The patient's own fee schedule",
     "owned_by": "Patient - Add/Edit Patient"},
    {"tier": "4", "fee_source": "assignment_provider",
     "source": "A fee schedule assigned to the provider or specialty",
     "owned_by": "Setup - Fee Schedules - Assignments"},
    {"tier": "5", "fee_source": "office_default",
     "source": "The office's default price list",
     "owned_by": "Setup - Offices - Info"},
    {"tier": "6", "fee_source": "office_ucr",
     "source": "The office's UCR list (also the source of the UCR fee and the write-off)",
     "owned_by": "Setup - Offices - Info"},
    {"tier": "7", "fee_source": "unpriced",
     "source": "Nothing prices this code - the office's unpriced policy decides",
     "owned_by": "Setup - Fee Schedules (add the code to a list)"},
)

#: The one-line rules that make the card deterministic. Published alongside it.
PRECEDENCE_NOTES: tuple[str, ...] = (
    "Plan beats carrier beats provider beats specialty. Office and office group only narrow "
    "who an assignment applies to - they never raise its priority and cannot stand alone.",
    "The fee is always the primary dental payer's allowed amount; secondary and tertiary "
    "plans change only the split.",
    "Within a list, the fee in force on the date of service wins; a fee that starts after "
    "that date is never used.",
    "A 0.00 fee is treated as 'not priced' unless the entry is explicitly marked no-charge.",
    "The UCR fee always comes from the office's UCR list, whichever list priced the fee.",
    "Whatever wins is stamped on the charge. Editing a fee schedule never re-prices posted history.",
)


def metadata() -> dict:
    """The whole vocabulary, shaped for ``GET /fee-schedules/metadata``."""
    return {
        "fee_types": [{"code": c, "label": label} for c, label in FEE_TYPES],
        "pricing_models": [{"code": c, "label": label} for c, label in PRICING_MODELS],
        "fee_sources": list(FEE_SOURCES),
        "unpriced_policies": [{"code": c, "label": label} for c, label in UNPRICED_POLICIES],
        "coverage_tiers": list(COVERAGE_TIERS),
        "assignment_rank_keys": list(ASSIGNMENT_RANK_KEYS),
        "assignment_scope_keys": list(ASSIGNMENT_SCOPE_KEYS),
        "copay_capable_fee_types": sorted(COPAY_CAPABLE_FEE_TYPES),
        "precedence": [dict(row) for row in PRECEDENCE_CARD],
        "precedence_notes": list(PRECEDENCE_NOTES),
        "warnings": [{"code": c, "label": label} for c, label in WARNING_CODES],
        "error_codes": dict(ERROR_CODES),
    }
