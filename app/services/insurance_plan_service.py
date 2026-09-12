"""Insurance Plan Details wizard — the plan-level engine behind the four tabs
(PLAN · BENEFITS · COVERAGE & LIMITATIONS · FREQ LIMITATION CODE GRP).

Backs ``docs/patient-insurance/insurance_plan_details_backend_devreport.md``
(PLAN-DTL-1 … PLAN-DTL-9).

What lives here and why
-----------------------
* **The catalogues** (PLAN-DTL-4, and the seeding half of PLAN-DTL-6).
  ``freq_limit`` on a coverage rule is a 1-based ordinal into Denticon's
  FREQUENCYLIMITATIONS list — migrated rows store ``"6"`` meaning "Once per
  Benefit Year" — and nothing in the API documented that. The list is stated
  here **once** (:data:`FREQUENCY_LIMITATIONS`) and published at
  ``GET /insurance-plans/metadata`` together with the default coverage table
  and the plan-field vocabularies, so the wizard can delete its hard-coded
  fallbacks. The same constants seed ``definitions`` for the 42 tenants that
  have none of these groups (only the migrated tenant does).

* **Typed limits** (PLAN-DTL-5). ``age_min``/``age_max``/``wait_months``/
  ``freq_limit`` are the canonical columns; the legacy ``age_limit`` /
  ``wait_period`` strings are *derived mirrors* so an older client keeps
  reading (and writing) them through the cutover.

* **Tenancy**. ``insurance_coverage_rules`` has no ``tenant_id`` and was exposed
  through the generic CRUD, which only scopes models that carry the column —
  so any authenticated tenant could read or edit any other tenant's coverage
  table by id. :class:`InsuranceCoverageRuleCRUD` scopes every access through
  the owning plan.

* **The FREQGRP convention** (PLAN-DTL-2). The frontend had nowhere to put the
  FREQ tab, so it wrote reserved-shape coverage rows (``category="FREQGRP"``,
  ``start_code="FQ01"``, whole-mouth as ``age_limit="WM"``). Those rows now
  live in ``insurance_plan_frequency_groups`` and the coverage write path
  refuses the shape (422 ``frequency_group_row_not_coverage``) so it cannot
  silently re-accumulate where every coverage consumer has to know to skip it.

* **Bulk replace / copy** (PLAN-DTL-8 + "COPY FROM EXISTING"). A fresh plan is
  ~30 sequential POSTs that can half-fail; ``PUT …/coverage-rules`` reconciles
  the whole table in one transaction and ``POST …/copy-from/{source}`` copies
  another plan's table (and, optionally, its plan-level fields) server-side.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit_context, concurrency
from app.core.exceptions import LockedError, NotFoundError, ValidationError
from app.core.logging import user_id_ctx
from app.crud.base import CRUDBase
from app.db.models import (
    Definition,
    InsuranceCoverageRule,
    InsurancePlan,
    InsurancePlanFrequencyGroup,
)
from app.services import permission_service

#: EDIT-PLAN-9: what the legacy dialog shows for a blank field — and, since
#: Alembic ``7f483f6833a7``, what a NULL column was backfilled to and what a
#: new row defaults to (``InsurancePlan`` column defaults). Published on
#: ``GET /insurance-plans/metadata → plan_field_defaults``.
PLAN_FIELD_DEFAULTS: dict[str, Any] = {
    "fees_to_print": "office_ucr",
    "claim_option": "submit",
    "form_to_print": "ADA2024",
    "network_type": "unknown",
    "noa_only": False,
    # The legacy dialog defaults this **on**; the first migration wrote false
    # and the Denticon export has no column, so migrated rows are not rewritten.
    "lifetime_ortho_benefits": True,
}

# ── PLAN-DTL-4: the frequency-limitation ordinals ────────────────────────────
#: ``(ordinal, label, key1, key2)`` — the legacy FREQUENCYLIMITATIONS list in
#: its legacy order (``definitions.legacy_id`` 325 … 337). ``ordinal`` is what
#: ``insurance_coverage_rules.freq_limit`` and
#: ``insurance_plan_frequency_groups.freq_limit`` store; ``0``/NULL means
#: "No Limitation". ``key1``/``key2`` are the "Once"/"6" fragments the migrated
#: definitions rows carry, kept so a tenant's own rows can be matched back.
FREQUENCY_LIMITATIONS: tuple[tuple[int, str, str, str | None], ...] = (
    (1, "Once every 6 month of Date of Service", "Once", "6"),
    (2, "Once every 3 years of Date of Service", "Once", "3"),
    (3, "Twice per Last 12 months of Date of Service", "Twice", "12"),
    (4, "Twice per Benefit Year", "Twice", "1"),
    (5, "Four per Benefit Year", "Four", "1"),
    (6, "Once per Benefit Year", "Once", "1"),
    (7, "Once per Two Benefit Years", "Once", "2"),
    (8, "Once per Three Benefit Years", "Once", "3"),
    (9, "Once per Five Benefit Years", "Once", "5"),
    (10, "Once per Seven Benefit Years", "Once", "7"),
    (11, "Once per Ten Benefit Years", "Once", "10"),
    (12, "Once per Lifetime", "Once", None),
    (13, "Other - See plan notes", "", None),
)
NO_LIMITATION_LABEL = "No Limitation"

# ── The default COVERAGE & LIMITATIONS table ─────────────────────────────────
#: ``(category code, label, default coverage %)`` — the DEFCOVERAGE catalogue.
#: The codes are the same Denticon coverage categories the estimate engine
#: matches on (``coverage_category_service``); the percentages are the legacy
#: "Change coverage table" defaults (``definitions.key2``).
DEFAULT_COVERAGE_TABLE: tuple[tuple[str, str, int], ...] = (
    ("01", "Diagnostic", 100),
    ("01A", "Diagnostic:  X-Rays", 100),
    ("01B", "Diagnostic: Panoramic X-Rays", 100),
    ("01C", "Diagnostic:  X-Rays - PAs", 100),
    ("01D", "Diagnostic:  X-Rays - Bitewings", 100),
    ("01E", "Diagnostic:  X-Rays - Cone Beam", 100),
    ("02", "Preventive", 100),
    ("02A", "Preventive:  Sealants", 100),
    ("02B", "Preventive:  Space Maint", 100),
    ("03", "Restorative", 80),
    ("03A", "Restorative: Crowns", 50),
    ("03B", "Restorative: Build Up", 80),
    ("04", "Endodontics", 80),
    ("04A", "Endodontics: Molar", 80),
    ("05", "Periodontics", 80),
    ("05A", "Periodontics: Osseous Surgery", 80),
    ("05B", "Periodontics: Arestin", 80),
    ("06", "Oral Surgery", 80),
    ("06A", "Oral Surgery: Impactions", 80),
    ("07", "Prosthodontix: (fix/rem), Inlays, Onlays", 50),
    ("08", "Maxillofacial Prosthetics", 50),
    ("09", "Implants", 0),
    ("09A", "Implants: Crowns", 0),
    ("10", "Orthodontics", 50),
    ("11", "Gen Adjunctive", 0),
    ("11A", "Gen Adjunctive: Anesthesia", 0),
    ("11B", "Gen Adjunctive: Biteguard/Nightguard", 0),
    ("12", "Non-covered Services", 0),
)

#: Default frequency ordinal per category — identical on every migrated plan
#: checked; anything not listed is 0 (No Limitation).
DEFAULT_CATEGORY_FREQUENCIES: dict[str, int] = {
    "01": 1, "01A": 6, "01B": 9, "01D": 5, "02": 1, "02A": 12, "03": 6, "03A": 9,
    "03B": 9, "04": 12, "04A": 12, "05": 7, "06": 12, "06A": 12, "09": 12, "09A": 9,
}

#: The INSLIMITATIONS code groups (Tab 4's "Code Group" picker).
CODE_GROUPS: tuple[tuple[str, str], ...] = (
    ("01", "Diagnostic: Periodic Exam (D0120)"),
    ("01A", "Diagnositc: Bitewing X-rays (D0274)"),
    ("01B", "Diagnostic: Full Mouth X-ray (D0210) / PanX (D0330)"),
    ("02", "Preventive: Prophylaxis - Adult (D1110)"),
    ("02A", "Preventive: Prophylaxis - Child (D1120)"),
    ("02B", "Preventive: Fluoride (D1208) / Varnish (D1206)"),
    ("02C", "Preventive: Sealants (D1351)"),
    ("02D", "Preventive: Space Maintainers (D1510-D1525)"),
    ("03", "Restorative: Crowns (D2710-D2794 )"),
    ("03A", "Restorative: Fillings (D2140-D2394)"),
    ("03B", "Restorative: Foil / Inlays / Onlays (D2410-D2664 )"),
    ("05", "Periodontics: SC/RP (D4341-4342)"),
    ("05A", "Periodontics: Full Mouth Debridement (D4355)"),
    ("05B", "Periodontics: Arestin (D4381)"),
    ("05C", "Periodontics: Perio Maintenance (D4910)"),
    ("06", "Oral and Maxillofacial: Occlusal Orthotic Device (D7880)"),
    ("07", "Removable Prosthetics: Dentures/Partials (D5110-D5281)"),
    ("07A", "Fixed Prosthetics: Bridges (D6205-D6252, D6710-D6794)"),
    ("07B", "Fixed Prosthetics: Bridges - Inlays / Onlays (D6545-D6634 )"),
    ("08", "Orthodontics"),
    ("11", "Adjunctive Services: Occlusal Guard (D9940)"),
    ("11A", "Adjunctive Services: Palliative / Emergency Tx (D9110)"),
)

PLAN_TYPES: tuple[str, ...] = (
    "PPO", "HMO", "DISCOUNT", "MEDICAID", "MEDICAL", "UNION", "OUT OF NETWORK",
)
#: ``(plan type, subtype label)`` — PLANSUBTYPE, keyed by the parent plan type.
PLAN_SUBTYPES: tuple[tuple[str, str], ...] = (
    ("PPO", "Aetna"), ("PPO", "Metlife"), ("PPO", "Delta"), ("PPO", "Cigna"),
    ("HMO", "Aetna"), ("HMO", "Metlife"), ("HMO", "Cigna"),
    ("MEDICAID", "Medicaid"), ("DISCOUNT", "Discount"), ("UNION", "Union"),
)

# ── PLAN-DTL-1: the plan-field vocabularies ──────────────────────────────────
#: The codes the wizard writes (``planDetailsModel.ts``). Published, not
#: enforced — an unrecognised value is stored as written (PROV-3 / INS-PT-12).
PLAN_FIELD_OPTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "fees_to_print": (
        ("office_ucr", "Office UCR fees"),
        ("plan_fees", "Plan fees"),
        ("carrier_fees", "Carrier fees"),
    ),
    "claim_option": (
        ("submit", "Submit claims"),
        ("do_not_submit", "Do not submit claims"),
        ("print_only", "Print only"),
    ),
    "form_to_print": (
        ("ADA2024", "ADA 2024"),
        ("ADA2019", "ADA 2019"),
        ("ADA2012", "ADA 2012"),
        ("ADA2006", "ADA 2006"),
        ("CMS1500", "CMS-1500"),
    ),
    "network_type": (
        ("unknown", "Unknown"),
        ("in_network", "In network"),
        ("out_of_network", "Out of network"),
    ),
}

#: Definitions groups the metadata endpoint reads (and the seeder writes).
DEF_GROUP_FREQUENCY = "FREQUENCYLIMITATIONS"
DEF_GROUP_COVERAGE = "DEFCOVERAGE"
DEF_GROUP_CODE_GROUPS = "INSLIMITATIONS"
DEF_GROUP_PLAN_TYPE = "PLANTYPE"
DEF_GROUP_PLAN_SUBTYPE = "PLANSUBTYPE"

# The reserved shape the frontend used for FREQ-tab rows before PLAN-DTL-2.
FREQGRP_CATEGORY = "FREQGRP"
_FREQGRP_CODE = re.compile(r"^FQ", re.IGNORECASE)
_ADA_CODE = re.compile(r"^D\d{4}$", re.IGNORECASE)
_INT = re.compile(r"^\d+$")
_RANGE = re.compile(r"^(\d+)\s*-\s*(\d+)$")


# ── typed-limit helpers (PLAN-DTL-5) ─────────────────────────────────────────
def parse_age_limit(value: str | None) -> tuple[int | None, int | None]:
    """``"5-14"`` → ``(5, 14)``; ``"19"`` → ``(19, None)`` — the wizard's own
    encoding (a lone number is the *minimum*). Migrated rows are handled in
    the migration, where a lone number is the legacy **maximum**; see the
    response doc. Anything else (``"0"``, ``"WM"``, blank) → ``(None, None)``."""
    text = (value or "").strip()
    if not text:
        return None, None
    m = _RANGE.match(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo or None), (hi or None)
    if _INT.match(text):
        n = int(text)
        return (n or None), None
    return None, None


def compose_age_limit(age_min: int | None, age_max: int | None) -> str | None:
    if age_min is None and age_max is None:
        return None
    if age_max is None:
        return str(age_min)
    return f"{age_min or 0}-{age_max}"


def parse_wait_months(value: str | None) -> int | None:
    """``"12"`` → 12. A non-numeric legacy value (one migrated row says
    ``"10 days"``) is *not* guessed at — it stays in the mirror column and the
    typed column is NULL."""
    text = (value or "").strip()
    if _INT.match(text):
        n = int(text)
        return n or None
    return None


def parse_freq_limit(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValidationError("freq_limit must be a whole number", code="invalid_freq_limit")
    try:
        n = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"freq_limit must be a whole number (the frequency ordinal), got {value!r}",
            code="invalid_freq_limit",
        ) from exc
    if n < 0:
        raise ValidationError("freq_limit cannot be negative", code="invalid_freq_limit")
    return n or None


def _non_negative_int(payload: dict, key: str) -> None:
    value = payload.get(key)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            value = int(str(value).strip())
        except ValueError as exc:
            raise ValidationError(
                f"{key} must be a whole number", code=f"invalid_{key}"
            ) from exc
    if value < 0:
        raise ValidationError(f"{key} cannot be negative", code=f"invalid_{key}")
    payload[key] = value or None


def normalise_rule_limits(payload: dict[str, Any], existing: InsuranceCoverageRule | None = None) -> dict[str, Any]:
    """Make the typed columns canonical and the string columns their mirror.

    Typed fields win when both shapes are sent. When only the legacy string is
    sent (an older client) it is parsed into the typed columns. On a PATCH the
    untouched half is read from the stored row so the mirror never goes stale.
    """
    out = dict(payload)
    if "freq_limit" in out:
        out["freq_limit"] = parse_freq_limit(out["freq_limit"])

    typed_age_sent = "age_min" in out or "age_max" in out
    if typed_age_sent:
        _non_negative_int(out, "age_min")
        _non_negative_int(out, "age_max")
        age_min = out.get("age_min", existing.age_min if existing else None)
        age_max = out.get("age_max", existing.age_max if existing else None)
        if age_min is not None and age_max is not None and age_min > age_max:
            raise ValidationError(
                "age_min cannot exceed age_max", code="invalid_age_limit",
                details={"age_min": age_min, "age_max": age_max},
            )
        out["age_limit"] = compose_age_limit(age_min, age_max)
    elif "age_limit" in out:
        out["age_min"], out["age_max"] = parse_age_limit(out["age_limit"])
        # Keep the mirror canonical too ("5 - 14" → "5-14").
        out["age_limit"] = compose_age_limit(out["age_min"], out["age_max"])

    if "wait_months" in out:
        _non_negative_int(out, "wait_months")
        out["wait_period"] = str(out["wait_months"]) if out["wait_months"] is not None else None
    elif "wait_period" in out:
        out["wait_months"] = parse_wait_months(out["wait_period"])
    return out


def is_frequency_group_shape(payload: dict[str, Any]) -> bool:
    category = (payload.get("category") or "").strip().upper()
    start = (payload.get("start_code") or "").strip()
    return category == FREQGRP_CATEGORY or bool(_FREQGRP_CODE.match(start))


# ── tenancy through the plan ─────────────────────────────────────────────────
def get_plan(
    db: Session, plan_id: int, tenant_id: int | None, *, for_update: bool = False,
) -> InsurancePlan:
    stmt = select(InsurancePlan).where(InsurancePlan.id == plan_id)
    if for_update:
        # EDIT-PLAN-1: a versioned write holds the row until commit.
        stmt = stmt.with_for_update()
    plan = db.execute(stmt).scalar_one_or_none()
    if plan is None or (tenant_id is not None and plan.tenant_id != tenant_id):
        raise NotFoundError(f"InsurancePlan '{plan_id}' was not found")
    return plan


# ── EDIT-PLAN-1/5/6: the plan row as the document's version + lock + scope ──
def _actor_id(actor_id: int | None) -> int | None:
    """The acting user: the explicit id when the caller has one, else the
    request context (the generic DELETE route carries no actor)."""
    if actor_id is not None:
        return actor_id
    raw = user_id_ctx.get()
    return int(raw) if raw and raw.isdigit() else None


def touch_plan(plan: InsurancePlan, actor_id: int | None) -> None:
    """Move the plan's version. ``insurance_plans.updated_at`` is the version of
    the **whole** plan document — a coverage-rule or frequency-group write
    changes what the plan pays, so it has to move the value a concurrent
    editor's precondition is judged against, even though the plan's own
    columns did not change (the mixin's ``onupdate`` would not fire)."""
    plan.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    actor = _actor_id(actor_id)
    if actor is not None:
        plan.updated_by = actor


def assert_plan_editable(db: Session, plan: InsurancePlan, actor_id: int | None) -> None:
    """EDIT-PLAN-5: a locked plan is 423 ``plan_locked`` unless the actor holds
    ``setup_insurance_plans_screen_edit_locked_plan`` (or a full-access role).
    An unresolvable actor never unlocks anything."""
    if not plan.is_locked:
        return
    perms = permission_service.permissions_for_user_id(db, _actor_id(actor_id))
    if perms is None:
        raise LockedError(
            "This insurance plan is locked", code="plan_locked",
            details={"plan_id": plan.id,
                     "required_any_of": [permission_service.INSURANCE_PLAN_EDIT_LOCKED]},
        )
    permission_service.assert_can_edit_locked(perms, plan_id=plan.id)


def record_plan_scope(plan_id: int, label: str | None = None) -> None:
    """EDIT-PLAN-6: tag the request's audit row with the plan a child-row write
    belongs to, so ``GET /insurance-plans/{id}/history`` can find it without a
    lookup per rule id. ``label`` names the row (``03A``, code group ``01``) —
    a PATCH diff carries only the changed fields, so the history summary
    would otherwise have nothing but the row id to show."""
    scope: dict[str, Any] = {"ins_plan_id": plan_id}
    if label:
        scope["label"] = label
    audit_context.record(scope=scope)


def _plan_for_write(
    db: Session, plan_id: int, tenant_id: int | None, actor_id: int | None,
    label: str | None = None,
) -> InsurancePlan:
    """The owning plan, checked for the lock, tagged for audit and version-bumped
    — the three things every child-row write has to do."""
    plan = get_plan(db, plan_id, tenant_id)
    assert_plan_editable(db, plan, actor_id)
    record_plan_scope(plan.id, label)
    touch_plan(plan, actor_id)
    return plan


def _tenant_plan_ids(tenant_id: int):
    return select(InsurancePlan.id).where(InsurancePlan.tenant_id == tenant_id)


class InsuranceCoverageRuleCRUD(CRUDBase[InsuranceCoverageRule]):
    """Tenant scoping via the owning plan, typed-limit normalisation, and the
    FREQGRP refusal (PLAN-DTL-2/5, and the tenancy hole described above)."""

    def _scope_tenant(self, stmt, tenant_id: int | None):  # noqa: ANN001
        if tenant_id is None:
            return stmt
        return stmt.where(InsuranceCoverageRule.ins_plan_id.in_(_tenant_plan_ids(tenant_id)))

    @staticmethod
    def _refuse_frequency_group(payload: dict[str, Any]) -> None:
        if is_frequency_group_shape(payload):
            raise ValidationError(
                "Frequency-limitation code groups are not coverage rules — use "
                "/insurance-plan-frequency-groups (or PUT /insurance-plans/{id}/coverage-rules)",
                code="frequency_group_row_not_coverage",
                details={"resource": "/insurance-plan-frequency-groups"},
            )

    def create(
        self, db: Session, data: dict[str, Any], *,
        tenant_id: int | None = None, created_by: int | None = None,
    ) -> InsuranceCoverageRule:
        payload = normalise_rule_limits(data)
        self._refuse_frequency_group(payload)
        if payload.get("ins_plan_id") is not None:
            _plan_for_write(db, payload["ins_plan_id"], tenant_id, created_by,
                            label=payload.get("start_code"))
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(
        self, db: Session, obj_id: Any, data: dict[str, Any], *,
        tenant_id: int | None = None, updated_by: int | None = None,
    ) -> InsuranceCoverageRule:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        payload = normalise_rule_limits(data, existing)
        merged = {
            "category": payload.get("category", existing.category),
            "start_code": payload.get("start_code", existing.start_code),
        }
        self._refuse_frequency_group(merged)
        _plan_for_write(db, existing.ins_plan_id, tenant_id, updated_by, label=existing.start_code)
        if "ins_plan_id" in payload and payload["ins_plan_id"] != existing.ins_plan_id:
            _plan_for_write(db, payload["ins_plan_id"], tenant_id, updated_by, label=existing.start_code)
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)

    def delete(self, db: Session, obj_id: Any, *, tenant_id: int | None = None) -> None:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        _plan_for_write(db, existing.ins_plan_id, tenant_id, None, label=existing.start_code)
        super().delete(db, obj_id, tenant_id=tenant_id)


