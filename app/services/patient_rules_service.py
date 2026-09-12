"""Add / Edit Patient checkbox integrity rules.

The Add-Patient and Edit-Patient forms render three checkbox panels — **Patient
Status**, **Coverage Type** and **Patient Type** — and every box in them was
independently selectable. Nothing stopped a user from saving a patient who is
simultaneously a *Child* and a *Senior Citizen*, or one flagged **No
Correspondence** while automated e-mail and SMS stayed switched on. The API
accepted all of it, so the contradiction was persisted and every downstream
consumer (recall sweeps, batch letters, the SMS reminder job) inherited it.

The rules live here, once, and are enforced on **every** write path — generic
``PATCH /patients/{id}``, the atomic ``POST /patients/register``, and the
``/patient-insurance`` slot resource — so a client cannot route around them.
They are also published verbatim by ``GET /metadata/patient-flag-rules`` so the
form can drive its own checkbox behaviour from this same table instead of
keeping a second copy that drifts.

Two different kinds of rule, deliberately handled differently:

* **Implications** (``A ⇒ B``) are *auto-applied*. The combination is not
  ambiguous — "No Correspondence" plainly contains "no automated e-mail" — so
  the server sets the implied flag and returns the corrected record. The client
  sees the corrected value come back in the response.
* **Exclusions** (``A ⊕ B``) are *rejected* with 422. When a patient is marked
  both Child and Senior there is no way to know which the user meant, and
  silently dropping one would discard real intent. The error names the pair.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError

# ── Patient Type (patients.patient_types, the CH/CP/EF/OR/SN/SR/SS/UP tags) ───
# Only genuinely contradictory pairs belong here. The rest of the catalog is
# orthogonal and legitimately multi-select: a patient really can be an Ortho
# Patient who is also Spanish Speaking, a Collection Problem and flagged for
# Short Notice all at once.
PATIENT_TYPE_EXCLUSIONS: tuple[tuple[str, str, str], ...] = (
    ("CH", "SR", "a patient cannot be both a Child and a Senior Citizen"),
)

# ── Patient Status (boolean columns on patients) ──────────────────────────────
# (when_field, when_value, {forced_field: forced_value}, why)
STATUS_IMPLICATIONS: tuple[tuple[str, bool, dict[str, bool], str], ...] = (
    (
        "no_correspondence", True,
        {"no_auto_email": True, "no_auto_sms": True},
        "No Correspondence is the umbrella opt-out; leaving automated e-mail or "
        "SMS switched on would keep messaging a patient who asked not to be contacted",
    ),
    (
        "is_active", False,
        {"add_to_quickfill": False},
        "the Quick-Fill list is the short-notice call list used to fill "
        "cancellations — an inactive patient must not be offered a slot from it",
    ),
)

# ── Coverage Type (patient_insurance slots) ───────────────────────────────────
# "No Coverage" is not a column: it is the derived state of having no active
# slot at all, so the No-Coverage-vs-the-rest exclusion can only be enforced in
# the form. What *is* enforceable here is ordinal integrity — a secondary payer
# with no primary is not a real coverage arrangement, it is a data-entry slip.
INSURANCE_RANKS: tuple[str, ...] = ("primary", "secondary", "tertiary", "quaternary")

_PLAN_TYPE_LABELS = {"D": "Dental", "M": "Medical"}

# ── Responsible-party relationship (patients.responsible_party_relationship) ──
# GAP-AP-25: the ``resp_party_rel`` definitions group was seeded twice — a
# lowercase key set (``self/spouse/…``) and the legacy single-letter codes
# (``S/SP/P/G/C/D/O``) — so the dropdown listed every option twice and the
# column held three spellings of the same fact (``spouse`` / ``SP`` / ``Spouse``).
# The **code** is canonical: it is the legacy vocabulary, it is what
# ``patient_insurance.relationship`` already holds, and it is the only set with
# *Dependent*. Every write path folds a key or a label to the code; a value that
# is none of the three is stored as written (the PROV-3 call — a 422 on save is a
# worse failure than an unfamiliar string, and a migrated value may be one).
RESP_PARTY_RELATIONSHIPS: tuple[tuple[str, str], ...] = (
    ("S", "Self"), ("SP", "Spouse"), ("P", "Parent"), ("G", "Guardian"),
    ("C", "Child"), ("D", "Dependent"), ("O", "Other"),
)
_REL_ALIASES: dict[str, str] = {}
for _code, _label in RESP_PARTY_RELATIONSHIPS:
    _REL_ALIASES[_code.lower()] = _code
    _REL_ALIASES[_label.lower()] = _code
RESP_PARTY_REL_SELF = "S"


def normalize_resp_party_relationship(value: Any) -> Any:
    """Fold a ``resp_party_rel`` key, code or label to the canonical code."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _REL_ALIASES.get(text.lower(), text)


