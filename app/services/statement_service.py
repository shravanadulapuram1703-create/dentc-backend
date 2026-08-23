"""Patient statement generation & delivery (STMT-1..3).

The "BALANCE STATEMENT" button and the monthly batch had no backend:

* **STMT-1** ``generate_statement`` freezes a single-patient account snapshot
  (opening/charges/payments/adjustments/closing + aging + the office aging
  message) into a ``patient_statements`` row.
* **STMT-2** ``generate_batch`` runs it for every office patient with an
  outstanding (optionally aged) balance under one ``batch_id``.
* **STMT-3** ``render_pdf`` renders the frozen snapshot to a PDF and ``deliver``
  records the print/email/download lifecycle.

The figures come from the same ``balance_service`` the FE already trusts, so the
statement agrees with the on-screen balance. reportlab is imported lazily.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.ledger_sign import sum_payment_credit, sum_payment_debit

from app.core.exceptions import NotFoundError, ValidationError
from app.core.ids import uuid7
from app.db.models import (
    Office,
    OfficeStatementSettings,
    Patient,
    PatientAdjustment,
    PatientPayment,
    PatientProcedure,
    PatientStatement,
)
from app.services import balance_service

_ZERO = Decimal("0")


def _d(value) -> Decimal:  # noqa: ANN001
    return Decimal(value or 0)


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _get_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def _aging_message(db: Session, office_id: int | None, aging: dict) -> str | None:
    """The office's configured statement message for the oldest non-zero bucket."""
    if office_id is None:
        return None
    settings = db.execute(
        select(OfficeStatementSettings).where(OfficeStatementSettings.office_id == office_id)
    ).scalar_one_or_none()
    if settings is None:
        return None
    for bucket, attr in (("b120", "message_120"), ("b90", "message_90"), ("b60", "message_60"),
                         ("b30", "message_30"), ("current", "message_current")):
        if _d(aging.get(bucket)) > _ZERO and getattr(settings, attr, None):
            return getattr(settings, attr)
    return settings.message_general


def _period_lines(
    db: Session, patient_id: int, date_from: date | None, date_to: date | None
) -> dict:
    """Charges/payments/adjustments within the window + an opening balance."""
    def _window(stmt, col):  # noqa: ANN001, ANN202
        if date_from is not None:
            stmt = stmt.where(col >= date_from)
        if date_to is not None:
            stmt = stmt.where(col <= date_to)
        return stmt

    charges = db.execute(_window(
        select(func.coalesce(func.sum(PatientProcedure.fee), 0)).where(
            PatientProcedure.patient_id == patient_id,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        ), PatientProcedure.date_of_service)).scalar_one()
    # AL-9: credits are always positive; a debit adjustment posted through
    # patient_payments is a charge and is added to the charge side.
    payments = db.execute(_window(
        select(sum_payment_credit()).where(
            PatientPayment.patient_id == patient_id, PatientPayment.is_void.is_(False),
        ), PatientPayment.payment_date)).scalar_one()
    payment_debits = db.execute(_window(
        select(sum_payment_debit()).where(
            PatientPayment.patient_id == patient_id, PatientPayment.is_void.is_(False),
        ), PatientPayment.payment_date)).scalar_one()
    adjustments = db.execute(_window(
        select(func.coalesce(func.sum(PatientAdjustment.amount), 0)).where(
            PatientAdjustment.patient_id == patient_id, PatientAdjustment.is_void.is_(False),
        ), PatientAdjustment.adjustment_date)).scalar_one()

    # Opening balance = everything strictly before date_from.
    opening = _ZERO
    if date_from is not None:
        pre_charge = db.execute(
            select(func.coalesce(func.sum(PatientProcedure.fee), 0)).where(
                PatientProcedure.patient_id == patient_id,
                PatientProcedure.is_void.is_(False),
                PatientProcedure.is_archived.is_(False),
                PatientProcedure.date_of_service < date_from,
            )).scalar_one()
        pre_pay = db.execute(
            select(sum_payment_credit() - sum_payment_debit()).where(  # AL-9
                PatientPayment.patient_id == patient_id, PatientPayment.is_void.is_(False),
                PatientPayment.payment_date < date_from,
            )).scalar_one()
        pre_adj = db.execute(
            select(func.coalesce(func.sum(PatientAdjustment.amount), 0)).where(
                PatientAdjustment.patient_id == patient_id, PatientAdjustment.is_void.is_(False),
                PatientAdjustment.adjustment_date < date_from,
            )).scalar_one()
        opening = _d(pre_charge) - _d(pre_pay) - _d(pre_adj)

    return {
        "opening": opening,
        # AL-9: a debit adjustment posted through patient_payments is a charge.
        "charges": _d(charges) + _d(payment_debits),
        "payments": _d(payments),
        "adjustments": _d(adjustments),
    }