class InsurancePlanFrequencyGroupCRUD(CRUDBase[InsurancePlanFrequencyGroup]):
    """PLAN-DTL-2: the plan must belong to the tenant; numbers are whole and
    non-negative; a blank description is filled from the code-group catalogue."""

    def _prepare(
        self, db: Session, payload: dict[str, Any], tenant_id: int | None,
        actor_id: int | None = None,
    ) -> dict[str, Any]:
        out = dict(payload)
        if "freq_limit" in out:
            out["freq_limit"] = parse_freq_limit(out["freq_limit"])
        if "per_day_quantity" in out:
            _non_negative_int(out, "per_day_quantity")
        if "code_group" in out:
            code = (out.get("code_group") or "").strip()
            if not code:
                raise ValidationError("code_group is required", code="missing_code_group")
            out["code_group"] = code
            if not out.get("description"):
                out["description"] = dict(CODE_GROUPS).get(code)
        if out.get("ins_plan_id") is not None:
            _plan_for_write(db, out["ins_plan_id"], tenant_id, actor_id, label=out.get("code_group"))
        return out

    def create(
        self, db: Session, data: dict[str, Any], *,
        tenant_id: int | None = None, created_by: int | None = None,
    ) -> InsurancePlanFrequencyGroup:
        payload = self._prepare(db, data, tenant_id, created_by)
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(
        self, db: Session, obj_id: Any, data: dict[str, Any], *,
        tenant_id: int | None = None, updated_by: int | None = None,
    ) -> InsurancePlanFrequencyGroup:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        _plan_for_write(db, existing.ins_plan_id, tenant_id, updated_by, label=existing.code_group)
        payload = self._prepare(db, data, tenant_id, updated_by)
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)

    def delete(self, db: Session, obj_id: Any, *, tenant_id: int | None = None) -> None:
        existing = self.get(db, obj_id, tenant_id=tenant_id)
        _plan_for_write(db, existing.ins_plan_id, tenant_id, None, label=existing.code_group)
        super().delete(db, obj_id, tenant_id=tenant_id)