# ── Middle name / initial (GAP-AP-19) ────────────────────────────────────────
def fold_middle_name(payload: dict[str, Any], *, existing: Any = None) -> None:
    """Keep ``middle_initial`` in step with ``middle_name`` in place.

    Legacy screens, letters (``#PAT_MID_INITIAL#``) and the migrated data all
    read the initial, so it must not go blank the moment a practice starts
    entering full names: a write that carries ``middle_name`` and no explicit
    ``middle_initial`` derives the initial from it. An explicit initial always
    wins — it may legitimately differ (``"Jr."`` conventions, two middle names).
    Clearing the name clears a derived initial only when the stored initial
    was the name's own first letter, so a hand-typed initial survives.
    """
    if "middle_name" not in payload or "middle_initial" in payload:
        return
    name = payload.get("middle_name")
    name = str(name).strip() if name is not None else ""
    if name:
        payload["middle_initial"] = name[0].upper()
        return
    stored_name = str(getattr(existing, "middle_name", None) or "").strip()
    stored_initial = str(getattr(existing, "middle_initial", None) or "").strip()
    if stored_name and stored_initial and stored_initial.upper() == stored_name[0].upper():
        payload["middle_initial"] = None


def _label(code: str) -> str:
    """Human label for a patient-type code, for error messages."""
    return {
        "CH": "Child", "CP": "Collection Problem", "EF": "Employee & Family",
        "OR": "Ortho Patient", "SN": "Short Notice Appointment", "SR": "Senior Citizen",
        "SS": "Spanish Speaking", "UP": "Update Information",
    }.get(code, code)


# ── patient_types ────────────────────────────────────────────────────────────
def normalize_patient_types(value: Any) -> list[str] | None:
    """Upper-case, trim, drop blanks and de-duplicate, preserving order.

    The multi-select could post the same code twice (and did, once the form let
    every box be ticked); a JSON column has no unique constraint to catch it.
    """
    if value is None:
        return None
    if not isinstance(value, (list, tuple, set)):
        raise ValidationError(
            "patient_types must be a list of patient-type codes",
            details={"received": str(type(value).__name__)},
        )
    seen: list[str] = []
    for raw in value:
        code = str(raw).strip().upper()
        if code and code not in seen:
            seen.append(code)
    return seen


def validate_patient_types(codes: list[str] | None) -> None:
    """Reject mutually exclusive patient-type tags (422)."""
    if not codes:
        return
    present = set(codes)
    for first, second, why in PATIENT_TYPE_EXCLUSIONS:
        if first in present and second in present:
            raise ValidationError(
                f"Patient Type '{first} – {_label(first)}' and "
                f"'{second} – {_label(second)}' cannot both be selected: {why}.",
                code="conflicting_patient_types",
                details={"field": "patient_types", "conflict": [first, second]},
            )


# ── patient status flags ─────────────────────────────────────────────────────
def _effective(field: str, payload: dict[str, Any], existing: Any) -> Any:
    """The value ``field`` will hold once ``payload`` is applied.

    A PATCH sends only the boxes the user touched, so an implication has to be
    evaluated against the merge of the incoming payload and the stored row —
    otherwise ticking No Correspondence on its own would not reach the e-mail
    and SMS flags already sitting true in the database.
    """
    if field in payload:
        return payload[field]
    if existing is not None:
        return getattr(existing, field, None)
    return None


def apply_status_implications(
    payload: dict[str, Any], *, existing: Any = None
) -> list[dict[str, Any]]:
    """Force the implied status flags into ``payload`` in place.

    Returns the rules that fired, as ``{rule, forced}`` dicts — used by the tests
    and worth logging; the caller does not need to act on it, because the
    corrected values are already in ``payload`` and come back in the response.
    """
    applied: list[dict[str, Any]] = []
    for when_field, when_value, forced, why in STATUS_IMPLICATIONS:
        if _effective(when_field, payload, existing) != when_value:
            continue
        changed: dict[str, bool] = {}
        for field, value in forced.items():
            if _effective(field, payload, existing) != value:
                payload[field] = value
                changed[field] = value
        if changed:
            applied.append({
                "rule": f"{when_field}={when_value}",
                "forced": changed,
                "why": why,
            })
    return applied


