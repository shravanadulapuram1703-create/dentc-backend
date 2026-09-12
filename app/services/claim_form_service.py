"""ADA Dental Claim Form (2024) — the server-side assembler
(ADA-BE-1..14 of docs/claims/ada_claim_form_2024_backend_devreport.md, plus the
CLM-FO-1..4 fill-out boxes that report folds in).

The frontend had been building all 58 items in the browser from ~18 requests
and rendering them with jsPDF: the layout lived in the client, nothing was
audited, a form could not be produced for a batch, and every item whose data
had no column (Items 1-EPSDT, 2, 29a, 29b, 31a, 34/34a, 35, 36, 38, 39a, 40-47,
53a) printed blank or from a per-browser ``localStorage`` record.

This module is the one place that decides what each item is:

* ``assemble`` composes the whole form for one claim from the canonical rows —
  claim → patient → billed slot → other slot → providers → office → service
  lines → chart — in a handful of statements, and reports **where every
  derived value came from** (``*_source``) plus a ``warnings[]`` list, because
  a printed claim that silently fell back to the wrong NPI is a rejected claim.
  ``GET /insurance-claims/{id}/ada-claim-form`` returns it as JSON (the FE's
  fallback renderer can keep its layout and drop its 18 requests) and
  ``…/reports/ada-claim-form`` hands the same dict to ``ada_claim_pdf``.
* ``InsuranceClaimCRUD`` (ADA-BE-12/9) defaults ``treating_provider_id`` /
  ``billing_provider_id`` / ``office_id`` / ``ins_plan_id`` / ``carrier_id`` /
  ``other_ins_plan_id`` at creation and validates the fill-out vocabulary on
  every write; ``attach_procedure_to_claim`` is the same defaulting when the
  ledger assigns ``claim_id`` line by line (the FE's POST-then-PATCH shape).
* ``normalise_claim_line`` is the write-side rule for ``diagnosis_pointers`` /
  ``quantity`` on ``patient_procedures`` (ADA-BE-3/4).
* ``derive_missing_teeth`` / ``tooth_status`` / ``derive_date_last_srp`` are the
  chart-derived answers for Items 33 and 39a (ADA-BE-6/2) — uncapped queries,
  so a heavily charted patient no longer loses rows to a ``size=200`` page.

Design calls worth knowing:

* **Derivations never overwrite stored intent.** A stored ``date_last_srp``,
  ``missing_teeth`` or ``has_other_coverage`` wins over the derived value; NULL
  means "derive", and the response says which happened.
* **The billing NPI is the office's Type 2 NPI when the office has one** (ADA-BE-8),
  else the billing provider's Type 1 NPI *with a warning* when the office bills
  under a corporate name — that pairing is what payers reject.
* **Item 36 is true when either the biller asserted it or an active
  ``claim_consent`` signature exists** (ADA-BE-7). A captured consent is a
  better assertion than a checkbox, so it wins; the checkbox stays because a
  practice may hold the consent on paper.
* **Item 25 (area of oral cavity)** is the ADA two-digit code mapped from the
  stored quadrant token (``procedure_rules_service.AREA_OF_ORAL_CAVITY``), so
  the token set the print understands is the one the API validates.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.crud.base import CRUDBase
from app.db.models import (
    ChartCondition,
    Employer,
    InsuranceCarrier,
    InsuranceClaim,
    InsurancePlan,
    InsuranceSubscriber,
    Office,
    Patient,
    PatientInsurance,
    PatientProcedure,
    PatientSignature,
    ProcedureCode,
    Provider,
    ProviderInsuranceId,
)
from app.services import provider_taxonomy_service
from app.services import signature_service as sig_svc
from app.services.patient_rules_service import INSURANCE_RANKS
from app.services.procedure_rules_service import AREA_OF_ORAL_CAVITY, parse_tooth
from app.services.supporting_records_service import (
    EXTRACTION_CODES,
    MISSING_CONDITION_CODES,
    SUPPORTING_RECORD_FLAGS,
    _enclosures,
)

FORM_VERSION = "2024"
#: Rule E of the completion instructions: one form holds ten service lines.
LINES_PER_PAGE = 10
#: ADA-BE-7: the ``patient_signatures.signature_type`` that authorises the
#: Item 36 release-of-information / claim statement (837D CLM09).
CLAIM_CONSENT_SIGNATURE_TYPE = "claim_consent"
#: SIG-12: the shared FE pad writes ``claim_patient_consent`` for Item 36; both
#: spellings are Item 36 (``signature_service.CLAIM_ITEM_36_TYPES``).
CLAIM_CONSENT_SIGNATURE_TYPES = sig_svc.CLAIM_ITEM_36_TYPES
#: Item 39a: "Date of Last Scaling and Root Planing" is derived from these.
SRP_CODES: frozenset[str] = frozenset({"D4341", "D4342"})
#: Implant placement — the natural tooth is gone, so it is marked in Item 33.
IMPLANT_CODES: frozenset[str] = frozenset({"D6010", "D6011", "D6012", "D6013", "D6040", "D6050"})
IMPLANT_CONDITION_CODES: frozenset[str] = frozenset({"IMPLANT", "FND-IMPLANT"})
#: Item 34 diagnosis-code list qualifier.
ICD_QUALIFIERS: dict[str, str] = {"AB": "ICD-10-CM", "B": "ICD-9-CM"}
DEFAULT_ICD_QUALIFIER = "AB"
ACCIDENT_TYPES: tuple[str, ...] = ("occupational", "auto", "other")
DIAGNOSIS_LETTERS = "ABCD"
DEFAULT_PLACE_OF_TREATMENT = "11"  # CMS POS 11 = Office
#: Item 18 relationship codes (837D SBR02 / PAT01 buckets).
RELATIONSHIP_CODES: tuple[str, ...] = ("self", "spouse", "dependent", "other")
#: Universal permanent tooth ids — the grid Item 33 draws.
PERMANENT_TEETH: tuple[str, ...] = tuple(str(n) for n in range(1, 33))
_ICD_RE = re.compile(r"^[A-Z0-9][A-Z0-9.]{1,9}$")
_ZERO = Decimal("0")


# ── small helpers ─────────────────────────────────────────────────────────────
def _clean(value: Any) -> str | None:  # noqa: ANN401
    text = (str(value).strip() if value is not None else "")
    return text or None


def _upper(value: Any) -> str | None:  # noqa: ANN401
    text = _clean(value)
    return text.upper() if text else None


def _fail(code: str, field: str, message: str, **extra: Any) -> ValidationError:  # noqa: ANN401
    return ValidationError(message, details={"code": code, "field": field, **extra})


def sex_code(value: str | None) -> str:
    """Items 14 / 21: ``M`` | ``F`` | ``U``."""
    g = (value or "").strip().upper()[:1]
    return g if g in ("M", "F") else "U"


def relationship_code(value: str | None) -> str:
    """Item 18 from the free-text ``patient_insurance.relationship``."""
    text = (value or "").strip().lower()
    if not text:
        return "other"
    if text in ("self", "s", "patient", "subscriber"):
        return "self"
    if text.startswith("sp") or text == "husband" or text == "wife":
        return "spouse"
    if text in ("child", "c", "dependent", "d", "son", "daughter", "p") or text.startswith("dep") or text.startswith("chi"):
        return "dependent"
    return "other"


def area_code_for(quadrant: str | None, tooth: str | None) -> str | None:
    """Item 25 — the ADA two-digit area code from the stored quadrant token (or
    a legacy quadrant-in-tooth value)."""
    q = _upper(quadrant)
    if q and q in AREA_OF_ORAL_CAVITY:
        return AREA_OF_ORAL_CAVITY[q]
    t = _upper(tooth)
    if t and t in AREA_OF_ORAL_CAVITY:
        return AREA_OF_ORAL_CAVITY[t]
    return None


def normalise_pointers(value: Any) -> str | None:  # noqa: ANN401
    """``diagnosis_pointers``: letters A–D, upper-cased, de-duplicated, in the
    order given (priority order), at most four. ``"a,b"`` / ``"AB"`` / ``"A B"``
    all read the same. 422 ``invalid_diagnosis_pointer`` on anything else."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        raw = "".join(str(v) for v in value)
    else:
        raw = str(value)
    letters: list[str] = []
    for ch in re.sub(r"[\s,;/]+", "", raw).upper():
        if ch not in DIAGNOSIS_LETTERS:
            raise _fail("invalid_diagnosis_pointer", "diagnosis_pointers",
                        f"'{value}' is not a diagnosis pointer (letters A–D, e.g. 'AB')",
                        value=value, allowed=list(DIAGNOSIS_LETTERS))
        if ch not in letters:
            letters.append(ch)
    return "".join(letters) or None