# ── PLAN-DTL-3: anniversary Month/Day ↔ full date ────────────────────────────
def fold_anniversary(payload: dict[str, Any], existing: InsurancePlan | None = None) -> dict[str, Any]:
    """Keep ``anniversary_month``/``anniversary_day`` and ``anniversary_date``
    consistent whichever the client writes.

    Month/day win when both are sent (they are the typed shape). A month/day
    write keeps the stored year — or the current one on first save — so the
    full-date column, which the migrated benefit-year data already uses, is
    never left contradicting the typed pair.
    """
    out = dict(payload)
    month = out.get("anniversary_month")
    day = out.get("anniversary_day")
    md_sent = "anniversary_month" in out or "anniversary_day" in out

    if md_sent:
        month = month if "anniversary_month" in out else (existing.anniversary_month if existing else None)
        day = day if "anniversary_day" in out else (existing.anniversary_day if existing else None)
        if month is None and day is None:
            out["anniversary_month"] = out["anniversary_day"] = None
            out["anniversary_date"] = None
            return out
        if month is None or day is None:
            raise ValidationError(
                "anniversary_month and anniversary_day must be set together",
                code="invalid_anniversary",
            )
        if not 1 <= int(month) <= 12:
            raise ValidationError("anniversary_month must be 1-12", code="invalid_anniversary")
        stored = existing.anniversary_date if existing else None
        year = stored.year if stored else date.today().year
        try:
            out["anniversary_date"] = date(year, int(month), int(day))
        except ValueError as exc:
            raise ValidationError(
                f"anniversary_day {day} is not valid for month {month}",
                code="invalid_anniversary",
            ) from exc
        out["anniversary_month"], out["anniversary_day"] = int(month), int(day)
        return out

    if "anniversary_date" in out:
        d = out["anniversary_date"]
        if isinstance(d, str):
            d = date.fromisoformat(d)
            out["anniversary_date"] = d
        out["anniversary_month"] = d.month if d else None
        out["anniversary_day"] = d.day if d else None
    return out