def _statement_out(row: PatientStatement) -> dict:
    return {
        "id": row.id, "patient_id": row.patient_id, "office_id": row.office_id,
        "statement_date": row.statement_date, "period_start": row.period_start,
        "period_end": row.period_end, "opening_balance": row.opening_balance,
        "total_charges": row.total_charges, "total_payments": row.total_payments,
        "total_adjustments": row.total_adjustments, "closing_balance": row.closing_balance,
        "aging_current": row.aging_current, "aging_30": row.aging_30, "aging_60": row.aging_60,
        "aging_90": row.aging_90, "aging_120": row.aging_120, "message": row.message,
        "batch_id": row.batch_id, "delivery_method": row.delivery_method,
        "delivery_status": row.delivery_status, "delivered_to": row.delivered_to,
        "delivered_at": row.delivered_at,
    }


# ── STMT-1: single-patient generation ─────────────────────────────────────────
def generate_statement(
    db: Session, patient_id: int, tenant_id: int, payload: dict, *,
    actor_id: int | None = None, batch_id: str | None = None, commit: bool = True,
) -> PatientStatement:
    patient = _get_patient(db, patient_id, tenant_id)
    office_id = payload.get("office_id") or patient.home_office_id
    date_from = payload.get("date_from")
    date_to = payload.get("date_to")

    lines = _period_lines(db, patient_id, date_from, date_to)
    balance = balance_service.get_patient_balance(db, patient_id, tenant_id)
    aging = balance["aging"]
    closing = _d(lines["opening"]) + _d(lines["charges"]) - _d(lines["payments"]) - _d(lines["adjustments"])
    message = payload.get("message") or _aging_message(db, office_id, aging)

    stmt = PatientStatement(
        tenant_id=tenant_id, patient_id=patient_id, office_id=office_id,
        statement_date=payload.get("statement_date") or _today(),
        period_start=date_from, period_end=date_to,
        opening_balance=lines["opening"], total_charges=lines["charges"],
        total_payments=lines["payments"], total_adjustments=lines["adjustments"],
        closing_balance=closing,
        aging_current=_d(aging.get("current")), aging_30=_d(aging.get("b30")),
        aging_60=_d(aging.get("b60")), aging_90=_d(aging.get("b90")),
        aging_120=_d(aging.get("b120")),
        message=message, batch_id=batch_id,
        snapshot={
            "patient_name": ", ".join(x for x in (patient.last_name, patient.first_name) if x),
            "chart_no": patient.chart_no,
            "account_balance": balance["account_balance"],
        },
        created_by=actor_id,
    )
    db.add(stmt)
    if commit:
        db.commit()
        db.refresh(stmt)
    else:
        db.flush()
    return stmt


# ── STMT-2: batch over an office's outstanding balances ──────────────────────
def generate_batch(
    db: Session, office_id: int, tenant_id: int, payload: dict, *, actor_id: int | None = None,
) -> dict:
    office = db.get(Office, office_id)
    if office is None or office.tenant_id != tenant_id:
        raise NotFoundError(f"Office '{office_id}' was not found")

    min_balance = _d(payload.get("min_balance") or "0.01")
    only_aged = bool(payload.get("only_aged"))
    batch_id = f"STMT-{uuid7()}"

    patients = db.execute(
        select(Patient.id).where(
            Patient.tenant_id == tenant_id,
            Patient.home_office_id == office_id,
            Patient.is_active.is_(True),
        )
    ).scalars().all()

    generated: list[dict] = []
    for pid in patients:
        balance = balance_service.get_patient_balance(db, pid, tenant_id)
        if _d(balance["account_balance"]) < min_balance:
            continue
        if only_aged:
            aging = balance["aging"]
            aged = sum(_d(aging.get(b)) for b in ("b30", "b60", "b90", "b120"))
            if aged <= _ZERO:
                continue
        stmt = generate_statement(
            db, pid, tenant_id,
            {"office_id": office_id, "statement_date": payload.get("statement_date"),
             "date_from": payload.get("date_from"), "date_to": payload.get("date_to")},
            actor_id=actor_id, batch_id=batch_id, commit=False,
        )
        db.flush()
        generated.append(_statement_out(stmt))

    db.commit()
    return {
        "office_id": office_id, "batch_id": batch_id,
        "generated": len(generated), "statements": generated,
    }


