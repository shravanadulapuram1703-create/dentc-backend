"""Payment-plan business logic — Ortho + Regular contracts.

Closes the cross-cutting gaps in
``docs/payment-plans/payment_plans_backend_devreport.md``:

* **PP-2** — posting a due instalment to the patient ledger. Every instalment
  table (``patient_ins_payment_plans``, ``patient_sec_ins_payment_plans``,
  ``patient_plan_installments``) carries ``is_billed`` + ``ledger_id`` but
  nothing set them, so no contract ever actually billed. :func:`post_installment`
  writes the real ``patient_procedures`` charge and stamps both columns;
  :func:`post_due` is the nightly sweep.
* **OPP-9 / RPP-5** — the patient side of a contract now has real instalment
  rows, generated server-side by :func:`generate_schedule` so the amortisation
  the paper contract prints is the amortisation the ledger bills.
* **PP-3** — :func:`build_contract` composes the printed contract/coupon payload
  from the stored terms, and :func:`render_contract_pdf` renders it.
* **PP-7** — :class:`PaymentPlanCRUD` stamps a resolvable ``created_by_id``.

Money is ``Decimal`` end to end; the final instalment absorbs the rounding
residue so the schedule sums exactly to the total of payments.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.ids import uuid7
from app.crud.base import CRUDBase
from app.db.models import (
    Definition,
    Office,
    OrthoPlan,
    Patient,
    PatientInsPaymentPlan,
    PatientPaymentPlan,
    PatientPlanInstallment,
    PatientProcedure,
    PatientSecInsPaymentPlan,
    ProcedureCode,
    Provider,
)
from app.integrations import redis_store
from app.services.patient_overview_service import resolve_responsible_party
from app.services.user_admin_service import resolve_user_names

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")

# PP-2: the three instalment stores, keyed by the ``plan_side`` vocabulary.
_SIDE_MODELS: dict[str, type] = {
    "ins": PatientInsPaymentPlan,
    "sec_ins": PatientSecInsPaymentPlan,
    "patient": PatientPlanInstallment,
}

# Payments per year per legacy interval, used for the periodic APR rate.
_PERIODS_PER_YEAR = {
    "monthly": 12, "semi_monthly": 24, "weekly": 52,
    "bi_weekly": 26, "quarterly": 4, "annually": 1,
}
_INTERVAL_DAYS = {"semi_monthly": 15, "weekly": 7, "bi_weekly": 14}
_INTERVAL_MONTHS = {"monthly": 1, "quarterly": 3, "annually": 12}


# ── helpers ──────────────────────────────────────────────────────────────────
def _money(value: Any) -> Decimal:  # noqa: ANN401
    if value is None:
        return _ZERO
    return Decimal(str(value)).quantize(_CENTS, rounding=ROUND_HALF_UP)


def normalise_interval(value: str | None) -> str:
    """Map the legacy/FE spellings ('Semi-Monthly', 'bi weekly') onto one key."""
    key = (value or "monthly").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "semimonthly": "semi_monthly", "twice_monthly": "semi_monthly",
        "biweekly": "bi_weekly", "every_2_weeks": "bi_weekly",
        "month": "monthly", "week": "weekly", "quarter": "quarterly",
        "year": "annually", "yearly": "annually", "annual": "annually",
    }
    key = aliases.get(key, key)
    return key if key in _PERIODS_PER_YEAR else "monthly"


def _add_months(start: date, months: int) -> date:
    """Calendar-month step with end-of-month clamping (Jan 31 + 1m → Feb 28)."""
    total = start.month - 1 + months
    year = start.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _due_date(first: date, interval: str, index: int) -> date:
    """Due date of instalment ``index`` (0-based) counting from ``first``."""
    if interval in _INTERVAL_MONTHS:
        return _add_months(first, _INTERVAL_MONTHS[interval] * index)
    from datetime import timedelta

    return first + timedelta(days=_INTERVAL_DAYS[interval] * index)


def amortise(
    principal: Decimal,
    apr: Decimal,
    num_payments: int,
    interval: str,
) -> tuple[Decimal, Decimal, Decimal]:
    """Return ``(periodic_amt, finance_charge, total_of_payments)``.

    Standard level-payment amortisation: ``A = P·r / (1 − (1+r)^−n)`` with
    ``r = APR / periods-per-year``. A zero APR degrades to ``P / n``.
    """
    principal = _money(principal)
    if num_payments <= 0 or principal <= _ZERO:
        return _ZERO, _ZERO, _ZERO

    rate = Decimal(str(apr or 0)) / Decimal(100) / Decimal(_PERIODS_PER_YEAR[interval])
    if rate <= _ZERO:
        periodic = _money(principal / Decimal(num_payments))
    else:
        factor = (Decimal(1) + rate) ** -num_payments
        periodic = _money(principal * rate / (Decimal(1) - factor))

    total = _money(periodic * Decimal(num_payments))
    return periodic, _money(total - principal), total


def build_schedule_rows(
    principal: Decimal,
    apr: Decimal,
    num_payments: int,
    interval: str,
    first_due: date | None,
    billing_code: str | None = None,
) -> tuple[list[dict], dict]:
    """Amortise into per-instalment rows plus the Truth-in-Lending terms box.

    The last instalment absorbs the rounding residue, so the rows always sum to
    ``total_of_payments`` exactly (the client-side projection could drift by a
    cent per instalment).
    """
    interval = normalise_interval(interval)
    periodic, finance_charge, total = amortise(principal, apr, num_payments, interval)

    rows: list[dict] = []
    remaining = total
    for i in range(max(num_payments, 0)):
        is_last = i == num_payments - 1
        amount = _money(remaining) if is_last else periodic
        remaining = _money(remaining - amount)
        rows.append({
            "periodic_order": i + 1,
            "periodic_date": _due_date(first_due, interval, i) if first_due else None,
            "periodic_amt": amount,
            "rem_payments": num_payments - i - 1,
            "rem_total_amt": remaining,
            "billing_code": billing_code,
            "is_billed": False,
            "ledger_id": None,
            "installment_id": None,
        })

    terms = {
        "amount_financed": _money(principal),
        "down_payment": _ZERO,
        "apr": Decimal(str(apr or 0)),
        "finance_charge": finance_charge,
        "total_of_payments": total,
        "periodic_amt": periodic,
        "num_payments": max(num_payments, 0),
        "interval_type": interval,
        "first_due_date": first_due,
        "final_due_date": rows[-1]["periodic_date"] if rows else None,
    }
    return rows, terms


# ── PP-7: resolvable actor on contract writes ────────────────────────────────
class PaymentPlanCRUD(CRUDBase):
    """``created_by`` on both contract tables is legacy free text, so ``CRUDBase``
    refuses to stamp it. Stamp the integer ``created_by_id`` FK instead (PP-7 /
    OPP-11); ``updated_by`` is already handled by ``CRUDBase.update``."""

    def create(self, db, data, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        if created_by is not None and hasattr(self.model, "created_by_id"):
            payload.setdefault("created_by_id", created_by)
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)


# ── lookups ──────────────────────────────────────────────────────────────────
def _get_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def get_plan(db: Session, plan_kind: str, plan_id: int, tenant_id: int):  # noqa: ANN201
    model = OrthoPlan if plan_kind == "ortho" else PatientPaymentPlan
    plan = db.execute(
        select(model).where(model.id == plan_id, model.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if plan is None:
        label = "OrthoPlan" if plan_kind == "ortho" else "PatientPaymentPlan"
        raise NotFoundError(f"{label} '{plan_id}' was not found")
    return plan


def _parent_plan(db: Session, row, tenant_id: int):  # noqa: ANN001, ANN201
    """The contract an instalment belongs to (may be None for migrated rows)."""
    ortho_id = getattr(row, "ortho_plan_id", None)
    if ortho_id is not None:
        return db.execute(
            select(OrthoPlan).where(OrthoPlan.id == ortho_id, OrthoPlan.tenant_id == tenant_id)
        ).scalar_one_or_none()
    plan_id = getattr(row, "payment_plan_id", None)
    if plan_id is not None:
        return db.execute(
            select(PatientPaymentPlan).where(
                PatientPaymentPlan.id == plan_id, PatientPaymentPlan.tenant_id == tenant_id
            )
        ).scalar_one_or_none()
    return None


def _plan_billing_code(plan) -> str | None:  # noqa: ANN001
    if plan is None:
        return None
    # ortho_plans.procedure_code is the *periodic* code (OPP-1).
    return getattr(plan, "billing_code", None) or getattr(plan, "procedure_code", None)


# ── PP-2: post one instalment to the ledger ──────────────────────────────────
def post_installment(
    db: Session,
    side: str,
    installment_id: int,
    tenant_id: int,
    *,
    actor_id: int | None = None,
    override: dict | None = None,
) -> dict:
    """Post a due instalment as a real ledger charge and mark it billed.

    Idempotent by refusal: an already-posted instalment raises ``ConflictError``
    carrying the existing ``ledger_id`` rather than double-charging the patient.
    """
    model = _SIDE_MODELS[side]
    row = db.execute(
        select(model).where(model.id == installment_id, model.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Installment '{installment_id}' was not found")
    if row.is_billed:
        raise ConflictError(
            f"Installment '{installment_id}' has already been posted",
            details={"ledger_id": row.ledger_id},
        )

    proc = _post_row(db, row, side, tenant_id, actor_id=actor_id, override=override or {})
    db.commit()
    db.refresh(row)
    _invalidate_balance(tenant_id, row.patient_id)
    return _posted_payload(row, side, proc)


def _post_row(
    db: Session,
    row,  # noqa: ANN001
    side: str,
    tenant_id: int,
    *,
    actor_id: int | None,
    override: dict,
) -> PatientProcedure:
    """Validate + stage (no commit) the ledger charge for one instalment."""
    patient = _get_patient(db, row.patient_id, tenant_id)
    plan = _parent_plan(db, row, tenant_id)

    code = override.get("procedure_code") or row.billing_code or _plan_billing_code(plan)
    if not code:
        raise ValidationError(
            "No billing code to post: set the instalment's billing_code or the contract's "
            "periodic billing code, or pass procedure_code."
        )
    if db.get(ProcedureCode, code) is None:
        raise ValidationError(f"Procedure code '{code}' does not exist")

    fee = _money(override.get("fee") if override.get("fee") is not None else row.periodic_amt)
    if fee <= _ZERO:
        raise ValidationError("Instalment amount must be greater than zero to post")

    provider_id = (
        override.get("provider_id")
        or getattr(plan, "pref_provider_id", None)
        or patient.preferred_provider_id
    )
    if not provider_id:
        raise ValidationError(
            "No provider to post under: set the contract's pref_provider_id or the "
            "patient's preferred provider, or pass provider_id."
        )
    if db.get(Provider, provider_id) is None:
        raise ValidationError(f"Provider '{provider_id}' does not exist")

    office_id = (
        override.get("office_id")
        or getattr(plan, "office_id", None)
        or patient.home_office_id
    )
    if not office_id:
        raise ValidationError(
            "No office to post to: set the contract's office_id or the patient's "
            "home office, or pass office_id."
        )

    post_date = (
        override.get("post_date")
        or row.periodic_date
        or datetime.now(timezone.utc).date()
    )

    label = {
        "ins": "primary insurance", "sec_ins": "secondary insurance", "patient": "patient",
    }[side]
    proc = PatientProcedure(
        id=f"PP-{uuid7()}",
        patient_id=row.patient_id,
        procedure_code=code,
        date_of_service=post_date,
        provider_id=provider_id,
        office_id=office_id,
        fee=fee,
        # The instalment is owed by whichever column of the contract it sits in.
        insurance_estimate=fee if side in ("ins", "sec_ins") else _ZERO,
        patient_estimate=_ZERO if side in ("ins", "sec_ins") else fee,
        notes=override.get("notes")
        or f"Periodic contract billing ({label}) — instalment {row.periodic_order or ''}".strip(),
        created_by=actor_id,
    )
    db.add(proc)
    db.flush()

    row.is_billed = True
    row.ledger_id = proc.id
    return proc


def _posted_payload(row, side: str, proc: PatientProcedure) -> dict:  # noqa: ANN001
    return {
        "installment_id": row.id,
        "source": side,
        "patient_id": row.patient_id,
        "periodic_order": row.periodic_order,
        "periodic_date": row.periodic_date,
        "ledger_id": proc.id,
        "procedure_code": proc.procedure_code,
        "amount": _money(proc.fee),
        "post_date": proc.date_of_service,
        "provider_id": proc.provider_id,
        "office_id": proc.office_id,
    }


def _invalidate_balance(tenant_id: int, patient_id: int) -> None:
    """The cached aggregate must not survive a charge we just posted."""
    redis_store.cache_delete(f"balance:{tenant_id}:{patient_id}")


def post_due(
    db: Session,
    tenant_id: int,
    *,
    actor_id: int | None = None,
    patient_id: int | None = None,
    ortho_plan_id: int | None = None,
    payment_plan_id: int | None = None,
    through_date: date | None = None,
    sides: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """PP-2 batch sweep: post every unbilled instalment due on/before a date.

    One instalment failing (missing provider, unknown code, …) never aborts the
    run — it lands in ``skipped`` with the reason and the sweep continues.
    """
    through = through_date or datetime.now(timezone.utc).date()
    wanted = sides or list(_SIDE_MODELS)

    posted: list[dict] = []
    skipped: list[dict] = []
    touched: set[int] = set()
    total = _ZERO

    for side in wanted:
        model = _SIDE_MODELS[side]
        stmt = select(model).where(
            model.tenant_id == tenant_id,
            model.is_billed.is_(False),
            model.periodic_date.is_not(None),
            model.periodic_date <= through,
        )
        if patient_id is not None:
            stmt = stmt.where(model.patient_id == patient_id)
        if ortho_plan_id is not None:
            stmt = stmt.where(model.ortho_plan_id == ortho_plan_id)
        if payment_plan_id is not None:
            if not hasattr(model, "payment_plan_id"):
                continue
            stmt = stmt.where(model.payment_plan_id == payment_plan_id)
        stmt = stmt.order_by(model.periodic_date.asc(), model.id.asc())

        for row in db.execute(stmt).scalars().all():
            try:
                proc = _post_row(db, row, side, tenant_id, actor_id=actor_id, override={})
            except (ValidationError, NotFoundError, ConflictError) as exc:
                db.rollback()
                skipped.append({"installment_id": row.id, "source": side, "reason": str(exc)})
                continue
            payload = _posted_payload(row, side, proc)
            if dry_run:
                db.rollback()
                payload["ledger_id"] = "(dry-run)"
            else:
                db.commit()
                touched.add(row.patient_id)
            posted.append(payload)
            total += payload["amount"]

    for pid in touched:
        _invalidate_balance(tenant_id, pid)

    return {
        "posted": posted,
        "skipped": skipped,
        "total_posted_amount": _money(total),
        "through_date": through,
        "dry_run": dry_run,
    }


# ── OPP-9 / RPP-5: the patient-side instalment schedule ──────────────────────
def _plan_terms(plan, plan_kind: str) -> dict:  # noqa: ANN001
    """The patient-side contract terms, whichever table the contract lives in."""
    if plan_kind == "ortho":
        return {
            "amount_financed": plan.pat_amt_financed,
            "down_payment": plan.pat_down_pay,
            "apr": plan.pat_apr,
            "num_payments": plan.pat_num_payments,
            "first_due_date": plan.pat_first_due_date,
            "interval_type": plan.pat_interval,
            "billing_code": plan.procedure_code,
        }
    return {
        "amount_financed": plan.amt_financed,
        "down_payment": plan.down_payment,
        "apr": plan.apr,
        "num_payments": plan.num_payments,
        "first_due_date": plan.first_due_date,
        "interval_type": plan.interval_type,
        "billing_code": plan.billing_code,
    }


def _plan_filter(plan_kind: str, plan_id: int):  # noqa: ANN201
    column = (
        PatientPlanInstallment.ortho_plan_id
        if plan_kind == "ortho"
        else PatientPlanInstallment.payment_plan_id
    )
    return column == plan_id


def list_installments(db: Session, plan_kind: str, plan_id: int, tenant_id: int) -> list:
    return list(db.execute(
        select(PatientPlanInstallment)
        .where(
            PatientPlanInstallment.tenant_id == tenant_id,
            PatientPlanInstallment.plan_side == "patient",
            _plan_filter(plan_kind, plan_id),
        )
        .order_by(
            PatientPlanInstallment.periodic_order.asc(),
            PatientPlanInstallment.id.asc(),
        )
    ).scalars().all())


def _row_out(row: PatientPlanInstallment) -> dict:
    return {
        "installment_id": row.id,
        "periodic_order": row.periodic_order or 0,
        "periodic_date": row.periodic_date,
        "periodic_amt": _money(row.periodic_amt),
        "rem_payments": row.rem_payments or 0,
        "rem_total_amt": _money(row.rem_total_amt),
        "is_billed": bool(row.is_billed),
        "ledger_id": row.ledger_id,
        "billing_code": row.billing_code,
    }


def _replace_rows(
    db: Session,
    plan,  # noqa: ANN001
    plan_kind: str,
    tenant_id: int,
    rows: list[dict],
    *,
    actor_id: int | None,
) -> list[PatientPlanInstallment]:
    """Replace the *unbilled* schedule. Posted instalments are never destroyed —
    they are ledger history — so they survive a re-amortisation untouched."""
    existing = list_installments(db, plan_kind, plan.id, tenant_id)
    billed = [r for r in existing if r.is_billed]
    for row in existing:
        if not row.is_billed:
            db.delete(row)

    billed_orders = {r.periodic_order for r in billed}
    created: list[PatientPlanInstallment] = []
    for data in rows:
        if data.get("periodic_order") in billed_orders:
            continue  # already posted — keep the ledger row's own figures
        created.append(PatientPlanInstallment(
            tenant_id=tenant_id,
            patient_id=plan.patient_id,
            plan_side="patient",
            ortho_plan_id=plan.id if plan_kind == "ortho" else None,
            payment_plan_id=plan.id if plan_kind == "regular" else None,
            periodic_order=data.get("periodic_order"),
            periodic_date=data.get("periodic_date"),
            periodic_amt=data.get("periodic_amt"),
            plan_amount=data.get("plan_amount"),
            down_payment=data.get("down_payment"),
            rem_total_amt=data.get("rem_total_amt"),
            rem_payments=data.get("rem_payments"),
            billing_code=data.get("billing_code"),
            created_by=actor_id,
        ))
    db.add_all(created)
    db.commit()
    return billed + created


def replace_installments(
    db: Session,
    plan_kind: str,
    plan_id: int,
    tenant_id: int,
    rows: list[dict],
    *,
    actor_id: int | None = None,
) -> dict:
    plan = get_plan(db, plan_kind, plan_id, tenant_id)
    _replace_rows(db, plan, plan_kind, tenant_id, rows, actor_id=actor_id)
    return schedule_response(db, plan, plan_kind, tenant_id, persisted=True)


def generate_schedule(
    db: Session,
    plan_kind: str,
    plan_id: int,
    tenant_id: int,
    payload: dict,
    *,
    actor_id: int | None = None,
) -> dict:
    """Amortise the contract's own terms into instalments (persisting by default)."""
    plan = get_plan(db, plan_kind, plan_id, tenant_id)
    terms = _plan_terms(plan, plan_kind)
    for key in ("amount_financed", "down_payment", "apr", "num_payments",
                "first_due_date", "interval_type", "billing_code"):
        if payload.get(key) is not None:
            terms[key] = payload[key]

    num_payments = int(terms["num_payments"] or 0)
    if num_payments <= 0:
        raise ValidationError(
            "Cannot generate a schedule: the contract has no number of payments. "
            "Set num_payments on the plan or pass it in the request."
        )
    principal = _money(terms["amount_financed"])
    if principal <= _ZERO:
        raise ValidationError(
            "Cannot generate a schedule: the contract has no amount financed."
        )

    rows, computed = build_schedule_rows(
        principal,
        Decimal(str(terms["apr"] or 0)),
        num_payments,
        terms["interval_type"],
        terms["first_due_date"],
        terms["billing_code"],
    )
    computed["down_payment"] = _money(terms["down_payment"])
    for row in rows:
        row["plan_amount"] = principal
        row["down_payment"] = computed["down_payment"]

    persist = payload.get("persist", True)
    if not persist:
        return {
            "plan_kind": plan_kind, "plan_id": plan.id, "patient_id": plan.patient_id,
            "plan_side": "patient", "terms": computed, "rows": rows, "persisted": False,
        }

    _replace_rows(db, plan, plan_kind, tenant_id, rows, actor_id=actor_id)
    return schedule_response(db, plan, plan_kind, tenant_id, persisted=True, terms=computed)