# ── the metadata payload (PLAN-DTL-1/4 + the default table) ──────────────────
def _tenant_definitions(db: Session, tenant_id: int | None, group_code: str) -> list[Definition]:
    if tenant_id is None:
        return []
    return list(db.execute(
        select(Definition)
        .where(Definition.tenant_id == tenant_id, Definition.group_code == group_code,
               Definition.is_active.is_(True))
        .order_by(Definition.sort_order.nulls_last(), Definition.id)
    ).scalars())


def frequency_catalogue(db: Session, tenant_id: int | None) -> list[dict]:
    """The 13 ordinals + "No Limitation", each carrying the tenant's own
    ``definitions`` row id where one exists (matched on label)."""
    by_label = {d.description.strip().lower(): d for d in _tenant_definitions(db, tenant_id, DEF_GROUP_FREQUENCY)}
    out = [{"code": 0, "label": NO_LIMITATION_LABEL, "key1": None, "key2": None,
            "definition_id": None, "legacy_id": None}]
    for ordinal, label, key1, key2 in FREQUENCY_LIMITATIONS:
        row = by_label.get(label.strip().lower())
        out.append({
            "code": ordinal, "label": label, "key1": key1, "key2": key2,
            "definition_id": row.id if row else None,
            "legacy_id": row.legacy_id if row else None,
        })
    return out