def normalise_claim_line(payload: dict, current: Any = None) -> dict:  # noqa: ANN401
    """Write-side rule for the ADA-BE-3/4 line columns on ``patient_procedures``.
    Runs on every create / PATCH; only touches the keys the payload carries."""
    if "diagnosis_pointers" in payload:
        payload["diagnosis_pointers"] = normalise_pointers(payload["diagnosis_pointers"])
    if "quantity" in payload:
        qty = payload["quantity"]
        if qty is None:
            qty = 1
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            raise _fail("invalid_quantity", "quantity", f"'{payload['quantity']}' is not a whole number")
        if not 1 <= qty <= 99:
            raise _fail("invalid_quantity", "quantity", "quantity must be between 1 and 99 (ADA Item 29b)",
                        value=qty)
        payload["quantity"] = qty
    elif current is None:
        payload["quantity"] = 1
    return payload


def parse_missing_teeth(value: Any) -> list[str]:  # noqa: ANN401
    """``"1, 16,32"`` → ``["1", "16", "32"]`` (permanent Universal ids only,
    ordered, de-duplicated). 422 ``invalid_missing_tooth`` otherwise."""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple)) else re.split(r"[\s,;]+", str(value))
    out: list[str] = []
    for raw in items:
        text = str(raw).strip().upper()
        if not text:
            continue
        try:
            tooth = parse_tooth(text)
        except ValidationError:
            tooth = None
        if tooth is None or tooth.is_quadrant or tooth.raw not in PERMANENT_TEETH:
            raise _fail("invalid_missing_tooth", "missing_teeth",
                        f"'{raw}' is not a permanent Universal tooth number (1–32)", value=raw)
        if tooth.raw not in out:
            out.append(tooth.raw)
    return sorted(out, key=int)


def validate_fillout(payload: dict) -> dict:
    """The fill-out vocabulary, enforced on every claim write (create + PATCH).
    Codes are canonicalised, never invented: an unknown ``place_of_treatment``
    is a 422, because the value prints verbatim into a payer-parsed box."""
    if "accident_type" in payload:
        v = _clean(payload["accident_type"])
        v = v.lower() if v else None
        if v is not None and v not in ACCIDENT_TYPES:
            raise _fail("invalid_accident_type", "accident_type",
                        f"accident_type must be one of {', '.join(ACCIDENT_TYPES)}", allowed=list(ACCIDENT_TYPES))
        payload["accident_type"] = v
    if "accident_state" in payload:
        v = _upper(payload["accident_state"])
        if v is not None and not re.fullmatch(r"[A-Z]{2}", v):
            raise _fail("invalid_accident_state", "accident_state", "accident_state is a two-letter state code")
        payload["accident_state"] = v
    if "icd_qualifier" in payload:
        v = _upper(payload["icd_qualifier"])
        if v is not None and v not in ICD_QUALIFIERS:
            raise _fail("invalid_icd_qualifier", "icd_qualifier",
                        "icd_qualifier must be AB (ICD-10-CM) or B (ICD-9-CM)", allowed=list(ICD_QUALIFIERS))
        payload["icd_qualifier"] = v
    for key in ("icd_1", "icd_2", "icd_3", "icd_4"):
        if key in payload:
            v = _upper(payload[key])
            if v is not None and not _ICD_RE.fullmatch(v):
                raise _fail("invalid_icd_code", key, f"'{payload[key]}' is not an ICD code", value=payload[key])
            payload[key] = v
    if "place_of_treatment" in payload:
        v = _clean(payload["place_of_treatment"])
        if v is not None:
            v = v.zfill(2) if v.isdigit() and len(v) == 1 else v
            if not re.fullmatch(r"\d{2}", v):
                raise _fail("invalid_place_of_treatment", "place_of_treatment",
                            "place_of_treatment is a two-digit CMS place-of-service code (e.g. 11)")
        payload["place_of_treatment"] = v
    if "missing_teeth" in payload:
        teeth = parse_missing_teeth(payload["missing_teeth"])
        payload["missing_teeth"] = ",".join(teeth) if teeth else None
    if "ortho_months_remaining" in payload and payload["ortho_months_remaining"] is not None:
        if not 0 <= int(payload["ortho_months_remaining"]) <= 99:
            raise _fail("invalid_ortho_months", "ortho_months_remaining", "ortho_months_remaining is 0–99")
    if "other_fees" in payload and payload["other_fees"] is not None:
        if Decimal(str(payload["other_fees"])) < _ZERO:
            raise _fail("invalid_other_fees", "other_fees", "other_fees cannot be negative")
    if "predetermination_number" in payload:
        payload["predetermination_number"] = _clean(payload["predetermination_number"])
    return payload


