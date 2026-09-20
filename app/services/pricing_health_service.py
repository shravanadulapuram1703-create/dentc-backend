"""Setup → pricing health report (§3.6).

One place that answers "what would mis-price a charge, and whose screen owns the
fix?" — the pull-based half of keeping the three fee/coverage maintainers in sync.
Each finding carries a stable ``code``, a ``severity``, the owning ``screen``, and
enough detail (an office id, a count) to act on. Every check here is a cheap
indexed query; the volume-ranked findings (a bound schedule missing a
high-traffic code, client-legacy/unpriced charges actually posted) are a later
addition that scans charge history.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    FeeSchedule,
    FeeScheduleAssignment,
    FeeScheduleEntry,
    Office,
    ProcedureCode,
)
from app.services import fee_vocab


def _finding(code: str, screen: str, *, severity: str = "warning", **detail) -> dict:
    return {"code": code, "severity": severity, "screen": screen, **detail}


def report(db: Session, tenant_id: int, *, office_id: int | None = None) -> dict:
    """The findings for one tenant (optionally one office). ``findings`` is a flat
    list so the UI can group by ``screen`` or ``office_id`` as it likes."""
    findings: list[dict] = []
    findings += _office_findings(db, tenant_id, office_id)
    findings += _assignment_findings(db, tenant_id)
    findings += _entry_findings(db, tenant_id)
    findings += _code_findings(db)

    by_code: dict[str, int] = {}
    for f in findings:
        by_code[f["code"]] = by_code.get(f["code"], 0) + 1
    return {"findings": findings, "summary": {"total": len(findings), "by_code": by_code}}


def _office_findings(db: Session, tenant_id: int, office_id: int | None) -> list[dict]:
    stmt = select(Office).where(Office.tenant_id == tenant_id, Office.is_active.is_(True))
    if office_id is not None:
        stmt = stmt.where(Office.id == office_id)
    out: list[dict] = []
    for office in db.execute(stmt).scalars().all():
        if office.default_ucr_fee_schedule_id is None:
            # An office that posts charges needs a UCR list to compute the write-off.
            out.append(_finding("office_without_ucr", "Setup - Offices - Fee Defaults",
                                severity="error", office_id=office.id, office_name=office.name))
        if office.default_fee_schedule_id is None:
            out.append(_finding("office_without_default", "Setup - Offices - Fee Defaults",
                                office_id=office.id, office_name=office.name))
    return out


def _assignment_findings(db: Session, tenant_id: int) -> list[dict]:
    out: list[dict] = []
    rows = db.execute(
        select(FeeScheduleAssignment).where(FeeScheduleAssignment.tenant_id == tenant_id)
    ).scalars().all()
    unreachable = 0
    inactive: list[int] = []
    for row in rows:
        if not fee_vocab.has_assignment_target(row):
            # A scope-only / all-NULL row can never win a walk — the eight legacy
            # practice-wide rows. New ones are refused; these are cleanup.
            unreachable += 1
            continue
        sched = db.get(FeeSchedule, row.fee_schedule_id) if row.fee_schedule_id else None
        if sched is None or not sched.is_active:
            inactive.append(row.id)
    if unreachable:
        out.append(_finding("assignment_never_reachable",
                            "Setup - Fee Schedules - Assignments",
                            count=unreachable))
    if inactive:
        out.append(_finding("assignment_to_inactive_schedule",
                            "Setup - Fee Schedules - Assignments",
                            severity="error", count=len(inactive),
                            assignment_ids=inactive[:50]))
    return out


def _entry_findings(db: Session, tenant_id: int) -> list[dict]:
    out: list[dict] = []
    # Plan Pays sitting on a percentage list — the guard refuses new ones, so any
    # hit is a legacy row to clean up.
    bad_plan_pays = db.execute(
        select(func.count()).select_from(FeeScheduleEntry).join(
            FeeSchedule, FeeSchedule.id == FeeScheduleEntry.fee_schedule_id
        ).where(
            FeeScheduleEntry.tenant_id == tenant_id,
            FeeScheduleEntry.insurance_fee.is_not(None),
            FeeScheduleEntry.insurance_fee > 0,
            FeeSchedule.pricing_model == "percentage",
        )
    ).scalar() or 0
    if bad_plan_pays:
        out.append(_finding("insurance_fee_on_percentage_schedule",
                            "Setup - Fee Schedules", count=int(bad_plan_pays)))
    # $0 (blank PATAMT) entries on a percentage list that is not flagged no-charge:
    # today they win a walk and post $0.
    zero_fee = db.execute(
        select(func.count()).select_from(FeeScheduleEntry).join(
            FeeSchedule, FeeSchedule.id == FeeScheduleEntry.fee_schedule_id
        ).where(
            FeeScheduleEntry.tenant_id == tenant_id,
            FeeSchedule.pricing_model == "percentage",
            FeeScheduleEntry.is_no_charge.is_(False),
            (FeeScheduleEntry.patient_fee.is_(None)) | (FeeScheduleEntry.patient_fee <= 0),
        )
    ).scalar() or 0
    if zero_fee:
        out.append(_finding("zero_fee_entries", "Setup - Fee Schedules",
                            count=int(zero_fee)))
    return out


def _code_findings(db: Session) -> list[dict]:
    # procedure_codes is global (no tenant_id); a NULL coverage_category means the
    # estimate engine cannot band it (FEE-1) — "unknown", never "non-covered".
    missing = db.execute(
        select(func.count()).select_from(ProcedureCode).where(
            ProcedureCode.coverage_category.is_(None),
            ProcedureCode.code.like("D%"),
        )
    ).scalar() or 0
    if missing:
        return [_finding("code_without_coverage_category", "Setup - Procedure Codes",
                         count=int(missing))]
    return []