def default_coverage_rules(db: Session, tenant_id: int | None) -> list[dict]:
    """The 28 category rows a new plan starts with: the tenant's DEFCOVERAGE
    percentages when it has them (a practice may have edited its defaults),
    else the built-in table; frequencies from the migrated default."""
    rows = _tenant_definitions(db, tenant_id, DEF_GROUP_COVERAGE)
    source = "builtin"
    table: list[tuple[str, str, int]] = list(DEFAULT_COVERAGE_TABLE)
    if rows:
        seen: dict[str, tuple[str, str, int]] = {}
        for d in rows:
            code = (d.key1 or "").strip()
            if not code or code in seen:
                continue
            pct = int(d.key2) if d.key2 and _INT.match(d.key2.strip()) else 0
            seen[code] = (code, d.description, pct)
        if seen:
            table = list(seen.values())
            source = "tenant"
    return [
        {
            "start_code": code, "end_code": code, "category": "0",
            "description": label, "coverage_pct": pct, "ded_waived": False,
            "freq_limit": DEFAULT_CATEGORY_FREQUENCIES.get(code, 0),
            "age_min": None, "age_max": None, "wait_months": None,
            "source": source,
        }
        for code, label, pct in sorted(table, key=lambda t: t[0])
    ]


def code_group_catalogue(db: Session, tenant_id: int | None) -> list[dict]:
    rows = _tenant_definitions(db, tenant_id, DEF_GROUP_CODE_GROUPS)
    if rows:
        seen: dict[str, dict] = {}
        for d in rows:
            code = (d.key1 or "").strip()
            if code and code not in seen:
                seen[code] = {"code": code, "label": d.description, "definition_id": d.id}
        if seen:
            return sorted(seen.values(), key=lambda r: r["code"])
    return [{"code": c, "label": l, "definition_id": None} for c, l in CODE_GROUPS]


