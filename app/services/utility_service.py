"""Utilities execution / audit service (UTIL-1/2/3).

Records every utility execution as a durable, tenant-wide ``utility_runs`` row —
the audit trail + job record the Utilities dashboard reads (replacing the
per-browser localStorage history). Server-side duplicate-run prevention per
(utility, office) is enforced here (UTIL-1). The *actual batch business logic*
for each utility (claims batch, contract charges, PGID migration, …) is a separate
effort; a submitted run is recorded and marked ``completed`` with a note so the UX
and audit are real today. Authorization is enforced at the route (UTIL-3).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.models import User, UtilityRun

_ACTIVE = ("submitted", "running")

#: OFF-SCOPE-16: utilities that operate on one office's data and therefore
#: require an ``office_id``. The frontend marks these ``officeScoped``; the set
#: is here (rather than a config list) so it versions with the code. Empty until
#: the office-scoped batch engines land — an office-scoped utility with no
#: office is a 422 ``office_id_required``.
OFFICE_SCOPED_UTILITIES: frozenset[str] = frozenset()


def submit_run(
    db: Session, tenant_id: int, user: User, utility_id: str,
    *, office_id: int | None = None, parameters: dict | None = None,
) -> UtilityRun:
    # OFF-SCOPE-16: an office-scoped utility must name an office, and any office a
    # run targets must be one the caller is assigned to (unless privileged).
    if utility_id in OFFICE_SCOPED_UTILITIES and office_id is None:
        raise ValidationError(
            f"Utility '{utility_id}' requires an office",
            code="office_id_required",
            details={"field": "office_id", "utility_id": utility_id},
        )
    if office_id is not None:
        from app.services import office_scope_service, permission_service

        rights = permission_service.office_rights(db, user)
        privileged = bool(
            rights & {permission_service.OFFICES_VIEW_ALL, permission_service.OFFICES_SWITCH_ANY}
        )
        assigned = office_scope_service.assigned_office_ids(db, user.id, tenant_id)
        if not privileged and assigned and int(office_id) not in assigned:
            from app.core.exceptions import ForbiddenError

            raise ForbiddenError(
                f"Office '{office_id}' is not assigned to you",
                code="office_not_assigned",
                details={"office_id": int(office_id), "field": "office_id"},
            )
    # UTIL-1: server-side duplicate-run prevention per (utility, office).
    existing = db.execute(
        select(UtilityRun.id).where(
            UtilityRun.tenant_id == tenant_id,
            UtilityRun.utility_id == utility_id,
            UtilityRun.office_id.is_(office_id) if office_id is None else UtilityRun.office_id == office_id,
            UtilityRun.status.in_(_ACTIVE),
        )
    ).scalars().first()
    if existing is not None:
        raise ConflictError(
            f"Utility '{utility_id}' is already running for this office", code="utility_in_progress"
        )

    run = UtilityRun(
        tenant_id=tenant_id, utility_id=utility_id, office_id=office_id,
        run_by=user.id, status="completed", parameters=parameters,
        processed=0, succeeded=0, failed=0,
        logs=["Run recorded. The batch execution engine for this utility is a "
              "follow-up (UTIL-1); no records were processed."],
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, tenant_id: int, job_id: int) -> UtilityRun:
    run = db.get(UtilityRun, job_id)
    if run is None or run.tenant_id != tenant_id:
        raise NotFoundError(f"Utility run '{job_id}' was not found")
    return run


def list_audit(
    db: Session, tenant_id: int, *, utility_id: str | None = None, office_id: int | None = None,
    run_by: int | None = None, date_from: date | None = None, date_to: date | None = None,
    limit: int = 100,
) -> list[UtilityRun]:
    stmt = select(UtilityRun).where(UtilityRun.tenant_id == tenant_id)
    if utility_id is not None:
        stmt = stmt.where(UtilityRun.utility_id == utility_id)
    if office_id is not None:
        stmt = stmt.where(UtilityRun.office_id == office_id)
    if run_by is not None:
        stmt = stmt.where(UtilityRun.run_by == run_by)
    if date_from is not None:
        stmt = stmt.where(UtilityRun.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        stmt = stmt.where(UtilityRun.created_at <= datetime.combine(date_to, datetime.max.time()))
    stmt = stmt.order_by(UtilityRun.created_at.desc(), UtilityRun.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())