# ── chart-derived items ───────────────────────────────────────────────────────
def derive_date_last_srp(db: Session, patient_id: int, *, on_or_before: date | None = None) -> date | None:
    """Item 39a: the most recent completed (non-void) D4341/D4342 for the patient."""
    stmt = (
        select(func.max(PatientProcedure.date_of_service))
        .where(PatientProcedure.patient_id == patient_id,
               PatientProcedure.procedure_code.in_(sorted(SRP_CODES)),
               PatientProcedure.is_void.is_(False),
               PatientProcedure.is_archived.is_(False))
    )
    if on_or_before is not None:
        stmt = stmt.where(PatientProcedure.date_of_service <= on_or_before)
    return db.execute(stmt).scalar_one_or_none()


def tooth_status(db: Session, patient_id: int) -> list[dict[str, Any]]:
    """Per-tooth status for every permanent tooth (ADA-BE-6.1 / INTEG-1):
    ``present`` | ``missing`` | ``extracted`` | ``implant``, with the evidence
    row and date. Two uncapped statements — never a paged list."""
    status: dict[str, dict[str, Any]] = {t: {"tooth": t, "status": "present", "source": None, "date": None,
                                             "condition_code": None, "procedure_code": None}
                                         for t in PERMANENT_TEETH}
    rank = {"present": 0, "missing": 1, "extracted": 2, "implant": 3}

    def _set(tooth: str | None, new_status: str, **evidence: Any) -> None:  # noqa: ANN401
        parsed = parse_tooth(tooth)
        if parsed is None or parsed.is_quadrant or parsed.raw not in status:
            return
        row = status[parsed.raw]
        if rank[new_status] >= rank[row["status"]]:
            row.update({"status": new_status, **evidence})

    conditions = db.execute(
        select(ChartCondition.tooth, ChartCondition.condition_code, ChartCondition.activity_date)
        .where(ChartCondition.patient_id == patient_id, ChartCondition.is_inactive.is_(False),
               func.upper(ChartCondition.condition_code).in_(
                   sorted(MISSING_CONDITION_CODES | IMPLANT_CONDITION_CODES)))
    ).all()
    for tooth, code, when in conditions:
        code_u = (code or "").upper()
        kind = "implant" if code_u in IMPLANT_CONDITION_CODES else (
            "extracted" if code_u.startswith("EXTRACT") else "missing")
        _set(tooth, kind, source="chart_condition", date=when, condition_code=code_u)
    procs = db.execute(
        select(PatientProcedure.tooth, PatientProcedure.procedure_code, PatientProcedure.date_of_service)
        .where(PatientProcedure.patient_id == patient_id, PatientProcedure.is_void.is_(False),
               PatientProcedure.is_archived.is_(False),
               PatientProcedure.procedure_code.in_(sorted(EXTRACTION_CODES | IMPLANT_CODES)))
    ).all()
    for tooth, code, when in procs:
        kind = "implant" if code in IMPLANT_CODES else "extracted"
        _set(tooth, kind, source="patient_procedure", date=when, procedure_code=code)
    return [status[t] for t in PERMANENT_TEETH]


def derive_missing_teeth(db: Session, patient_id: int) -> list[str]:
    """Item 33 from the chart: every permanent tooth charted missing / extracted
    / replaced by an implant."""
    return [row["tooth"] for row in tooth_status(db, patient_id) if row["status"] != "present"]


def claim_consent_patient_ids(db: Session, patient_ids: set[int]) -> set[int]:
    """ADA-BE-7: which of these patients hold an active ``claim_consent``
    signature (batched — one statement for a whole list page)."""
    if not patient_ids:
        return set()
    rows = db.execute(
        select(PatientSignature.patient_id).where(
            PatientSignature.patient_id.in_(patient_ids),
            PatientSignature.signature_type.in_(CLAIM_CONSENT_SIGNATURE_TYPES),
            PatientSignature.is_active.is_(True),
        ).distinct()
    ).scalars().all()
    return set(rows)


def _claim_consent_signature(db: Session, patient_id: int) -> PatientSignature | None:
    return db.execute(
        select(PatientSignature).where(
            PatientSignature.patient_id == patient_id,
            PatientSignature.signature_type.in_(CLAIM_CONSENT_SIGNATURE_TYPES),
            PatientSignature.is_active.is_(True),
        ).order_by(PatientSignature.signed_at.desc().nullslast(), PatientSignature.id.desc())
    ).scalars().first()


# ── slots ─────────────────────────────────────────────────────────────────────
def _slots(db: Session, patient_id: int) -> list[dict[str, Any]]:
    """Active coverage slots with plan / carrier / subscriber / employer, ordered
    dental-first then by rank — the order the print picks an "other" plan in."""
    stmt = (
        select(PatientInsurance, InsurancePlan, InsuranceCarrier, InsuranceSubscriber, Employer)
        .outerjoin(InsurancePlan, InsurancePlan.id == PatientInsurance.ins_plan_id)
        .outerjoin(InsuranceCarrier, InsuranceCarrier.id == InsurancePlan.carrier_id)
        .outerjoin(InsuranceSubscriber, InsuranceSubscriber.id == PatientInsurance.subscriber_id)
        .outerjoin(Employer, Employer.id == InsurancePlan.employer_id)
        .where(PatientInsurance.patient_id == patient_id, PatientInsurance.is_active.is_(True))
    )
    out = []
    for rec, plan, carrier, sub, employer in db.execute(stmt).all():
        out.append({"record": rec, "plan": plan, "carrier": carrier, "subscriber": sub, "employer": employer})

    def _key(slot: dict) -> tuple:
        cat = (slot["record"].legacy_plan_type or "").strip().upper()[:1]
        rank = (slot["record"].insurance_type or "").strip().lower()
        return (0 if cat == "D" else 1 if cat == "M" else 2,
                INSURANCE_RANKS.index(rank) if rank in INSURANCE_RANKS else 99, slot["record"].id)

    return sorted(out, key=_key)