def normalize_patient_payload(
    payload: dict[str, Any], *, existing: Any = None
) -> dict[str, Any]:
    """The single entry point for every patient write path.

    Normalizes + validates ``patient_types`` and applies the status
    implications. Returns the corrected payload (a copy — the caller's dict is
    left alone). Raises ``ValidationError`` on a contradiction that cannot be
    resolved automatically.
    """
    out = dict(payload)
    # Only what is actually being written is validated. A migrated row already
    # holding both tags keeps them until someone edits *that* field — rejecting
    # an unrelated edit (a phone-number correction) with a patient-type error the
    # user cannot act on from that screen would be worse than the stale data.
    if "patient_types" in out:
        out["patient_types"] = normalize_patient_types(out["patient_types"])
        validate_patient_types(out["patient_types"])
    if "responsible_party_relationship" in out:
        out["responsible_party_relationship"] = normalize_resp_party_relationship(
            out["responsible_party_relationship"]
        )
    fold_middle_name(out, existing=existing)
    apply_status_implications(out, existing=existing)
    return out


# ── coverage slots ───────────────────────────────────────────────────────────
def validate_coverage_slot(
    db: Session,
    *,
    patient_id: int | None,
    legacy_plan_type: str | None,
    insurance_type: str | None,
    is_active: bool,
    exclude_id: int | None = None,
) -> None:
    """Reject an active coverage slot whose lower-ranked slot does not exist.

    Secondary Dental with no Primary Dental (and the medical equivalent) is the
    Coverage Type panel's version of the same defect: the boxes were
    independent, so a coverage arrangement that cannot exist could be saved.

    Only *active* slots are checked — an archived secondary left behind by a
    plan change is history, not a contradiction. An ``insurance_type`` outside
    the known rank ladder is left alone rather than guessed at.
    """
    from app.db.models import PatientInsurance

    if not is_active or patient_id is None or not insurance_type:
        return
    rank = str(insurance_type).strip().lower()
    if rank not in INSURANCE_RANKS:
        return
    index = INSURANCE_RANKS.index(rank)
    if index == 0:  # primary needs nothing beneath it
        return
    required = INSURANCE_RANKS[index - 1]

    stmt = select(PatientInsurance.id).where(
        PatientInsurance.patient_id == patient_id,
        PatientInsurance.insurance_type == required,
        PatientInsurance.is_active.is_(True),
    )
    # The slot key is (plan_type × ordinal): dental secondary needs a dental
    # primary, not just any primary.
    if legacy_plan_type is None:
        stmt = stmt.where(PatientInsurance.legacy_plan_type.is_(None))
    else:
        stmt = stmt.where(PatientInsurance.legacy_plan_type == legacy_plan_type)
    if exclude_id is not None:
        stmt = stmt.where(PatientInsurance.id != exclude_id)

    if db.execute(stmt).scalar_one_or_none() is not None:
        return

    kind = _PLAN_TYPE_LABELS.get(legacy_plan_type or "", legacy_plan_type or "").strip()
    prefix = f"{kind} " if kind else ""
    raise ValidationError(
        f"Cannot add {prefix}{rank} coverage: this patient has no active "
        f"{prefix}{required} coverage. Add the {required} plan first.",
        code="missing_primary_coverage",
        details={
            "field": "insurance_type",
            "requires": required,
            "legacy_plan_type": legacy_plan_type,
        },
    )


# ── published rule set (drives the form) ─────────────────────────────────────
def published_rules() -> dict[str, Any]:
    """The rule table as data, for ``GET /metadata/patient-flag-rules``.

    The form needs the same logic to tick and untick boxes as the user clicks.
    Serving it from here means the two halves cannot drift: add a rule to the
    constants above and the form picks it up without a release.
    """
    return {
        "patient_type": {
            "field": "patient_types",
            "exclusions": [
                {
                    "codes": [first, second],
                    "labels": [_label(first), _label(second)],
                    "reason": why,
                }
                for first, second, why in PATIENT_TYPE_EXCLUSIONS
            ],
        },
        "patient_status": {
            "implications": [
                {"when": {when_field: when_value}, "then": forced, "reason": why}
                for when_field, when_value, forced, why in STATUS_IMPLICATIONS
            ],
        },
        "coverage_type": {
            # "No Coverage" has no column — it is the absence of active slots, so
            # only the form can render it. Published so the form's behaviour is
            # specified here rather than invented per screen.
            "no_coverage_is_derived": True,
            "no_coverage_excludes": [
                {"legacy_plan_type": plan, "insurance_type": rank}
                for plan in ("D", "M")
                for rank in ("primary", "secondary")
            ],
            "ranks": list(INSURANCE_RANKS),
            "requires_lower_rank": True,
        },
        # GAP-AP-25: the canonical value the column holds is the *code*; keys
        # and labels are accepted on write and folded. Published so the form
        # binds the dropdown's value to ``key1`` rather than the description.
        "responsible_party_relationship": {
            "field": "responsible_party_relationship",
            "canonical": "key1",
            "definition_group": "resp_party_rel",
            "self_code": RESP_PARTY_REL_SELF,
            "codes": [{"code": c, "label": lbl} for c, lbl in RESP_PARTY_RELATIONSHIPS],
        },
    }
