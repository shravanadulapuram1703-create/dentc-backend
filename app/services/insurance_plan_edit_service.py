"""Edit Insurance Plan from the patient screen — the shared-plan safeguards.

Backs ``docs/patient-insurance/edit_insurance_plan_backend_devreport.md``
(EDIT-PLAN-2 usage, EDIT-PLAN-3 re-estimate cascade, EDIT-PLAN-6 history).
EDIT-PLAN-1 (optimistic concurrency) lives in :mod:`app.core.concurrency`,
EDIT-PLAN-4 (subscriber group-number cascade) in
:mod:`app.services.insurance_service`, EDIT-PLAN-5 (permissions + lock) in
:mod:`app.services.permission_service`.

One ``insurance_plans`` row is shared by every patient linked to it, so an
edit from one patient's slot screen changes what every other patient on the
plan pays. The frontend wraps the save in an impact banner and a confirmation;
what it could not compute on its own is here:

* **Usage** (:func:`plan_usage`) — how many *distinct* patients, subscribers,
  open claims and pending treatment-plan items sit on the plan, in a handful
  of index-backed counts. The banner had been reading two list totals with
  ``size=1``, one of which was a 96k-row sequential scan (``insurance_claims``
  had no index on ``ins_plan_id``), and counted a patient once per slot.

* **Re-estimate cascade** (:func:`affected_treatment_plans`,
  :func:`re_estimate_cascade`) — coverage %, deductibles and frequency rules
  drive the patient / insurance split, and a saved edit left every existing
  treatment-plan estimate at the old numbers with no way even to list them.
  The affected set is defined once (``treatment_service.
  affected_by_insurance_plan_clause``) and shared with
  ``GET /treatment-plans?ins_plan_id=``; the cascade runs the existing
  per-plan ``re_estimate`` inline under a cap, one failure recorded per plan
  rather than aborting the sweep, ``dry_run`` for the "N pending plans" prompt.

* **History** (:func:`plan_history`) — ``audit_logs`` recorded a plan PATCH
  with its field diff, but a coverage-rule edit logged under its *own* id, so
  "what changed on plan X" needed a lookup per rule and returned ``user_id``
  only. Child-row writes now stamp ``details.scope.ins_plan_id`` and the bulk
  PUT records ``details.changes[]``; this read aggregates plan + rule +
  frequency-group rows (including rows written *before* the scope existed,
  matched on the plan's current rule ids and a create's ``after.ins_plan_id``)
  with user names, and carries the "Modified by / on" strip.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import audit_context, concurrency
from app.core.exceptions import ValidationError
from app.db.models import (
    FeeSchedule,
    InsuranceClaim,
    InsuranceCoverageRule,
    InsurancePlanFrequencyGroup,
    InsuranceSubscriber,
    OrthoPlan,
    Patient,
    PatientInsurance,
    TreatmentPlan,
    TreatmentPlanItem,
)
from app.db.models.audit import AuditLog
from app.services import billing_service, treatment_service
from app.services.insurance_plan_service import get_plan
from app.services.treatment_service import COMPLETED_STATUS, affected_by_insurance_plan_clause
from app.services.user_admin_service import resolve_user_names

#: A claim in one of these states is settled — it no longer carries an
#: *estimate* a coverage change could move. Everything else is ``claims_open``.
CLOSED_CLAIM_STATUSES: frozenset[str] = frozenset({
    "closed", "paid", "denied", "rejected", "void", "voided", "cancelled", "canceled",
})

PLAN_RESOURCE = "insurance-plans"
RULE_RESOURCE = "insurance-coverage-rules"
GROUP_RESOURCE = "insurance-plan-frequency-groups"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── EDIT-PLAN-2: usage ───────────────────────────────────────────────────────
def _open_items_subquery():
    """``(plan_id, n)`` — open (not completed, not archived) items per plan."""
    return (
        select(
            TreatmentPlanItem.plan_id.label("plan_id"),
            func.count().label("n"),
            func.max(TreatmentPlanItem.updated_at).label("last_updated_at"),
        )
        .where(
            TreatmentPlanItem.is_archived.is_(False),
            TreatmentPlanItem.status != COMPLETED_STATUS,
        )
        .group_by(TreatmentPlanItem.plan_id)
        .subquery()
    )


def _affected_base(ins_plan_id: int):
    """Treatment plans in the affected set that still have an open item."""
    open_items = _open_items_subquery()
    stmt = (
        select(TreatmentPlan, open_items.c.n, open_items.c.last_updated_at)
        .join(open_items, open_items.c.plan_id == TreatmentPlan.id)
        .where(affected_by_insurance_plan_clause(ins_plan_id))
    )
    return stmt, open_items


def plan_usage(db: Session, plan_id: int, tenant_id: int | None) -> dict[str, Any]:
    plan = get_plan(db, plan_id, tenant_id)
    pid = plan.id

    def _count(stmt) -> int:  # noqa: ANN001
        return int(db.execute(stmt).scalar_one() or 0)

    active_links = select(PatientInsurance).where(
        PatientInsurance.ins_plan_id == pid, PatientInsurance.is_active.is_(True),
    )
    patients = _count(select(func.count(func.distinct(PatientInsurance.patient_id)))
                      .where(PatientInsurance.ins_plan_id == pid, PatientInsurance.is_active.is_(True)))
    patient_links = _count(select(func.count()).select_from(active_links.subquery()))
    subscribers = _count(select(func.count()).where(
        InsuranceSubscriber.ins_plan_id == pid, InsuranceSubscriber.is_active.is_(True),
    ))

    by_status: dict[str, int] = {}
    for status_value, n in db.execute(
        select(InsuranceClaim.status, func.count())
        .where(InsuranceClaim.ins_plan_id == pid, InsuranceClaim.is_active.is_(True))
        .group_by(InsuranceClaim.status)
    ):
        by_status[(status_value or "").lower() or "unknown"] = int(n)
    claims_total = sum(by_status.values())
    claims_open = sum(n for s, n in by_status.items() if s not in CLOSED_CLAIM_STATUSES)
    claims_other = _count(select(func.count()).where(
        InsuranceClaim.other_ins_plan_id == pid, InsuranceClaim.is_active.is_(True),
    ))

    base, open_items = _affected_base(pid)
    tp_rows = db.execute(
        select(func.count(), func.coalesce(func.sum(open_items.c.n), 0))
        .select_from(base.subquery())
    ).one()
    treatment_plans, pending_items = int(tp_rows[0] or 0), int(tp_rows[1] or 0)

    # Ortho contracts are the only payment plans that name an insurance plan
    # (``patient_payment_plans`` carries no plan FK).
    payment_plans = _count(select(func.count()).where(or_(
        OrthoPlan.ins_plan_id == pid, OrthoPlan.sec_ins_plan_id == pid,
    )))
    fee_schedules = _count(select(func.count()).where(FeeSchedule.ins_plan_id == pid))

    stamps = [
        db.execute(select(func.max(PatientInsurance.created_at))
                   .where(PatientInsurance.ins_plan_id == pid)).scalar_one(),
        db.execute(select(func.max(InsuranceSubscriber.created_at))
                   .where(InsuranceSubscriber.ins_plan_id == pid)).scalar_one(),
        db.execute(select(func.max(InsuranceClaim.created_at))
                   .where(InsuranceClaim.ins_plan_id == pid)).scalar_one(),
    ]
    last_used = max((s for s in stamps if s is not None), default=None)

    return {
        "plan_id": pid,
        "patients": patients,
        "patient_links": patient_links,
        "subscribers": subscribers,
        "claims_total": claims_total,
        "claims_open": claims_open,
        "claims_by_status": by_status,
        "claims_as_other_coverage": claims_other,
        "treatment_plans": treatment_plans,
        "treatment_plan_items_pending": pending_items,
        "payment_plans": payment_plans,
        "fee_schedules": fee_schedules,
        "last_used_at": last_used,
        "is_locked": bool(plan.is_locked),
        "shared": patients > 1,
    }


# ── EDIT-PLAN-3: affected treatment plans + the cascade ──────────────────────
def _affected_rows(db: Session, plan_id: int, *, offset: int | None = None, limit: int | None = None):
    base, _ = _affected_base(plan_id)
    total = int(db.execute(select(func.count()).select_from(base.subquery())).scalar_one() or 0)
    stmt = base.order_by(TreatmentPlan.created_at.desc(), TreatmentPlan.id.asc())
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = db.execute(stmt).all()
    return rows, total


def _describe_affected(db: Session, plan_id: int, rows) -> list[dict[str, Any]]:  # noqa: ANN001
    patient_ids = {tp.patient_id for tp, _, _ in rows}
    names: dict[int, str] = {}
    if patient_ids:
        for p in db.execute(select(Patient).where(Patient.id.in_(patient_ids))).scalars():
            names[p.id] = ", ".join(x for x in (p.last_name, p.first_name) if x) or f"Patient {p.id}"
    covered = set(db.execute(
        select(PatientInsurance.patient_id).where(
            PatientInsurance.ins_plan_id == plan_id,
            PatientInsurance.is_active.is_(True),
            PatientInsurance.patient_id.in_(patient_ids),
        )
    ).scalars().all()) if patient_ids else set()
    return [
        {
            "id": tp.id,
            "patient_id": tp.patient_id,
            "patient_name": names.get(tp.patient_id),
            "name": tp.name,
            "status": tp.status,
            "office_id": tp.office_id,
            "pending_items": int(n or 0),
            "coverage_source": "active_slot" if tp.patient_id in covered else "estimated_against",
            "last_updated_at": last_updated,
        }
        for tp, n, last_updated in rows
    ]


def affected_treatment_plans(
    db: Session, plan_id: int, tenant_id: int | None, *, page: int = 1, size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    plan = get_plan(db, plan_id, tenant_id)
    rows, total = _affected_rows(db, plan.id, offset=(page - 1) * size, limit=size)
    return _describe_affected(db, plan.id, rows), total


def _open_estimate_total(db: Session, treatment_plan_id: str) -> Decimal:
    value = db.execute(
        select(func.coalesce(func.sum(TreatmentPlanItem.insurance_estimate), 0)).where(
            TreatmentPlanItem.plan_id == treatment_plan_id,
            TreatmentPlanItem.is_archived.is_(False),
            TreatmentPlanItem.status != COMPLETED_STATUS,
        )
    ).scalar_one()
    return Decimal(str(value or 0))


def re_estimate_cascade(
    db: Session,
    plan_id: int,
    tenant_id: int,
    *,
    actor_id: int | None,
    dry_run: bool = False,
    use_new_fees: bool = False,
    treatment_plan_ids: list[str] | None = None,
    max_plans: int = 500,
    recalculate_claims: bool = True,
) -> dict[str, Any]:
    """Re-run the treatment-plan estimate for every plan the coverage edit
    affects (and re-sum the plan's open claims from their lines).

    Runs **inline** under ``max_plans``; a per-plan failure is recorded on that
    line and the sweep continues — one bad plan must not undo the other N.
    ``re_estimate`` reads the patient's *current* active coverage, so a plan
    whose patient has since moved to another plan is refreshed to that plan —
    which is the correct current answer, not the stale one.
    """
    started = _utcnow()
    plan = get_plan(db, plan_id, tenant_id)
    rows, total = _affected_rows(db, plan.id)
    described = _describe_affected(db, plan.id, rows)

    if treatment_plan_ids is not None:
        wanted = [str(x) for x in treatment_plan_ids]
        known = {d["id"] for d in described}
        unknown = sorted(set(wanted) - known)
        if unknown:
            raise ValidationError(
                "Some treatment plans are not affected by this insurance plan",
                code="treatment_plan_not_affected",
                details={"treatment_plan_ids": unknown},
            )
        described = [d for d in described if d["id"] in set(wanted)]
    truncated = len(described) > max_plans
    described = described[:max_plans]

    lines: list[dict[str, Any]] = []
    counts = {"re_estimated": 0, "unchanged": 0, "failed": 0}
    for entry in described:
        before = _open_estimate_total(db, entry["id"])
        line = {
            "treatment_plan_id": entry["id"], "patient_id": entry["patient_id"],
            "items": entry["pending_items"],
            "insurance_estimate_before": before, "insurance_estimate_after": None,
            "status": "planned", "error": None,
        }
        if not dry_run:
            try:
                result = treatment_service.re_estimate(
                    db, entry["id"], tenant_id, use_new_fees=use_new_fees,
                )
                after = Decimal(str(result.total_insurance_estimate))
                line["insurance_estimate_after"] = after
                line["status"] = "re_estimated" if after != before else "unchanged"
                counts[line["status"]] += 1
            except Exception as exc:  # noqa: BLE001 - one plan must not abort the sweep
                db.rollback()
                line["status"] = "failed"
                line["error"] = str(exc)[:300]
                counts["failed"] += 1
        lines.append(line)

    open_claim_ids = [
        cid for cid, status_value in db.execute(
            select(InsuranceClaim.id, InsuranceClaim.status).where(
                InsuranceClaim.ins_plan_id == plan.id, InsuranceClaim.is_active.is_(True),
            )
        )
        if (status_value or "").lower() not in CLOSED_CLAIM_STATUSES
    ]
    claims_recalculated = 0
    if recalculate_claims and not dry_run:
        for cid in open_claim_ids:
            try:
                billing_service.recalculate_claim(db, cid, tenant_id)
                claims_recalculated += 1
            except Exception:  # noqa: BLE001
                db.rollback()

    if not dry_run:
        audit_context.record(
            resource_id=str(plan.id), row_id=plan.id,
            scope={"ins_plan_id": plan.id},
            after={"re_estimate": {
                "affected": total, **counts, "claims_recalculated": claims_recalculated,
                "use_new_fees": use_new_fees, "actor_id": actor_id,
            }},
        )
    return {
        "plan_id": plan.id,
        "dry_run": dry_run,
        "use_new_fees": use_new_fees,
        "affected": total,
        **counts,
        "truncated": truncated,
        "claims_open": len(open_claim_ids),
        "claims_recalculated": claims_recalculated,
        "treatment_plans": lines,
        "started_at": started,
        "finished_at": _utcnow(),
    }


# ── EDIT-PLAN-6: history ─────────────────────────────────────────────────────
def _source_of(row: AuditLog) -> str:
    if row.resource_type == RULE_RESOURCE:
        return "coverage_rule"
    if row.resource_type == GROUP_RESOURCE:
        return "frequency_group"
    path = row.path or ""
    if path.endswith("/coverage-rules"):
        return "coverage_bulk"
    if "/copy-from/" in path:
        return "copy"
    if path.endswith("/re-estimate"):
        return "re_estimate"
    return "plan"


def _summary_of(row: AuditLog, source: str, changes: list[dict]) -> str:
    details = row.details or {}
    after = details.get("after") or {}
    before = details.get("before") or {}
    fields = sorted(set(after) | set(before))
    verb = {"POST": "Created", "PATCH": "Updated", "PUT": "Replaced", "DELETE": "Deleted"}.get(
        row.method, row.method
    )
    if source == "coverage_bulk" or source == "copy":
        tally: dict[str, int] = {}
        for c in changes:
            tally[c.get("action") or "?"] = tally.get(c.get("action") or "?", 0) + 1
        parts = [f"{n} {a}d" if not a.endswith("e") else f"{n} {a}d" for a, n in sorted(tally.items())]
        head = "Copied coverage" if source == "copy" else "Replaced coverage"
        return f"{head}: " + (", ".join(parts) if parts else "no row changes")
    if source == "re_estimate":
        info = after.get("re_estimate") or {}
        return (f"Re-estimated {info.get('re_estimated', 0)} of {info.get('affected', 0)} "
                f"treatment plans")
    scope = details.get("scope") or {}
    if source == "coverage_rule":
        label = after.get("start_code") or before.get("start_code") or scope.get("label") or row.resource_id
        return f"{verb} coverage rule {label}" + (f": {', '.join(fields)}" if fields and row.method != "POST" else "")
    if source == "frequency_group":
        label = after.get("code_group") or before.get("code_group") or scope.get("label") or row.resource_id
        return f"{verb} frequency group {label}" + (f": {', '.join(fields)}" if fields and row.method != "POST" else "")
    if row.method == "DELETE":
        return "Deactivated plan" if after.get("is_active") is False or "is_active" in before else "Deleted plan"
    return f"{verb} plan" + (f": {', '.join(fields)}" if fields else "")


def plan_history(
    db: Session, plan_id: int, tenant_id: int | None, *, page: int = 1, size: int = 50,
) -> dict[str, Any]:
    plan = get_plan(db, plan_id, tenant_id)
    pid = plan.id
    rule_ids = [str(r) for r in db.execute(
        select(InsuranceCoverageRule.id).where(InsuranceCoverageRule.ins_plan_id == pid)
    ).scalars()]
    group_ids = [str(g) for g in db.execute(
        select(InsurancePlanFrequencyGroup.id).where(InsurancePlanFrequencyGroup.ins_plan_id == pid)
    ).scalars()]

    child_match = [
        AuditLog.details["scope"]["ins_plan_id"].as_integer() == pid,
        # Rows written before the scope existed: a create carried the plan id
        # in its payload; an update / delete of a rule still on the plan is
        # matched on the rule's id.
        AuditLog.details["after"]["ins_plan_id"].as_integer() == pid,
    ]
    if rule_ids or group_ids:
        child_match.append(AuditLog.resource_id.in_(rule_ids + group_ids))
    where = or_(
        (AuditLog.resource_type == PLAN_RESOURCE) & (AuditLog.resource_id == str(pid)),
        AuditLog.resource_type.in_((RULE_RESOURCE, GROUP_RESOURCE)) & or_(*child_match),
    )
    stmt = select(AuditLog).where(where)
    if tenant_id is not None:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one() or 0)
    rows = list(db.execute(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * size).limit(size)
    ).scalars())

    user_ids = {r.user_id for r in rows if r.user_id is not None}
    user_ids |= {plan.updated_by} if plan.updated_by is not None else set()
    names = resolve_user_names(db, user_ids)

    items = []
    for r in rows:
        details = r.details or {}
        changes = list(details.get("changes") or [])
        source = _source_of(r)
        items.append({
            "id": r.id,
            "at": r.created_at,
            "user_id": r.user_id,
            "user_name": names.get(r.user_id),
            "action": r.method,
            "source": source,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "path": r.path,
            "before": details.get("before"),
            "after": details.get("after"),
            "changes": changes,
            "summary": _summary_of(r, source, changes),
        })
    pages = (total + size - 1) // size if size else 0
    return {
        "plan_id": pid,
        "items": items,
        "meta": {"page": page, "size": size, "total": total, "pages": pages},
        "created_at": plan.created_at,
        "created_by_name": plan.created_by,
        "updated_at": plan.updated_at,
        "updated_by_name": (names.get(plan.updated_by) if plan.updated_by is not None else None)
        or plan.modified_by,
        "version": concurrency.version_token(concurrency.version_of(plan)),
    }


__all__ = [
    "CLOSED_CLAIM_STATUSES",
    "affected_treatment_plans",
    "plan_history",
    "plan_usage",
    "re_estimate_cascade",
]