def plan_metadata(db: Session, tenant_id: int | None) -> dict:
    freq = frequency_catalogue(db, tenant_id)
    defaults = default_coverage_rules(db, tenant_id)
    groups = code_group_catalogue(db, tenant_id)
    return {
        "frequency_limitations": freq,
        "default_coverage_rules": defaults,
        "code_groups": groups,
        "plan_field_options": {
            field: [{"code": code, "label": label} for code, label in options]
            for field, options in PLAN_FIELD_OPTIONS.items()
        },
        # EDIT-PLAN-9: what a blank / omitted field means (and now stores).
        "plan_field_defaults": dict(PLAN_FIELD_DEFAULTS),
        # EDIT-PLAN-5: the rights the write paths enforce, so the UI gates
        # Edit Plan on the same codes the server does.
        "permissions": {
            "write_any_of": list(permission_service.INSURANCE_PLAN_WRITE),
            "edit_locked": permission_service.INSURANCE_PLAN_EDIT_LOCKED,
            "locked_error_code": "plan_locked",
            "denied_error_code": "permission_denied",
        },
        # EDIT-PLAN-1: how a client asserts "unchanged since I read it".
        "concurrency": {
            "version_field": "updated_at",
            "headers": ["If-Match", "If-Unmodified-Since"],
            "body_field": "expected_updated_at",
            "error_code": "precondition_failed",
            "status_code": 412,
        },
        "catalog_sources": {
            "frequency_limitations": "tenant" if any(f["definition_id"] for f in freq) else "builtin",
            "default_coverage_rules": defaults[0]["source"] if defaults else "builtin",
            "code_groups": "tenant" if any(g["definition_id"] for g in groups) else "builtin",
        },
        "conventions": {
            "category_row": "start_code = end_code = <category code>, category = '0'",
            "exception_row": "start_code = end_code = <ADA code>, category = <parent category code>",
            "freq_limit": "1-based ordinal into frequency_limitations; 0 or null = No Limitation",
            "age_limit": "derived mirror of age_min/age_max ('min' or 'min-max'); typed fields win",
            "wait_period": "derived mirror of wait_months",
            "frequency_groups": "insurance_plan_frequency_groups — never a coverage rule",
        },
    }


# ── plan details: read / bulk replace / copy (PLAN-DTL-8) ────────────────────
_RULE_FIELDS = (
    "start_code", "end_code", "category", "description", "coverage_pct", "ded_waived",
    "freq_limit", "age_min", "age_max", "wait_months", "age_limit", "wait_period",
)
_GROUP_FIELDS = ("code_group", "description", "freq_limit", "whole_mouth", "per_day_quantity")
#: Plan-level fields "COPY FROM EXISTING" carries across (BENEFITS + PLAN extras).
COPYABLE_PLAN_FIELDS = (
    "plan_type", "coverage_type", "is_prepaid",
    "individual_deductible", "family_deductible", "individual_max", "family_max", "ortho_max",
    "fees_to_print", "claim_option", "form_to_print", "reporting_subtype", "network_type",
    "noa_only", "per_visit_copay", "lifetime_ortho_benefits", "plan_notes",
    "anniversary_month", "anniversary_day", "anniversary_date",
)


def _rules_for(db: Session, plan_id: int) -> list[InsuranceCoverageRule]:
    return list(db.execute(
        select(InsuranceCoverageRule)
        .where(InsuranceCoverageRule.ins_plan_id == plan_id)
        .order_by(InsuranceCoverageRule.id)
    ).scalars())


def _groups_for(db: Session, plan_id: int) -> list[InsurancePlanFrequencyGroup]:
    return list(db.execute(
        select(InsurancePlanFrequencyGroup)
        .where(InsurancePlanFrequencyGroup.ins_plan_id == plan_id)
        .order_by(InsurancePlanFrequencyGroup.code_group, InsurancePlanFrequencyGroup.id)
    ).scalars())


