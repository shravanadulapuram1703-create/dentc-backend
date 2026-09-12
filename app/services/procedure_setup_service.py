"""Procedure Code Setup service (PROC-2/3/5/6).

Procedure codes are a global catalog (no ``tenant_id``); stats aggregate the whole
catalog, consistent with the list endpoint. The provider permission set and the
per-code insurance rules are tenant-scoped.
"""

from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.models import (
    FeeSchedule,
    ProcedureCode,
    ProcedureInsuranceRule,
    Provider,
    ProviderProcedureCode,
)


def get_code(db: Session, code: str) -> ProcedureCode:
    row = db.get(ProcedureCode, code)
    if row is None:
        raise NotFoundError(f"ProcedureCode '{code}' was not found")
    return row


# ── PROC-5: catalog KPI stats ────────────────────────────────────────────────
def stats(db: Session) -> dict:
    total = db.execute(select(func.count()).select_from(ProcedureCode)).scalar_one()
    active = db.execute(
        select(func.count()).select_from(ProcedureCode).where(ProcedureCode.is_active.is_(True))
    ).scalar_one()
    ortho = db.execute(
        select(func.count()).select_from(ProcedureCode).where(ProcedureCode.is_ortho.is_(True))
    ).scalar_one()
    by_category = {
        (cat or "Uncategorized"): int(count)
        for cat, count in db.execute(
            select(ProcedureCode.category, func.count()).group_by(ProcedureCode.category)
        ).all()
    }
    return {
        "total": int(total),
        "active": int(active),
        "inactive": int(total) - int(active),
        "ortho": int(ortho),
        "by_category": by_category,
    }


# ── APPT-10: category taxonomy ───────────────────────────────────────────────
def list_categories(db: Session, *, active_only: bool = False) -> list[dict]:
    """The distinct procedure-code categories with their code counts.

    Sourced from ``procedure_codes.category`` (the same column ``stats()`` groups
    by) so the taxonomy can never drift from the catalog it describes. NULL/blank
    categories collapse into "Uncategorized" — the codes still exist and the
    picker must be able to reach them.
    """
    stmt = select(
        ProcedureCode.category,
        func.count(),
        func.sum(case((ProcedureCode.is_active.is_(True), 1), else_=0)),
    ).group_by(ProcedureCode.category)
    if active_only:
        stmt = stmt.where(ProcedureCode.is_active.is_(True))

    rolled: dict[str, list[int]] = {}
    for cat, total, active in db.execute(stmt).all():
        key = (cat or "").strip() or "Uncategorized"
        bucket = rolled.setdefault(key, [0, 0])
        bucket[0] += int(total or 0)
        bucket[1] += int(active or 0)
    return [
        {"category": key, "code_count": counts[0], "active_code_count": counts[1]}
        for key, counts in sorted(rolled.items(), key=lambda kv: kv[0].lower())
    ]


# ── PROC-2: provider↔procedure permission set ────────────────────────────────
def get_provider_codes(db: Session, provider_id: str) -> list[ProcedureCode]:
    sub = select(ProviderProcedureCode.procedure_code).where(
        ProviderProcedureCode.provider_id == provider_id
    )
    return list(db.execute(
        select(ProcedureCode).where(ProcedureCode.code.in_(sub)).order_by(ProcedureCode.code.asc())
    ).scalars().all())


def set_provider_codes(
    db: Session, provider_id: str, tenant_id: int, codes: list[str]
) -> list[ProcedureCode]:
    existing = {
        link.procedure_code: link
        for link in db.execute(
            select(ProviderProcedureCode).where(ProviderProcedureCode.provider_id == provider_id)
        ).scalars()
    }
    desired = set(codes)
    for code, link in existing.items():
        if code not in desired:
            db.delete(link)
    for code in desired:
        if code not in existing:
            db.add(ProviderProcedureCode(tenant_id=tenant_id, provider_id=provider_id, procedure_code=code))
    db.commit()
    return get_provider_codes(db, provider_id)


def providers_for_code(db: Session, tenant_id: int, code: str) -> list[Provider]:
    """PLAN-16 reverse lookup: the providers assigned ``code`` in this tenant.
    Empty means *unrestricted* — nobody has been limited, so everyone may perform it."""
    sub = select(ProviderProcedureCode.provider_id).where(
        ProviderProcedureCode.tenant_id == tenant_id,
        ProviderProcedureCode.procedure_code == code,
    )
    return list(db.execute(
        select(Provider).where(Provider.id.in_(sub)).order_by(Provider.name.asc(), Provider.id.asc())
    ).scalars().all())