# ── listing / fetch ───────────────────────────────────────────────────────────
def get_statement(db: Session, patient_id: int, statement_id: int, tenant_id: int) -> PatientStatement:
    stmt = db.execute(
        select(PatientStatement).where(
            PatientStatement.id == statement_id,
            PatientStatement.patient_id == patient_id,
            PatientStatement.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if stmt is None:
        raise NotFoundError(f"Statement '{statement_id}' was not found")
    return stmt


def list_statements(
    db: Session, patient_id: int, tenant_id: int, *, page: int = 1, size: int = 50,
) -> tuple[list[dict], int]:
    _get_patient(db, patient_id, tenant_id)
    base = select(PatientStatement).where(
        PatientStatement.patient_id == patient_id, PatientStatement.tenant_id == tenant_id
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(PatientStatement.statement_date.desc(), PatientStatement.id.desc())
        .offset((page - 1) * size).limit(size)
    ).scalars().all()
    return [_statement_out(r) for r in rows], total


# ── STMT-3: delivery ──────────────────────────────────────────────────────────
def deliver(
    db: Session, patient_id: int, statement_id: int, tenant_id: int, payload: dict,
) -> dict:
    stmt = get_statement(db, patient_id, statement_id, tenant_id)
    method = payload.get("method", "email")
    if method == "email":
        patient = _get_patient(db, patient_id, tenant_id)
        target = payload.get("email") or patient.email
        if not target:
            raise ValidationError("No email address on file for this patient")
        # No SMTP integration is wired; record intent for a downstream mailer/worker.
        stmt.delivery_status = "emailed"
        stmt.delivered_to = target
    elif method == "print":
        stmt.delivery_status = "printed"
    else:  # download
        stmt.delivery_status = "downloaded"
    stmt.delivery_method = method
    stmt.delivered_at = _today()
    db.commit()
    db.refresh(stmt)
    return _statement_out(stmt)


# ── STMT-3: PDF rendering ─────────────────────────────────────────────────────
def _pdf_canvas():  # noqa: ANN202
    try:
        from reportlab.lib.pagesizes import LETTER  # noqa: PLC0415
        from reportlab.pdfgen import canvas  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise ValidationError(
            "PDF rendering requires the 'reportlab' package (pip install -r requirements.txt)."
        ) from exc
    return canvas, LETTER


def _fmt(value) -> str:  # noqa: ANN001
    return f"${_d(value):,.2f}"


def render_pdf(db: Session, patient_id: int, statement_id: int, tenant_id: int) -> bytes:
    stmt = get_statement(db, patient_id, statement_id, tenant_id)
    office = db.get(Office, stmt.office_id) if stmt.office_id else None
    snapshot = stmt.snapshot or {}

    canvas, LETTER = _pdf_canvas()
    buf = io.BytesIO()
    width, height = LETTER
    pdf = canvas.Canvas(buf, pagesize=LETTER)
    pdf.setTitle(f"Statement {stmt.id}")
    y = height - 60

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(54, y, "Account Statement")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(width - 54, y, office.name if office else "")
    y -= 26

    pdf.setFont("Helvetica", 10)
    for label, value in (
        ("Patient", snapshot.get("patient_name") or f"Patient {stmt.patient_id}"),
        ("Chart #", snapshot.get("chart_no") or "—"),
        ("Statement date", str(stmt.statement_date)),
        ("Period", f"{stmt.period_start or '—'} → {stmt.period_end or '—'}"),
    ):
        pdf.drawString(54, y, f"{label}:")
        pdf.drawString(180, y, str(value))
        y -= 14

    y -= 12
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(54, y, "Account activity")
    y -= 16
    pdf.setFont("Helvetica", 10)
    for label, value in (
        ("Opening balance", stmt.opening_balance),
        ("Charges", stmt.total_charges),
        ("Payments", stmt.total_payments),
        ("Adjustments", stmt.total_adjustments),
    ):
        pdf.drawString(70, y, label)
        pdf.drawRightString(width - 70, y, _fmt(value))
        y -= 14
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(70, y, "Balance due")
    pdf.drawRightString(width - 70, y, _fmt(stmt.closing_balance))
    y -= 24

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(54, y, "Aging")
    y -= 14
    pdf.setFont("Helvetica", 9)
    for label, value in (
        ("Current", stmt.aging_current), ("31-60", stmt.aging_30), ("61-90", stmt.aging_60),
        ("91-120", stmt.aging_90), ("120+", stmt.aging_120),
    ):
        pdf.drawString(70, y, label)
        pdf.drawRightString(width - 70, y, _fmt(value))
        y -= 12

    if stmt.message:
        y -= 12
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.drawString(54, y, stmt.message[:110])

    pdf.setFont("Helvetica-Oblique", 7)
    pdf.drawString(54, 48, f"Generated {datetime.now(timezone.utc).isoformat()} · statement {stmt.id}")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()