def plan_coverage(db: Session, plan_id: int, tenant_id: int | None) -> dict:
    plan = get_plan(db, plan_id, tenant_id)
    return {
        "plan_id": plan.id,
        "rules": _rules_for(db, plan.id),
        "frequency_groups": _groups_for(db, plan.id),
    }


def _apply_fields(obj, data: dict[str, Any], fields: Iterable[str]) -> None:  # noqa: ANN001
    for f in fields:
        if f in data:
            setattr(obj, f, data[f])


def replace_plan_coverage(
    db: Session,
    plan_id: int,
    tenant_id: int | None,
    *,
    rules: list[dict[str, Any]] | None,
    frequency_groups: list[dict[str, Any]] | None,
    actor_id: int | None,
    expected_updated_at: Any = concurrency._SENTINEL,
) -> dict:
    """Reconcile a plan's whole coverage table in one transaction.

    A section that is ``None`` is left untouched. For a section that is sent,
    an item carrying the ``id`` of a row on this plan is **updated in place**
    (its id and ``legacy_id`` survive), an item without one is inserted, and
    any existing row not mentioned is deleted — replace semantics that keep
    identity for the rows the caller kept. An ``id`` that is not on this plan
    is a 422, never a cross-plan move.

    EDIT-PLAN-1: ``expected_updated_at`` (or the request's ``If-Match`` /
    ``If-Unmodified-Since``) is judged against the **plan** row, which is
    locked for the transaction; the plan's version moves on success.
    EDIT-PLAN-5: a locked plan is refused. EDIT-PLAN-6: every row-level
    change lands in the request's audit row as ``changes[]``.
    """
    precondition = dict(concurrency.snapshot() or {})
    if expected_updated_at is not concurrency._SENTINEL:
        precondition["expected_updated_at"] = expected_updated_at
    plan = get_plan(db, plan_id, tenant_id, for_update=bool(precondition))
    concurrency.check(plan, precondition or None, db=db, resource="InsurancePlan")
    assert_plan_editable(db, plan, actor_id)
    summary = {"rules": None, "frequency_groups": None}
    changes: list[dict[str, Any]] = []

    def _change(resource_type: str, row_id: Any, action: str, before: dict | None,
                after: dict | None, label: str | None) -> None:
        changes.append({
            "resource_type": resource_type, "row_id": row_id, "action": action,
            "label": label,
            "before": {k: audit_context.json_safe(v) for k, v in before.items()} if before else None,
            "after": {k: audit_context.json_safe(v) for k, v in after.items()} if after else None,
        })

    try:
        if rules is not None:
            existing = {r.id: r for r in _rules_for(db, plan.id)}
            kept: set[int] = set()
            created = updated = 0
            for idx, item in enumerate(rules):
                payload = normalise_rule_limits({k: v for k, v in item.items() if k in _RULE_FIELDS or k == "id"})
                if is_frequency_group_shape(payload):
                    raise ValidationError(
                        f"rules[{idx}] is a frequency-group row; send it in frequency_groups",
                        code="frequency_group_row_not_coverage", details={"index": idx},
                    )
                if not (payload.get("start_code") or "").strip():
                    raise ValidationError(
                        f"rules[{idx}].start_code is required", code="missing_start_code",
                        details={"index": idx},
                    )
                payload.setdefault("end_code", payload["start_code"])
                rid = payload.pop("id", None)
                if rid is not None:
                    row = existing.get(rid)
                    if row is None:
                        raise ValidationError(
                            f"rules[{idx}].id {rid} is not a rule on plan {plan.id}",
                            code="rule_not_on_plan", details={"index": idx, "id": rid},
                        )
                    before, after = audit_context.diff_fields(row, {k: v for k, v in payload.items() if k in _RULE_FIELDS})
                    _apply_fields(row, payload, _RULE_FIELDS)
                    if before:
                        row.updated_by = actor_id
                        _change("insurance-coverage-rules", rid, "update", before, after,
                                f"{row.start_code} {row.description or ''}".strip())
                    kept.add(rid)
                    updated += 1
                else:
                    fields = {k: v for k, v in payload.items() if k in _RULE_FIELDS}
                    new_row = InsuranceCoverageRule(ins_plan_id=plan.id, created_by=actor_id, **fields)
                    db.add(new_row)
                    _change("insurance-coverage-rules", None, "create", None, fields,
                            f"{fields.get('start_code')} {fields.get('description') or ''}".strip())
                    created += 1
            deleted = 0
            for rid, row in existing.items():
                if rid not in kept:
                    _change("insurance-coverage-rules", rid, "delete",
                            {f: getattr(row, f) for f in _RULE_FIELDS}, None,
                            f"{row.start_code} {row.description or ''}".strip())
                    db.delete(row)
                    deleted += 1
            summary["rules"] = {"created": created, "updated": updated, "deleted": deleted}

        if frequency_groups is not None:
            existing_g = {g.id: g for g in _groups_for(db, plan.id)}
            kept_g: set[int] = set()
            created = updated = 0
            seen_codes: set[str] = set()
            for idx, item in enumerate(frequency_groups):
                payload = dict(item)
                gid = payload.pop("id", None)
                payload = {k: v for k, v in payload.items() if k in _GROUP_FIELDS}
                code = (payload.get("code_group") or "").strip()
                if not code:
                    raise ValidationError(
                        f"frequency_groups[{idx}].code_group is required",
                        code="missing_code_group", details={"index": idx},
                    )
                if code in seen_codes:
                    raise ValidationError(
                        f"frequency_groups[{idx}] repeats code group {code}",
                        code="duplicate_code_group", details={"index": idx, "code_group": code},
                    )
                seen_codes.add(code)
                payload["code_group"] = code
                if "freq_limit" in payload:
                    payload["freq_limit"] = parse_freq_limit(payload["freq_limit"])
                if "per_day_quantity" in payload:
                    _non_negative_int(payload, "per_day_quantity")
                if not payload.get("description"):
                    payload["description"] = dict(CODE_GROUPS).get(code)
                if gid is not None:
                    row = existing_g.get(gid)
                    if row is None:
                        raise ValidationError(
                            f"frequency_groups[{idx}].id {gid} is not on plan {plan.id}",
                            code="frequency_group_not_on_plan", details={"index": idx, "id": gid},
                        )
                    before, after = audit_context.diff_fields(row, payload)
                    _apply_fields(row, payload, _GROUP_FIELDS)
                    if before:
                        row.updated_by = actor_id
                        _change("insurance-plan-frequency-groups", gid, "update", before, after, code)
                    kept_g.add(gid)
                    updated += 1
                else:
                    # Same code group re-sent without its id: adopt the row so the
                    # unique constraint does not turn a re-PUT into a 409.
                    match = next((g for g in existing_g.values() if g.code_group == code and g.id not in kept_g), None)
                    if match is not None:
                        before, after = audit_context.diff_fields(match, payload)
                        _apply_fields(match, payload, _GROUP_FIELDS)
                        if before:
                            match.updated_by = actor_id
                            _change("insurance-plan-frequency-groups", match.id, "update", before, after, code)
                        kept_g.add(match.id)
                        updated += 1
                    else:
                        db.add(InsurancePlanFrequencyGroup(
                            tenant_id=plan.tenant_id, ins_plan_id=plan.id,
                            created_by=actor_id, **payload,
                        ))
                        _change("insurance-plan-frequency-groups", None, "create", None, payload, code)
                        created += 1
            deleted = 0
            for gid, row in existing_g.items():
                if gid not in kept_g:
                    _change("insurance-plan-frequency-groups", gid, "delete",
                            {f: getattr(row, f) for f in _GROUP_FIELDS}, None, row.code_group)
                    db.delete(row)
                    deleted += 1
            summary["frequency_groups"] = {"created": created, "updated": updated, "deleted": deleted}

        # EDIT-PLAN-1: the plan row is the document's version — it moves on
        # every coverage write so a concurrent editor's precondition fails.
        touch_plan(plan, actor_id)
        db.commit()
    except Exception:
        db.rollback()
        raise

    # EDIT-PLAN-6: one audit row for the request, carrying every row-level change.
    audit_context.record(
        resource_id=str(plan.id), row_id=plan.id,
        scope={"ins_plan_id": plan.id}, changes=changes or None,
    )
    out = plan_coverage(db, plan.id, tenant_id)
    out["summary"] = summary
    out["plan_updated_at"] = plan.updated_at
    out["version"] = concurrency.version_token(concurrency.version_of(plan))
    return out