def schedule_response(
    db: Session,
    plan,  # noqa: ANN001
    plan_kind: str,
    tenant_id: int,
    *,
    persisted: bool = False,
    terms: dict | None = None,
) -> dict:
    stored = list_installments(db, plan_kind, plan.id, tenant_id)
    if terms is None:
        terms = _terms_from_plan(plan, plan_kind, stored)
    return {
        "plan_kind": plan_kind,
        "plan_id": plan.id,
        "patient_id": plan.patient_id,
        "plan_side": "patient",
        "terms": terms,
        "rows": [_row_out(r) for r in stored],
        "persisted": persisted,
    }


def _terms_from_plan(plan, plan_kind: str, stored: list) -> dict:  # noqa: ANN001
    """Terms as *stored* on the contract, with the derived figures filled in."""
    raw = _plan_terms(plan, plan_kind)
    interval = normalise_interval(raw["interval_type"])
    num_payments = int(raw["num_payments"] or 0)
    principal = _money(raw["amount_financed"])

    if stored:
        total = _money(sum(_money(r.periodic_amt) for r in stored))
        periodic = _money(stored[0].periodic_amt)
        count = len(stored)
        final = stored[-1].periodic_date
    else:
        periodic, _, total = amortise(
            principal, Decimal(str(raw["apr"] or 0)), num_payments, interval
        )
        count = num_payments
        final = _due_date(raw["first_due_date"], interval, num_payments - 1) if (
            raw["first_due_date"] and num_payments > 0
        ) else None

    # RPP-6 / plan-level overrides win when the contract persisted them.
    stored_total = getattr(plan, "total_of_payments", None)
    if stored_total is not None:
        total = _money(stored_total)
    finance_charge = (
        getattr(plan, "pat_fin_charge", None) if plan_kind == "ortho" else plan.fin_charge
    )

    return {
        "amount_financed": principal,
        "down_payment": _money(raw["down_payment"]),
        "apr": Decimal(str(raw["apr"] or 0)),
        "finance_charge": (
            _money(finance_charge) if finance_charge is not None else _money(total - principal)
        ),
        "total_of_payments": total,
        "periodic_amt": periodic,
        "num_payments": count,
        "interval_type": interval,
        "first_due_date": raw["first_due_date"],
        "final_due_date": final,
    }


