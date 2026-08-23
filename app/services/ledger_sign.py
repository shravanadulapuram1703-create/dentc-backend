"""The one place that decides what a ``patient_payments`` row does to a balance (AL-9).

**Why this module exists.** ``patient_payments`` carries two different kinds of
row and, historically, two different sign conventions:

* Rows migrated from Denticon ``LEDGER`` (``LTYPE`` ``P``/``I``/``A``) keep the
  legacy *signed ledger delta* — a payment is stored **negative** because money
  in reduces the balance, and an ``A`` (adjustment) row keeps whichever sign the
  practice posted it with.
* Rows created by this application store the **magnitude** of the payment,
  positive, and every consumer assumed "positive = credit".

Mixing the two double-negated the migrated rows: ``balance = charged - paid``
with ``paid = -417.50`` returned ``1093.00 - (-417.50) = 1510.50`` where the
legacy answer is ``675.50``, and the account-ledger feed emitted
``credit: -500.00`` *and* ``amount: +500.00`` for the same $500 payment, so a
payment made the running balance go **up**.

**The settled convention** (one rule, applied by every consumer through this
module):

``delta`` is what the row adds to the account balance.

===================  =========================================================
``payment_type``     ``delta``
===================  =========================================================
``adjustment``       ``amount`` verbatim — an adjustment is genuinely two-way
                     (a write-off credits, a late fee debits), so the stored
                     sign *is* the intent and must not be normalised away.
anything else        ``-abs(amount)`` — a payment always credits the account,
                     whichever sign it happens to be stored with.
===================  =========================================================

From ``delta`` everything else follows: ``credit = max(0, -delta)`` (money in,
always reported positive), ``debit = max(0, +delta)``, and a ledger row's signed
``amount`` is simply ``delta``.

A reversal never arrives here as a negative payment — ``refund_service`` writes a
first-class ``patient_refunds`` row (REF-1/2) — so ``-abs()`` cannot swallow a
deliberate negative.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Numeric, case, func, literal
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import PatientPayment

ZERO = Decimal("0")

#: ``payment_type`` whose stored sign is meaningful rather than a magnitude.
SIGNED_PAYMENT_TYPES = ("adjustment",)


def _d(value) -> Decimal:  # noqa: ANN001
    return Decimal(str(value or 0))


# ── Python-side (ORM rows already loaded) ────────────────────────────────────
def payment_delta(amount, payment_type: str | None) -> Decimal:  # noqa: ANN001
    """Signed balance delta of one payment row — negative credits the account."""
    value = _d(amount)
    if (payment_type or "").strip().lower() in SIGNED_PAYMENT_TYPES:
        return value
    return -abs(value)


def payment_credit(amount, payment_type: str | None) -> Decimal:  # noqa: ANN001
    """Money in, always ``>= 0`` (the ledger ``credit`` column / "total paid")."""
    delta = payment_delta(amount, payment_type)
    return -delta if delta < ZERO else ZERO


def payment_debit(amount, payment_type: str | None) -> Decimal:  # noqa: ANN001
    """Money out — a debit adjustment posted through ``patient_payments``."""
    delta = payment_delta(amount, payment_type)
    return delta if delta > ZERO else ZERO


# ── SQL-side (aggregates that must not load rows) ────────────────────────────
def _numeric(value: int) -> ColumnElement:
    return literal(value, Numeric(12, 2))


def payment_delta_sql(column=None, type_column=None) -> ColumnElement:  # noqa: ANN001
    """``payment_delta`` as a SQL expression, for ``sum()`` aggregates."""
    amount = PatientPayment.amount if column is None else column
    ptype = PatientPayment.payment_type if type_column is None else type_column
    return case(
        (func.lower(func.coalesce(ptype, "")).in_(SIGNED_PAYMENT_TYPES), amount),
        else_=-func.abs(amount),
    )


def payment_credit_sql(column=None, type_column=None) -> ColumnElement:  # noqa: ANN001
    """Positive money-in per row — ``sum()`` this for "total paid"."""
    delta = payment_delta_sql(column, type_column)
    return case((delta < 0, -delta), else_=_numeric(0))


def payment_debit_sql(column=None, type_column=None) -> ColumnElement:  # noqa: ANN001
    """Positive money-out per row — debit adjustments posted as payments."""
    delta = payment_delta_sql(column, type_column)
    return case((delta > 0, delta), else_=_numeric(0))


def sum_payment_credit() -> ColumnElement:
    return func.coalesce(func.sum(payment_credit_sql()), 0)


def sum_payment_debit() -> ColumnElement:
    return func.coalesce(func.sum(payment_debit_sql()), 0)


def sum_payment_delta() -> ColumnElement:
    return func.coalesce(func.sum(payment_delta_sql()), 0)