def copy_plan_coverage(
    db: Session,
    target_id: int,
    source_id: int,
    tenant_id: int | None,
    *,
    include_rules: bool = True,
    include_frequency_groups: bool = True,
    include_plan_fields: bool = False,
    actor_id: int | None,
) -> dict:
    """COPY FROM EXISTING, server-side: the source plan's coverage table (and,
    on request, its BENEFITS/PLAN-tab fields — never its identity: carrier,
    employer, group number and audit columns stay the target's own)."""
    if target_id == source_id:
        raise ValidationError("A plan cannot be copied onto itself", code="copy_onto_self")
    target = get_plan(db, target_id, tenant_id)
    source = get_plan(db, source_id, tenant_id)

    rules = None
    if include_rules:
        rules = [
            {f: getattr(r, f) for f in _RULE_FIELDS}
            for r in _rules_for(db, source.id)
        ]
    groups = None
    if include_frequency_groups:
        groups = [
            {f: getattr(g, f) for f in _GROUP_FIELDS}
            for g in _groups_for(db, source.id)
        ]
    if include_plan_fields:
        for f in COPYABLE_PLAN_FIELDS:
            setattr(target, f, getattr(source, f))
    out = replace_plan_coverage(
        db, target.id, tenant_id, rules=rules, frequency_groups=groups, actor_id=actor_id,
    )
    out["copied_from_plan_id"] = source.id
    out["copied_plan_fields"] = list(COPYABLE_PLAN_FIELDS) if include_plan_fields else []
    return out


__all__ = [
    "CODE_GROUPS",
    "COPYABLE_PLAN_FIELDS",
    "DEFAULT_CATEGORY_FREQUENCIES",
    "DEFAULT_COVERAGE_TABLE",
    "FREQUENCY_LIMITATIONS",
    "InsuranceCoverageRuleCRUD",
    "InsurancePlanFrequencyGroupCRUD",
    "PLAN_FIELD_DEFAULTS",
    "PLAN_FIELD_OPTIONS",
    "PLAN_SUBTYPES",
    "PLAN_TYPES",
    "assert_plan_editable",
    "compose_age_limit",
    "copy_plan_coverage",
    "fold_anniversary",
    "get_plan",
    "normalise_rule_limits",
    "parse_age_limit",
    "parse_wait_months",
    "plan_coverage",
    "plan_metadata",
    "record_plan_scope",
    "replace_plan_coverage",
    "touch_plan",
]