def _billed_slot(slots: list[dict], claim: InsuranceClaim) -> dict | None:
    if claim.ins_plan_id is not None:
        for slot in slots:
            if slot["record"].ins_plan_id == claim.ins_plan_id:
                return slot
    if claim.billing_order:
        rank = claim.billing_order.strip().lower()
        for slot in slots:
            if (slot["record"].insurance_type or "").lower() == rank:
                return slot
    return slots[0] if slots else None


def resolve_other_slot(
    db: Session, claim: InsuranceClaim, slots: list[dict], billed: dict | None,
) -> tuple[dict | None, str]:
    """Items 4–11: the *other* plan. A stored ``other_ins_plan_id`` (ADA-BE-9)
    wins; else the first active slot that is not the billed one, dental
    before medical. -> (slot-or-None, source)."""
    if claim.other_ins_plan_id is not None:
        for slot in slots:
            if slot["record"].ins_plan_id == claim.other_ins_plan_id:
                return slot, "stored"
        plan = db.get(InsurancePlan, claim.other_ins_plan_id)
        if plan is not None:
            carrier = db.get(InsuranceCarrier, plan.carrier_id) if plan.carrier_id else None
            employer = db.get(Employer, plan.employer_id) if plan.employer_id else None
            return {"record": None, "plan": plan, "carrier": carrier, "subscriber": None,
                    "employer": employer}, "stored_plan_only"
    billed_id = billed["record"].id if billed and billed.get("record") is not None else None
    for slot in slots:
        if slot["record"].id != billed_id:
            return slot, "derived"
    return None, "none"


def default_other_plan_id(db: Session, patient_id: int, ins_plan_id: int | None) -> int | None:
    """What ``InsuranceClaimCRUD`` captures at creation (ADA-BE-9)."""
    slots = _slots(db, patient_id)
    billed = next((s for s in slots if s["record"].ins_plan_id == ins_plan_id), None) if ins_plan_id else None
    other, _src = resolve_other_slot(db, InsuranceClaim(ins_plan_id=ins_plan_id, other_ins_plan_id=None), slots, billed)
    return other["record"].ins_plan_id if other and other.get("record") is not None else None


# ── providers ─────────────────────────────────────────────────────────────────
def _provider(db: Session, provider_id: str | None, tenant_id: int) -> Provider | None:
    if not provider_id:
        return None
    row = db.get(Provider, provider_id)
    return row if row is not None and row.tenant_id == tenant_id else None


def pick_treating_provider(db: Session, procs: list[PatientProcedure]) -> str | None:
    """ADA-BE-12: the provider of the procedures being claimed. Majority wins
    (ties → the earliest line); a mix is a 422 ``claim_provider_mismatch``
    only when one of the providers is flagged ``print_separate_claim_form``,
    because that flag is the practice saying "never on one form with anyone"."""
    ids = [p.provider_id for p in procs if p.provider_id]
    if not ids:
        return None
    distinct = list(dict.fromkeys(ids))
    if len(distinct) > 1:
        flagged = db.execute(
            select(Provider.id).where(Provider.id.in_(distinct), Provider.print_separate_claim_form.is_(True))
        ).scalars().all()
        if flagged:
            raise ValidationError(
                "The procedures span providers that must print on separate claim forms",
                details={"code": "claim_provider_mismatch", "provider_ids": distinct,
                         "print_separate_claim_form": list(flagged),
                         "hint": "Create one claim per provider."},
            )
    counts = Counter(ids)
    best = max(counts.values())
    for pid in ids:  # earliest line among the tied majority
        if counts[pid] == best:
            return pid
    return distinct[0]  # pragma: no cover


def attach_procedure_to_claim(db: Session, claim: InsuranceClaim, proc: PatientProcedure) -> None:
    """The per-line half of ADA-BE-12: when the ledger PATCHes ``claim_id`` onto a
    charge, fill the claim's provider ids from that charge if they are still
    NULL; refuse the attach only when the charge's provider must print alone."""
    if claim.treating_provider_id is None and proc.provider_id:
        claim.treating_provider_id = proc.provider_id
    elif proc.provider_id and claim.treating_provider_id != proc.provider_id:
        flagged = db.execute(
            select(Provider.id).where(Provider.id.in_([proc.provider_id, claim.treating_provider_id]),
                                      Provider.print_separate_claim_form.is_(True))
        ).scalars().all()
        if flagged:
            raise ValidationError(
                "This procedure's provider must print on a separate claim form",
                details={"code": "claim_provider_mismatch", "claim_id": claim.id,
                         "claim_provider_id": claim.treating_provider_id, "procedure_provider_id": proc.provider_id,
                         "print_separate_claim_form": list(flagged)},
            )
    if claim.billing_provider_id is None:
        office = db.get(Office, claim.office_id) if claim.office_id else None
        claim.billing_provider_id = (office.billing_provider_id if office else None) or claim.treating_provider_id
    if claim.date_of_service_from is None or (proc.date_of_service and proc.date_of_service < claim.date_of_service_from):
        claim.date_of_service_from = proc.date_of_service
    if claim.date_of_service_to is None or (proc.date_of_service and proc.date_of_service > claim.date_of_service_to):
        claim.date_of_service_to = proc.date_of_service