def code_eligibility(db: Session, tenant_id: int, codes: list[str]) -> dict:
    """PLAN-16 batched form: for each requested code, who may perform it, plus
    the intersection for a multi-row Change Provider. One query, however many
    codes and providers — the client used to fan out one request per provider.

    Semantics (confirmed): a code with **no** assignment rows is unrestricted
    (``restricted=False``, empty ``provider_ids``) and does not narrow the
    intersection; ``eligible_for_all`` is ``None`` when nothing is restricted."""
    wanted = list(dict.fromkeys(c.strip() for c in codes if c and c.strip()))
    by_code: dict[str, list[str]] = {c: [] for c in wanted}
    if wanted:
        for provider_id, code in db.execute(
            select(ProviderProcedureCode.provider_id, ProviderProcedureCode.procedure_code)
            .where(ProviderProcedureCode.tenant_id == tenant_id,
                   ProviderProcedureCode.procedure_code.in_(wanted))
            .order_by(ProviderProcedureCode.provider_id.asc())
        ).all():
            by_code.setdefault(code, []).append(provider_id)
    restricted_all = list(db.execute(
        select(ProviderProcedureCode.provider_id)
        .where(ProviderProcedureCode.tenant_id == tenant_id)
        .distinct().order_by(ProviderProcedureCode.provider_id.asc())
    ).scalars().all())
    eligible: set[str] | None = None
    for code in wanted:
        ids = by_code.get(code) or []
        if not ids:
            continue
        eligible = set(ids) if eligible is None else (eligible & set(ids))
    return {
        "codes": [
            {"procedure_code": c, "restricted": bool(by_code.get(c)), "provider_ids": by_code.get(c) or []}
            for c in wanted
        ],
        "eligible_for_all": sorted(eligible) if eligible is not None else None,
        "restricted_provider_ids": restricted_all,
    }


# ── PROC-3: per-code insurance rules ─────────────────────────────────────────
def list_insurance_rules(db: Session, tenant_id: int, code: str) -> list[ProcedureInsuranceRule]:
    return list(db.execute(
        select(ProcedureInsuranceRule).where(
            ProcedureInsuranceRule.tenant_id == tenant_id,
            ProcedureInsuranceRule.procedure_code == code,
        ).order_by(ProcedureInsuranceRule.id.asc())
    ).scalars().all())


def _get_rule(db: Session, tenant_id: int, code: str, rule_id: int) -> ProcedureInsuranceRule:
    row = db.execute(
        select(ProcedureInsuranceRule).where(
            ProcedureInsuranceRule.id == rule_id,
            ProcedureInsuranceRule.tenant_id == tenant_id,
            ProcedureInsuranceRule.procedure_code == code,
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Insurance rule '{rule_id}' was not found")
    return row


def create_insurance_rule(
    db: Session, tenant_id: int, code: str, data: dict, user_id: int | None
) -> ProcedureInsuranceRule:
    row = ProcedureInsuranceRule(
        tenant_id=tenant_id, procedure_code=code, created_by=user_id, updated_by=user_id, **data
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_insurance_rule(
    db: Session, tenant_id: int, code: str, rule_id: int, data: dict, user_id: int | None
) -> ProcedureInsuranceRule:
    row = _get_rule(db, tenant_id, code, rule_id)
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def delete_insurance_rule(db: Session, tenant_id: int, code: str, rule_id: int) -> None:
    row = _get_rule(db, tenant_id, code, rule_id)
    db.delete(row)
    db.commit()


# ── PROC-6: lightweight fee-schedule id→name projection ──────────────────────
def fee_schedule_options(db: Session, tenant_id: int) -> list[dict]:
    rows = db.execute(
        select(FeeSchedule.id, FeeSchedule.name, FeeSchedule.fee_type)
        .where(FeeSchedule.tenant_id == tenant_id, FeeSchedule.is_active.is_(True))
        .order_by(FeeSchedule.name.asc())
    ).all()
    return [{"id": r[0], "name": r[1], "fee_type": r[2]} for r in rows]