# ── PP-3: server-rendered contract / coupons ─────────────────────────────────
def _disclosure_text(db: Session, tenant_id: int, key: str | None) -> str | None:
    if not key:
        return None
    row = db.execute(
        select(Definition).where(
            Definition.tenant_id == tenant_id,
            Definition.group_code == "financial_disclosure",
            Definition.key1 == key,
        )
    ).scalar_one_or_none()
    return row.description if row else None


def _patient_label(patient: Patient) -> str:
    name = ", ".join(x for x in (patient.last_name, patient.first_name) if x)
    return name or patient.chart_no or f"Patient {patient.id}"


def build_contract(db: Session, plan_kind: str, plan_id: int, tenant_id: int) -> dict:
    """PP-3: everything the printed contract shows, computed server-side."""
    plan = get_plan(db, plan_kind, plan_id, tenant_id)
    patient = _get_patient(db, plan.patient_id, tenant_id)
    terms = _terms_from_plan(plan, plan_kind, list_installments(db, plan_kind, plan.id, tenant_id))
    rows = [_row_out(r) for r in list_installments(db, plan_kind, plan.id, tenant_id)]
    if not rows and terms["num_payments"]:
        rows, _ = build_schedule_rows(
            terms["amount_financed"], terms["apr"], terms["num_payments"],
            terms["interval_type"], terms["first_due_date"],
            _plan_terms(plan, plan_kind)["billing_code"],
        )

    office_id = getattr(plan, "created_office_id", None) or plan.office_id or patient.home_office_id
    office = db.get(Office, office_id) if office_id else None
    provider_id = getattr(plan, "pref_provider_id", None) or patient.preferred_provider_id
    provider = db.get(Provider, provider_id) if provider_id else None

    rp = resolve_responsible_party(db, tenant_id, patient.responsible_party_id)
    rp_name = ", ".join(x for x in (rp.last_name, rp.first_name) if x) or None if rp else None

    actor_names = resolve_user_names(
        db, {plan.created_by_id} if plan.created_by_id is not None else set()
    )
    address = ", ".join(
        x for x in (patient.address_line1, patient.city, patient.state, patient.zip) if x
    ) or None

    return {
        "plan_kind": plan_kind,
        "plan_id": plan.id,
        "party": {
            "patient_id": patient.id,
            "patient_name": _patient_label(patient),
            "chart_no": patient.chart_no,
            "address": address,
            "phone": patient.phone or patient.cell_phone,
            "responsible_party_name": rp_name,
        },
        "office_name": office.name if office else None,
        "provider_name": provider.name if provider else None,
        "setup_date": (
            (plan.pat_setup_date or plan.treat_start_date)
            if plan_kind == "ortho"
            else plan.setup_date
        ),
        "billing_code": _plan_terms(plan, plan_kind)["billing_code"],
        "initial_billing_code": getattr(plan, "initial_procedure_code", None),
        "financial_disclosure": plan.financial_disclosure,
        "disclosure_text": _disclosure_text(db, tenant_id, plan.financial_disclosure),
        "terms": terms,
        "rows": rows,
        "notes": (plan.pat_notes or plan.remarks) if plan_kind == "ortho" else plan.notes,
        "created_by_name": actor_names.get(plan.created_by_id) or plan.created_by,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _pdf_canvas():  # noqa: ANN202
    """Import reportlab lazily so the rest of the module works without it."""
    try:
        from reportlab.lib.pagesizes import LETTER  # noqa: PLC0415
        from reportlab.pdfgen import canvas  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover — depends on the deployment
        raise ValidationError(
            "PDF rendering requires the 'reportlab' package (pip install -r requirements.txt). "
            "Use the JSON contract endpoint if PDF output is not needed."
        ) from exc
    return canvas, LETTER


def _fmt(value: Decimal | None) -> str:
    return f"${_money(value):,.2f}"


def render_contract_pdf(contract: dict) -> bytes:
    """PP-3: the Truth-in-Lending style contract, rendered on the server so the
    paper output is identical across clients and archivable."""
    import io

    canvas, LETTER = _pdf_canvas()
    buf = io.BytesIO()
    width, height = LETTER
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    pdf.setTitle(f"Payment contract {contract['plan_id']}")

    terms = contract["terms"]
    party = contract["party"]
    y = height - 60

    pdf.setFont("Helvetica-Bold", 15)
    kind = "Orthodontic" if contract["plan_kind"] == "ortho" else "Regular"
    pdf.drawString(54, y, f"{kind} Payment Contract")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(width - 54, y, contract.get("office_name") or "")
    y -= 24

    pdf.setFont("Helvetica", 10)
    for label, value in (
        ("Patient", f"{party['patient_name']}  (chart {party.get('chart_no') or '—'})"),
        ("Address", party.get("address") or "—"),
        ("Responsible party", party.get("responsible_party_name") or "—"),
        ("Provider", contract.get("provider_name") or "—"),
        ("Setup date", str(contract.get("setup_date") or "—")),
        ("Billing code", contract.get("billing_code") or "—"),
    ):
        pdf.drawString(54, y, f"{label}:")
        pdf.drawString(170, y, str(value))
        y -= 14

    # Truth-in-Lending style disclosure box.
    y -= 12
    box_top, box_h = y, 58
    pdf.rect(54, box_top - box_h, width - 108, box_h)
    cols = [
        ("ANNUAL PERCENTAGE RATE", f"{Decimal(str(terms['apr'] or 0)):.3f}%"),
        ("FINANCE CHARGE", _fmt(terms["finance_charge"])),
        ("Amount Financed", _fmt(terms["amount_financed"])),
        ("Total of Payments", _fmt(terms["total_of_payments"])),
    ]
    col_w = (width - 108) / len(cols)
    for i, (head, value) in enumerate(cols):
        x = 54 + i * col_w + 6
        pdf.setFont("Helvetica-Bold", 7)
        pdf.drawString(x, box_top - 16, head)
        pdf.setFont("Helvetica", 12)
        pdf.drawString(x, box_top - 38, value)
    y = box_top - box_h - 22

    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        54, y,
        f"{terms['num_payments']} {terms['interval_type'].replace('_', '-')} payments of "
        f"{_fmt(terms['periodic_amt'])}, first due {terms['first_due_date'] or '—'}"
        f" · down payment {_fmt(terms['down_payment'])}",
    )
    y -= 22

    if contract.get("disclosure_text"):
        pdf.setFont("Helvetica-Oblique", 8)
        for line in _wrap(contract["disclosure_text"], 110):
            pdf.drawString(54, y, line)
            y -= 10
        y -= 8

    # Payment schedule.
    pdf.setFont("Helvetica-Bold", 9)
    for label, x in (("#", 54), ("Due date", 90), ("Amount", 180), ("Remaining", 260),
                     ("Payments left", 350), ("Status", 450)):
        pdf.drawString(x, y, label)
    y -= 12
    pdf.setFont("Helvetica", 9)
    for row in contract["rows"]:
        if y < 90:
            pdf.showPage()
            y = height - 60
            pdf.setFont("Helvetica", 9)
        pdf.drawString(54, y, str(row["periodic_order"]))
        pdf.drawString(90, y, str(row.get("periodic_date") or "—"))
        pdf.drawString(180, y, _fmt(row["periodic_amt"]))
        pdf.drawString(260, y, _fmt(row["rem_total_amt"]))
        pdf.drawString(350, y, str(row["rem_payments"]))
        pdf.drawString(450, y, "POSTED" if row["is_billed"] else "due")
        y -= 12

    y -= 30
    if y < 90:
        pdf.showPage()
        y = height - 90
    pdf.setFont("Helvetica", 9)
    pdf.line(54, y, 280, y)
    pdf.drawString(54, y - 12, "Responsible party signature")
    pdf.line(320, y, 540, y)
    pdf.drawString(320, y - 12, "Date")
    pdf.setFont("Helvetica-Oblique", 7)
    pdf.drawString(54, 48, f"Generated {contract['generated_at']} · plan {contract['plan_id']}")

    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def render_coupons_pdf(contract: dict) -> bytes:
    """PP-3: the tear-off coupon strip, one coupon per unposted instalment."""
    import io

    canvas, LETTER = _pdf_canvas()
    buf = io.BytesIO()
    width, height = LETTER
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    pdf.setTitle(f"Payment coupons {contract['plan_id']}")

    party = contract["party"]
    per_page, coupon_h = 5, 130
    for index, row in enumerate(contract["rows"]):
        slot = index % per_page
        if slot == 0 and index:
            pdf.showPage()
        top = height - 50 - slot * coupon_h
        pdf.setDash(2, 3)
        pdf.line(40, top + 8, width - 40, top + 8)
        pdf.setDash()

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(
            54, top - 16,
            f"Payment coupon {row['periodic_order']} of {len(contract['rows'])}",
        )
        pdf.setFont("Helvetica", 9)
        pdf.drawString(
            54, top - 32,
            f"{party['patient_name']} · chart {party.get('chart_no') or '—'}",
        )
        pdf.drawString(54, top - 46, f"Account / plan: {contract['plan_id']}")
        pdf.drawString(54, top - 60, contract.get("office_name") or "")

        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawRightString(width - 54, top - 16, f"Due {row.get('periodic_date') or '—'}")
        pdf.setFont("Helvetica", 14)
        pdf.drawRightString(width - 54, top - 40, _fmt(row["periodic_amt"]))
        pdf.setFont("Helvetica", 8)
        pdf.drawRightString(
            width - 54, top - 58,
            "PAID — posted to ledger" if row["is_billed"]
            else f"Balance after: {_fmt(row['rem_total_amt'])}",
        )
        pdf.rect(54, top - 108, width - 108, 34)
        pdf.drawString(60, top - 90, "Amount enclosed: ______________    Check #: ______________")

    if not contract["rows"]:
        pdf.setFont("Helvetica", 11)
        pdf.drawString(54, height - 80, "This contract has no instalment schedule yet.")

    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def _wrap(text: str, width: int) -> list[str]:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