# ── the claim CRUD (ADA-BE-9/12 + fill-out validation) ────────────────────────
class InsuranceClaimCRUD(CRUDBase[InsuranceClaim]):
    """Generic CRUD plus the creation defaults the ADA form depends on.

    ``procedure_ids`` (not a column) lets the ledger create the claim and link
    its lines in **one** transaction — the previous POST + per-line PATCH shape
    left a window where the claim existed with no provider, no dates and no
    lines, which is exactly the row the print report found (ADA-BE-12)."""

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        procedure_ids = payload.pop("procedure_ids", None) or []
        validate_fillout(payload)
        patient = db.get(Patient, payload.get("patient_id"))
        if patient is None or (tenant_id is not None and patient.tenant_id != tenant_id):
            raise NotFoundError(f"Patient '{payload.get('patient_id')}' was not found")
        payload.setdefault("id", uuid7())
        payload.setdefault("claim_number", payload["id"])
        if payload.get("office_id") is None:
            payload["office_id"] = patient.home_office_id

        procs: list[PatientProcedure] = []
        if procedure_ids:
            procs = list(db.execute(
                select(PatientProcedure).where(PatientProcedure.id.in_(procedure_ids))
            ).scalars().all())
            found = {p.id for p in procs}
            missing = [pid for pid in procedure_ids if pid not in found]
            if missing:
                raise ValidationError("One or more procedures were not found",
                                      details={"code": "procedure_not_found", "procedure_ids": missing})
            for p in procs:
                if p.patient_id != patient.id:
                    raise ValidationError("A procedure belongs to another patient",
                                          details={"code": "procedure_patient_mismatch", "procedure_id": p.id})
                if p.is_void:
                    raise ValidationError("A voided procedure cannot be claimed",
                                          details={"code": "procedure_void", "procedure_id": p.id})
                if p.hold_claim:
                    raise ValidationError("A procedure on hold cannot be claimed",
                                          details={"code": "procedure_on_hold_claim", "procedure_id": p.id})
                if p.claim_id and p.claim_id != payload["id"]:
                    raise ValidationError("A procedure is already on another claim",
                                          details={"code": "procedure_already_claimed", "procedure_id": p.id,
                                                   "claim_id": p.claim_id})
            procs.sort(key=lambda p: (p.date_of_service or date.min, p.id))

        if payload.get("treating_provider_id") is None and procs:
            payload["treating_provider_id"] = pick_treating_provider(db, procs)
        if payload.get("treating_provider_id") is None and patient.preferred_provider_id:
            payload["treating_provider_id"] = patient.preferred_provider_id
        if payload.get("billing_provider_id") is None:
            office = db.get(Office, payload["office_id"]) if payload.get("office_id") else None
            payload["billing_provider_id"] = (office.billing_provider_id if office else None) \
                or payload.get("treating_provider_id")

        slots = _slots(db, patient.id)
        if payload.get("ins_plan_id") is None and slots:
            rank = (payload.get("billing_order") or "primary").strip().lower()
            pick = next((s for s in slots if (s["record"].insurance_type or "").lower() == rank), slots[0])
            payload["ins_plan_id"] = pick["record"].ins_plan_id
        if payload.get("carrier_id") is None and payload.get("ins_plan_id"):
            plan = db.get(InsurancePlan, payload["ins_plan_id"])
            payload["carrier_id"] = plan.carrier_id if plan else None
        if "other_ins_plan_id" not in payload:
            payload["other_ins_plan_id"] = default_other_plan_id(db, patient.id, payload.get("ins_plan_id"))

        if procs:
            dates = [p.date_of_service for p in procs if p.date_of_service]
            if dates:
                payload.setdefault("date_of_service_from", min(dates))
                payload.setdefault("date_of_service_to", max(dates))
            if not payload.get("total_billed"):
                payload["total_billed"] = sum((p.fee or _ZERO) for p in procs)
            if not payload.get("est_insurance"):
                payload["est_insurance"] = sum((p.insurance_estimate or _ZERO) for p in procs)
        if tenant_id is not None and hasattr(self.model, "tenant_id"):
            payload.setdefault("tenant_id", tenant_id)
        if created_by is not None and self._is_int_col("created_by"):
            payload.setdefault("created_by", created_by)
        obj = self.model(**payload)
        db.add(obj)
        db.flush()
        for p in procs:
            p.claim_id = obj.id
        self._commit(db)
        db.refresh(obj)
        self._audit(obj, after={k: v for k, v in payload.items()})
        return obj

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        payload = validate_fillout(dict(data))
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)


# ── the assembler ─────────────────────────────────────────────────────────────
def _get_claim(db: Session, claim_id: str, tenant_id: int) -> tuple[InsuranceClaim, Patient]:
    row = db.execute(
        select(InsuranceClaim, Patient).join(Patient, Patient.id == InsuranceClaim.patient_id)
        .where(InsuranceClaim.id == claim_id, Patient.tenant_id == tenant_id)
    ).first()
    if row is None:
        raise NotFoundError(f"InsuranceClaim '{claim_id}' was not found")
    return row[0], row[1]


def _address(line1, line2, city, state, zip_code) -> dict[str, str | None]:  # noqa: ANN001
    return {"address_line1": _clean(line1), "address_line2": _clean(line2), "city": _clean(city),
            "state": _clean(state), "zip": _clean(zip_code)}


def _subscriber_block(slot: dict | None) -> dict[str, Any]:
    sub: InsuranceSubscriber | None = slot["subscriber"] if slot else None
    plan: InsurancePlan | None = slot["plan"] if slot else None
    employer: Employer | None = slot["employer"] if slot else None
    rec: PatientInsurance | None = slot["record"] if slot else None
    return {
        "subscriber_id": sub.id if sub else None,
        "last_name": _clean(sub.sub_last_name) if sub else None,
        "first_name": _clean(sub.sub_first_name) if sub else None,
        "middle_initial": _clean(sub.sub_mi)[:1] if sub and _clean(sub.sub_mi) else None,
        "suffix": _clean(sub.sub_suffix) if sub else None,
        **(_address(sub.sub_address, sub.sub_address2, sub.sub_city, sub.sub_state, sub.sub_zip) if sub
           else _address(None, None, None, None, None)),
        "dob": sub.sub_dob if sub else None,
        "sex": sex_code(sub.sub_gender) if sub else "U",
        "member_id": _clean(sub.sub_member_id) if sub else None,
        "group_number": (_clean(sub.group_number) if sub and _clean(sub.group_number) else None)
        or (_clean(plan.group_number) if plan else None),
        "employer_name": (_clean(employer.name) if employer else None)
        or (_clean(getattr(plan, "employer_name", None)) if plan else None),
        "relationship": _clean(rec.relationship) if rec else None,
        "relationship_code": relationship_code(rec.relationship if rec else None),
        "ins_plan_id": plan.id if plan else None,
        "plan_type": _clean(plan.plan_type) if plan else None,
    }


def _carrier_block(slot: dict | None) -> dict[str, Any]:
    carrier: InsuranceCarrier | None = slot["carrier"] if slot else None
    if carrier is None:
        return {"carrier_id": None, "name": None, "payer_id": None,
                **_address(None, None, None, None, None)}
    return {"carrier_id": carrier.id, "name": _clean(carrier.name), "payer_id": _clean(carrier.payer_id),
            **_address(carrier.address, carrier.address2, carrier.city, carrier.state, carrier.zip)}


def _provider_block(p: Provider | None) -> dict[str, Any]:
    if p is None:
        return {"provider_id": None, "name": None, "npi": None, "license": None, "tax_id": None,
                "phone": None, "specialty": None}
    return {"provider_id": p.id, "name": _clean(p.name), "npi": _clean(p.npi), "license": _clean(p.license),
            "tax_id": _clean(p.tax_id), "phone": _clean(p.phone), "specialty": _clean(p.specialty)}


def _additional_ids(db: Session, provider_ids: set[str], carrier_id: int | None) -> dict[str, str | None]:
    """Items 52a / 58: the (provider, carrier) legacy insurance id."""
    if not provider_ids or carrier_id is None:
        return {}
    rows = db.execute(
        select(ProviderInsuranceId.provider_id, ProviderInsuranceId.ins_id)
        .where(ProviderInsuranceId.provider_id.in_(provider_ids), ProviderInsuranceId.carrier_id == carrier_id)
        .order_by(ProviderInsuranceId.id.desc())
    ).all()
    out: dict[str, str | None] = {}
    for pid, ins_id in rows:
        out.setdefault(pid, _clean(ins_id))
    return out


def assemble(db: Session, claim_id: str, tenant_id: int, *,
             include_signature_images: bool = False) -> dict[str, Any]:
    """The whole 2024 form for one claim — see the module doc for the rules.

    ``include_signature_images`` (SIG-16) embeds the captured signature images
    (data URLs, 20–40 KB each) under ``authorizations.signatures`` — on for the
    PDF renderers, off for the JSON read and the submit snapshot."""
    claim, patient = _get_claim(db, claim_id, tenant_id)
    warnings: list[dict[str, Any]] = []

    def warn(code: str, item: str, message: str, **extra: Any) -> None:  # noqa: ANN401
        warnings.append({"code": code, "item": item, "message": message, **extra})

    # ── coverage ───────────────────────────────────────────────────────────
    slots = _slots(db, patient.id)
    billed = _billed_slot(slots, claim)
    if billed is None and claim.ins_plan_id is not None:
        plan = db.get(InsurancePlan, claim.ins_plan_id)
        if plan is not None:
            billed = {"record": None, "plan": plan,
                      "carrier": db.get(InsuranceCarrier, plan.carrier_id) if plan.carrier_id else None,
                      "subscriber": None,
                      "employer": db.get(Employer, plan.employer_id) if plan.employer_id else None}
            warn("billed_slot_inactive", "12", "The billed plan is no longer an active coverage slot; "
                 "subscriber details could not be resolved")
    if billed is not None and billed["carrier"] is None and claim.carrier_id is not None:
        billed = dict(billed, carrier=db.get(InsuranceCarrier, claim.carrier_id))
    payer = _carrier_block(billed)
    if payer["name"] is None:
        warn("payer_missing", "3", "No carrier resolves for this claim")
    subscriber = _subscriber_block(billed)
    if subscriber["last_name"] is None:
        warn("subscriber_missing", "12", "No subscriber is linked to the billed coverage slot")

    other_slot, other_source = resolve_other_slot(db, claim, slots, billed)
    has_other = claim.has_other_coverage if claim.has_other_coverage is not None else other_slot is not None
    other = {
        "has_other_coverage": bool(has_other),
        "has_other_coverage_source": "stored" if claim.has_other_coverage is not None else "derived",
        "plan_source": other_source,
        "subscriber": _subscriber_block(other_slot) if (has_other and other_slot) else None,
        "carrier": _carrier_block(other_slot) if (has_other and other_slot) else None,
        "coverage_type": (
            "dental" if other_slot and other_slot.get("record") is not None
            and (other_slot["record"].legacy_plan_type or "").upper().startswith("D")
            else "medical" if other_slot and other_slot.get("record") is not None else None
        ),
    }
    if has_other and other_slot is None:
        warn("other_coverage_unresolved", "4", "has_other_coverage is set but no other plan resolves")
    if other_source == "stored_plan_only":
        warn("other_plan_subscriber_unresolved", "5",
             "other_ins_plan_id no longer matches an active slot; Items 5–11 print the plan only")

    # ── service lines ──────────────────────────────────────────────────────
    procs = list(db.execute(
        select(PatientProcedure)
        .where(PatientProcedure.claim_id == claim.id, PatientProcedure.is_void.is_(False))
        .order_by(PatientProcedure.date_of_service, PatientProcedure.id)
    ).scalars().all())
    codes = {p.procedure_code for p in procs}
    code_rows: dict[str, ProcedureCode] = {
        r.code: r for r in db.execute(select(ProcedureCode).where(ProcedureCode.code.in_(codes))).scalars()
    } if codes else {}
    icd = {"A": _clean(claim.icd_1), "B": _clean(claim.icd_2), "C": _clean(claim.icd_3), "D": _clean(claim.icd_4)}
    lines: list[dict[str, Any]] = []
    for n, p in enumerate(procs, start=1):
        code_row = code_rows.get(p.procedure_code)
        pointers = _clean(p.diagnosis_pointers)
        if pointers:
            dangling = [ch for ch in pointers if not icd.get(ch)]
            if dangling:
                warn("pointer_without_diagnosis", "29a",
                     f"Line {n} points at diagnosis {', '.join(dangling)} but that code is blank on the claim",
                     line_no=n, procedure_id=p.id)
        lines.append({
            "line_no": n,
            "page_no": (n - 1) // LINES_PER_PAGE + 1,
            "procedure_id": p.id,
            "date_of_service": p.date_of_service,
            "area_of_oral_cavity": area_code_for(p.quadrant, p.tooth),
            "tooth_system": "JP",
            "tooth": _clean(p.tooth) if not (parse_tooth(p.tooth) and parse_tooth(p.tooth).is_quadrant) else None,
            "surface": _clean(p.surface),
            "procedure_code": p.procedure_code,
            "diagnosis_pointers": pointers,
            "quantity": int(p.quantity or 1),
            "description": _clean(code_row.description) if code_row else None,
            "fee": p.fee if p.fee is not None else _ZERO,
            "provider_id": p.provider_id,
        })
    if not lines:
        warn("no_service_lines", "24", "The claim has no non-void procedures")
    line_providers = list(dict.fromkeys(p.provider_id for p in procs if p.provider_id))
    if len(line_providers) > 1:
        warn("procedure_provider_mismatch", "53",
             "The service lines span more than one provider", provider_ids=line_providers)
    pages = max(1, math.ceil(len(lines) / LINES_PER_PAGE))
    flags_on_claim = {f for r in code_rows.values() for f in SUPPORTING_RECORD_FLAGS if getattr(r, f, False)}

    # ── providers / office ─────────────────────────────────────────────────
    office = db.get(Office, claim.office_id) if claim.office_id else None
    if office is None and patient.home_office_id:
        office = db.get(Office, patient.home_office_id)
    treating = _provider(db, claim.treating_provider_id, tenant_id)
    treating_source = "claim"
    if treating is None:
        counts = Counter(p.provider_id for p in procs if p.provider_id)
        if counts:
            treating = _provider(db, counts.most_common(1)[0][0], tenant_id)
            treating_source = "procedures"
    if treating is None and patient.preferred_provider_id:
        treating = _provider(db, patient.preferred_provider_id, tenant_id)
        treating_source = "preferred_provider"
    if treating is None:
        treating_source = "none"
        warn("treating_provider_unresolved", "53", "No treating provider resolves for this claim")
    billing = _provider(db, claim.billing_provider_id, tenant_id)
    billing_source = "claim"
    if billing is None and office is not None and office.billing_provider_id:
        billing = _provider(db, office.billing_provider_id, tenant_id)
        billing_source = "office"
    if billing is None:
        billing = treating
        billing_source = "treating" if treating else "none"

    carrier_id = payer["carrier_id"]
    add_ids = _additional_ids(db, {p.id for p in (treating, billing) if p}, carrier_id)

    office_npi = _clean(office.npi) if office else None
    entity_bills = bool(office_npi)
    if office_npi:
        billing_npi, npi_type, npi_source = office_npi, "2", "office"
    else:
        billing_npi, npi_type, npi_source = (_clean(billing.npi) if billing else None), "1", "billing_provider"
        if office is not None and _clean(office.corporate_name):
            warn("billing_entity_npi_missing", "49",
                 "The office bills under a corporate name but has no Type 2 NPI (offices.npi); "
                 "the billing provider's Type 1 NPI is printed instead")
    if billing_npi is None:
        warn("billing_npi_missing", "49", "No billing NPI resolves")
    if entity_bills and not (office and office.use_billing_license):
        billing_license = None
    else:
        billing_license = _clean(billing.license) if billing else None
    billing_block = {
        "name": (_clean(office.corporate_name) or _clean(office.name)) if office else (
            _clean(billing.name) if billing else None),
        **(_address(office.address_line1, office.address_line2, office.city, office.state, office.zip) if office
           else _address(None, None, None, None, None)),
        "npi": billing_npi, "npi_type": npi_type, "npi_source": npi_source,
        "license": billing_license,
        "tax_id": (_clean(office.tax_id) if office else None) or (_clean(billing.tax_id) if billing else None),
        "phone": (_clean(office.phone) if office else None) or (_clean(billing.phone) if billing else None),
        "additional_provider_id": add_ids.get(billing.id) if billing else None,
        "provider_id": billing.id if billing else None,
        "provider_source": billing_source,
        "office_id": office.id if office else None,
    }
    if office is not None and _clean(office.treatment_address_line1):
        location = _address(office.treatment_address_line1, office.treatment_address_line2,
                            office.treatment_city, office.treatment_state, office.treatment_zip)
        location_source = "treatment_address"
    elif office is not None:
        location = _address(office.address_line1, office.address_line2, office.city, office.state, office.zip)
        location_source = "office_address"
    else:
        location = _address(None, None, None, None, None)
        location_source = "none"
    if location_source == "office_address" and re.search(r"\bP\.?\s?O\.?\s*BOX\b", (location["address_line1"] or "").upper()):
        warn("treatment_location_is_po_box", "56",
             "Item 56 must be a physical street address; set offices.treatment_address_* (ADA-BE-13)")
    taxonomy, taxonomy_source = provider_taxonomy_service.effective_code(
        treating.taxonomy_code if treating else None, treating.specialty if treating else None)
    treating_block = {
        **_provider_block(treating),
        "provider_source": treating_source,
        "is_locum_tenens": bool(claim.is_locum_tenens),
        "additional_provider_id": add_ids.get(treating.id) if treating else None,
        "specialty_code": taxonomy,
        "specialty_code_source": taxonomy_source,
        "specialty_label": provider_taxonomy_service.label_for(taxonomy),
        "location": location,
        "location_source": location_source,
        "phone": (_clean(treating.phone) if treating else None) or (_clean(office.phone) if office else None),
    }
    if treating is not None and not _clean(treating.npi):
        warn("treating_npi_missing", "54", "The treating provider has no NPI")

    # ── ancillary ─────────────────────────────────────────────────────────
    if claim.missing_teeth:
        missing = parse_missing_teeth(claim.missing_teeth)
        missing_source = "claim"
    else:
        missing = derive_missing_teeth(db, patient.id)
        missing_source = "chart"
    if claim.date_last_srp is not None:
        last_srp, srp_source = claim.date_last_srp, "claim"
    else:
        last_srp = derive_date_last_srp(db, patient.id, on_or_before=claim.date_of_service_to)
        srp_source = "derived" if last_srp else "none"
    # SIG-16: the three signature lines — pinned to this claim → patient's
    # latest of that type → (Item 53) the treating provider's store / user.
    signatures = sig_svc.resolve_claim_signatures(
        db, tenant_id, claim, treating_provider_id=treating.id if treating else None,
        include_images=include_signature_images,
    )
    for item in ("item_36", "item_37", "item_53"):
        slot = signatures[item]
        if slot["signature_id"] is not None and slot["legacy_sig_string_only"]:
            warn("signature_not_printable", item.replace("item_", ""),
                 "The resolved signature is a legacy Topaz SigString with no image; the line prints blank",
                 signature_id=slot["signature_id"])
    consent = _claim_consent_signature(db, patient.id)
    if signatures["item_36"]["signature_id"] is not None:
        signature_on_file, signature_source = True, "claim_consent_signature"
    elif claim.signature_on_file:
        signature_on_file, signature_source = True, "claim"
    else:
        signature_on_file, signature_source = False, "none"
    total_lines = sum((line["fee"] for line in lines), _ZERO)
    other_fees = claim.other_fees
    transaction_type = "epsdt" if claim.is_epsdt else ("predetermination" if claim.is_preauth else "statement")

    return {
        "form_version": FORM_VERSION,
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "patient_id": patient.id,
        "status": claim.status,
        "pages": pages,
        "lines_per_page": LINES_PER_PAGE,
        "header": {
            "transaction_type": transaction_type,
            "is_preauth": bool(claim.is_preauth),
            "is_epsdt": bool(claim.is_epsdt),
            "predetermination_number": _clean(claim.predetermination_number),
        },
        "payer": payer,
        "other_coverage": other,
        "subscriber": subscriber,
        "patient": {
            "patient_id": patient.id,
            "last_name": _clean(patient.last_name),
            "first_name": _clean(patient.first_name),
            "middle_initial": (_clean(patient.middle_initial) or _clean(patient.middle_name) or "")[:1] or None,
            "suffix": _clean(patient.suffix),
            **_address(patient.address_line1, patient.address_line2, patient.city, patient.state, patient.zip),
            "dob": patient.dob,
            "sex": sex_code(patient.gender),
            "chart_no": _clean(patient.chart_no),
            "relationship_to_subscriber": subscriber["relationship_code"],
        },
        "service_lines": lines,
        "fees": {
            "lines_total": total_lines,
            "other_fees": other_fees,
            "total_fee": total_lines + (other_fees or _ZERO),
        },
        "missing_teeth": {"teeth": missing, "source": missing_source},
        "diagnosis": {"qualifier": _clean(claim.icd_qualifier) or DEFAULT_ICD_QUALIFIER, "codes": icd},
        "remarks": _clean(claim.remarks),
        "authorizations": {
            "signature_on_file": signature_on_file,
            "signature_source": signature_source,
            "consent_signature_id": signatures["item_36"]["signature_id"] or (consent.id if consent else None),
            "consent_signed_at": signatures["item_36"]["signed_at"] or (consent.signed_at if consent else None),
            "assignment_of_benefits": bool(patient.assign_benefits)
            or signatures["item_37"]["signature_id"] is not None,
            "signatures": signatures,
        },
        "ancillary": {
            "place_of_treatment": _clean(claim.place_of_treatment) or DEFAULT_PLACE_OF_TREATMENT,
            "place_of_treatment_source": "claim" if _clean(claim.place_of_treatment) else "default",
            "enclosures": _enclosures(db, claim, flags_on_claim),
            "date_last_srp": last_srp,
            "date_last_srp_source": srp_source,
            "is_ortho": bool(claim.is_ortho),
            "ortho_appliance_date": claim.ortho_appliance_date,
            "ortho_months_remaining": claim.ortho_months_remaining,
            "prosthesis_replacement": bool(claim.prosthesis_replacement),
            "prosthesis_prior_date": claim.prosthesis_prior_date,
            "accident_type": _clean(claim.accident_type),
            "accident_date": claim.accident_date,
            "accident_state": _clean(claim.accident_state),
        },
        "billing": billing_block,
        "treating": treating_block,
        "warnings": warnings,
    }


# ── published rules ───────────────────────────────────────────────────────────
def rules_metadata() -> dict[str, Any]:
    """``GET /metadata/ada-claim-form-rules`` — every vocabulary the form's
    write path validates and the print interprets, so a client can drive the
    fill-out dialog from the same table."""
    return {
        "form_version": FORM_VERSION,
        "lines_per_page": LINES_PER_PAGE,
        "endpoints": {
            "json": "GET /insurance-claims/{claim_id}/ada-claim-form",
            "pdf": "GET /insurance-claims/{claim_id}/reports/ada-claim-form?mode=form|overlay&offset_x=&offset_y=",
            "batch_pdf": "POST /insurance-claims/reports/ada-claim-form {claim_ids: [...], mode}",
            "tooth_status": "GET /patients/{patient_id}/tooth-status",
        },
        "pdf_modes": {"form": "full form drawn on plain paper", "overlay": "data only, for pre-printed stock"},
        "transaction_types": ["statement", "predetermination", "epsdt"],
        "icd_qualifiers": [{"code": k, "label": v} for k, v in ICD_QUALIFIERS.items()],
        "diagnosis_pointers": {"letters": list(DIAGNOSIS_LETTERS), "max": 4,
                               "storage": "priority-ordered letters, e.g. 'AB'"},
        "quantity": {"min": 1, "max": 99, "default": 1},
        "accident_types": list(ACCIDENT_TYPES),
        "relationship_codes": list(RELATIONSHIP_CODES),
        "place_of_treatment": {"default": DEFAULT_PLACE_OF_TREATMENT,
                               "catalog": "GET /place-of-service-codes (CMS POS codes, per tenant)"},
        "area_of_oral_cavity": [{"token": k, "code": v} for k, v in AREA_OF_ORAL_CAVITY.items()],
        "missing_teeth": {"teeth": list(PERMANENT_TEETH), "storage": "comma list, e.g. '1,16,17'",
                          "null_means": "derive from chart_conditions + extraction/implant charges"},
        "date_last_srp": {"derived_from": sorted(SRP_CODES), "null_means": "derive"},
        "signatures": {
            "items": {k: list(v) for k, v in sig_svc.CLAIM_SIGNATURE_ITEMS.items()},
            "resolution": ["claim_id pin", "latest active of type on patient",
                           "item_53: provider store, then linked user"],
            "print_geometry_pt": {"item_36": [208, 14], "item_37": [208, 17], "item_53": [78, 16]},
        },
        "signature_on_file": {"signature_type": CLAIM_CONSENT_SIGNATURE_TYPE,
                              "rule": "true when the claim flag is set OR an active claim_consent signature exists"},
        "billing_npi": {"rule": "offices.npi (Type 2) when set, else the billing provider's NPI (Type 1) "
                                "with warning billing_entity_npi_missing when the office has a corporate_name"},
        "taxonomy_codes": provider_taxonomy_service.catalog(),
        "warnings": [
            "payer_missing", "subscriber_missing", "billed_slot_inactive", "other_coverage_unresolved",
            "other_plan_subscriber_unresolved", "pointer_without_diagnosis", "no_service_lines",
            "procedure_provider_mismatch", "treating_provider_unresolved", "billing_entity_npi_missing",
            "billing_npi_missing", "treating_npi_missing", "treatment_location_is_po_box",
        ],
        "error_codes": [
            "invalid_diagnosis_pointer", "invalid_quantity", "invalid_missing_tooth", "invalid_accident_type",
            "invalid_accident_state", "invalid_icd_qualifier", "invalid_icd_code", "invalid_place_of_treatment",
            "invalid_ortho_months", "invalid_other_fees", "claim_provider_mismatch", "procedure_not_found",
            "procedure_patient_mismatch", "procedure_void", "procedure_on_hold_claim", "procedure_already_claimed",
        ],
    }
