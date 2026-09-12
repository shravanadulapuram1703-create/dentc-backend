"""Lab Tracking (legacy Denticon M12) — LAB-1..11.

A lab case **is an appointment** with lab fields; there is deliberately no
lab-case row (the legacy model, and the FE's). What this module adds is the
rule table around those fields and the office-wide read the per-patient
appointment listing could never give:

* :func:`derive_lab_status` — the one status derivation (``not_sent`` /
  ``sent`` / ``overdue`` / ``received``) the read field, the list filter, the
  cost report and the PDFs all share, so a client never re-derives it.
* :func:`apply_lab_rules` — the write-side contract enforced on **every**
  appointment write (generic CRUD create/update route through it):

  - ``has_lab = false`` **clears** the lab detail fields (LAB-8, implication —
    the un-ticked panel's residue is not intent; the Add/Edit form sends the
    stale DDS / cost along with the un-tick and must not 422).
  - any lab detail sent on a row whose ``has_lab`` is false, without ``has_lab``
    in the payload, **derives** ``has_lab = true`` — an appointment with lab
    data is a lab case.
  - ``lab_due_on`` / ``lab_received_on`` before ``lab_sent_on`` is 422
    ``lab_date_order`` (LAB-9), judged against the merge of payload + stored
    row, and only when the payload touches a lab date — re-pricing a migrated
    row with odd dates must not fail.
  - ``lab_vendor_id`` must be one of the tenant's labs (422
    ``lab_vendor_not_found``); an inactive vendor is refused only when the id
    *moves* onto it (``lab_vendor_inactive``) so an old case stays editable.

* :func:`list_lab_cases` — the denormalised, filtered, server-paged office /
  patient view (LAB-2 / LAB-5) with the per-status counts the review tabs need.
* :func:`lab_cost_report` + the PDF / CSV renderers (LAB-4).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.datetimes import office_today
from app.core.exceptions import ConflictError, ValidationError
from app.crud.base import CRUDBase
from app.db.models import Appointment, Lab, Office, Patient, Provider

# ── vocabulary ───────────────────────────────────────────────────────────────
LAB_STATUSES: tuple[str, ...] = ("not_sent", "sent", "overdue", "received")
LAB_STATUS_FILTERS: tuple[str, ...] = LAB_STATUSES + ("not_received",)
LAB_STATUS_LABELS = {
    "not_sent": "Not Sent",
    "sent": "Sent",
    "overdue": "Overdue",
    "received": "Received",
    "not_received": "Not Received",
}
#: Every lab column other than the ``has_lab`` switch itself.
LAB_DETAIL_FIELDS: tuple[str, ...] = (
    "lab_vendor_id", "lab_dds", "lab_cost", "lab_short_notice",
    "lab_sent_on", "lab_due_on", "lab_received_on",
)
LAB_DATE_FIELDS: tuple[str, ...] = ("lab_sent_on", "lab_due_on", "lab_received_on")
LAB_DDS_MAX_LENGTH = 100
LAB_COST_MAX_DIGITS = 10
LAB_COST_DECIMAL_PLACES = 2

COST_REPORT_GROUPS: tuple[str, ...] = ("vendor", "provider", "office", "month", "dds")
COST_REPORT_DATE_BASIS: tuple[str, ...] = ("appointment", "sent", "due", "received")
LAB_CASE_SORTS: tuple[str, ...] = (
    "date", "lab_sent_on", "lab_due_on", "lab_received_on", "lab_cost", "patient_name",
    "provider_name", "lab_vendor_name", "created_at", "updated_at",
)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def resolve_as_of(db: Session, office_id: int | None) -> date:
    """"Today" for the status derivation: the office's own date when one office
    is in scope (an evening "due today" must not read as overdue at 8 pm local
    because UTC rolled over), else UTC."""
    if office_id is not None:
        office = db.get(Office, office_id)
        if office is not None:
            return office_today(getattr(office, "timezone", None))
    return utc_today()


# ── status derivation ────────────────────────────────────────────────────────
def derive_lab_status(
    sent: date | None, due: date | None, received: date | None, today: date,
) -> str:
    """received -> ``received``; sent + due passed -> ``overdue``; sent ->
    ``sent``; else ``not_sent``. Mirrors the FE's ``deriveStatus`` exactly."""
    if received is not None:
        return "received"
    if sent is not None:
        if due is not None and due < today:
            return "overdue"
        return "sent"
    return "not_sent"


def lab_status_clause(status: str, today: date):  # noqa: ANN201
    """The SQL twin of :func:`derive_lab_status` for one status (or the legacy
    ``not_received`` review filter). Always implies ``has_lab = true``."""
    sent, due, received = (
        Appointment.lab_sent_on, Appointment.lab_due_on, Appointment.lab_received_on,
    )
    base = Appointment.has_lab.is_(True)
    if status == "received":
        return and_(base, received.is_not(None))
    if status == "not_sent":
        return and_(base, received.is_(None), sent.is_(None))
    if status == "overdue":
        return and_(base, received.is_(None), sent.is_not(None), due.is_not(None), due < today)
    if status == "sent":
        return and_(
            base, received.is_(None), sent.is_not(None), or_(due.is_(None), due >= today),
        )
    if status == "not_received":
        return and_(base, received.is_(None), sent.is_not(None))
    raise ValidationError(
        f"Unknown lab_status '{status}'",
        details={"code": "invalid_lab_status", "field": "lab_status", "allowed": list(LAB_STATUS_FILTERS)},
    )


def _status_case(today: date):  # noqa: ANN202
    """``CASE`` expression yielding the status label per row (for grouping)."""
    return case(
        (Appointment.lab_received_on.is_not(None), "received"),
        (and_(Appointment.lab_sent_on.is_not(None), Appointment.lab_due_on.is_not(None),
              Appointment.lab_due_on < today), "overdue"),
        (Appointment.lab_sent_on.is_not(None), "sent"),
        else_="not_sent",
    )


# ── write rules (LAB-8 / LAB-9 / LAB-1 vendor) ───────────────────────────────
def _is_empty(field: str, value: Any) -> bool:  # noqa: ANN401
    """"No lab data" for the has_lab derivation. A cost of 0 is empty because
    the migration wrote a literal ``0.00`` on every non-lab appointment."""
    if value is None:
        return True
    if field == "lab_short_notice":
        return not value
    if field == "lab_cost":
        try:
            return Decimal(str(value)) == 0
        except Exception:  # noqa: BLE001
            return False
    if isinstance(value, str):
        return not value.strip()
    return False


def _cleared() -> dict[str, Any]:
    out: dict[str, Any] = {f: None for f in LAB_DETAIL_FIELDS}
    out["lab_short_notice"] = False
    return out


def _require_vendor(db: Session, vendor_id: int, tenant_id: int | None, *, moved: bool) -> Lab:
    lab = db.get(Lab, vendor_id)
    if lab is None or (tenant_id is not None and lab.tenant_id != tenant_id):
        raise ValidationError(
            f"Lab '{vendor_id}' was not found",
            details={"code": "lab_vendor_not_found", "field": "lab_vendor_id"},
        )
    if moved and not lab.is_active:
        raise ValidationError(
            f"Lab '{lab.name}' is inactive",
            details={"code": "lab_vendor_inactive", "field": "lab_vendor_id", "lab_id": lab.id},
        )
    return lab


def apply_lab_rules(
    db: Session, payload: dict[str, Any], current: Appointment | None, *, tenant_id: int | None,
) -> dict[str, Any]:
    """Normalise + validate the lab block of an appointment write. Mutates and
    returns ``payload``. ``current`` is the stored row on PATCH, ``None`` on create."""
    touches_lab = "has_lab" in payload or any(f in payload for f in LAB_DETAIL_FIELDS)
    if not touches_lab:
        return payload

    stored_has_lab = bool(current.has_lab) if current is not None else False
    if "has_lab" in payload and payload["has_lab"] is not None:
        has_lab = bool(payload["has_lab"])
    else:
        has_lab = stored_has_lab
        # Derive: lab data on a non-lab row makes it a lab case.
        if not has_lab and any(
            f in payload and not _is_empty(f, payload[f]) for f in LAB_DETAIL_FIELDS
        ):
            has_lab = True
            payload["has_lab"] = True

    if not has_lab:
        # LAB-8: the un-tick clears everything below it, including values that
        # rode along in the same payload (the form's stale inputs).
        payload["has_lab"] = False
        payload.update(_cleared())
        return payload

    # Vendor must be one of the tenant's labs; "inactive" only blocks a move.
    if payload.get("lab_vendor_id") is not None:
        moved = current is None or current.lab_vendor_id != payload["lab_vendor_id"]
        _require_vendor(db, int(payload["lab_vendor_id"]), tenant_id, moved=moved)

    # LAB-9: date order on the merge, only when a date is being written.
    if any(f in payload for f in LAB_DATE_FIELDS):
        merged = {
            f: payload[f] if f in payload else (getattr(current, f, None) if current else None)
            for f in LAB_DATE_FIELDS
        }
        sent = merged["lab_sent_on"]
        if sent is not None:
            for field in ("lab_due_on", "lab_received_on"):
                other = merged[field]
                if other is not None and other < sent:
                    raise ValidationError(
                        f"{field} ({other}) is before lab_sent_on ({sent})",
                        details={"code": "lab_date_order", "field": field,
                                 "lab_sent_on": str(sent), field: str(other)},
                    )
    return payload


# ── read enrichment (AppointmentRead: lab_vendor_name + lab_status) ──────────
def vendor_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {lab.id: lab.name for lab in db.execute(select(Lab).where(Lab.id.in_(ids))).scalars()}


def enrich_appointments(db: Session, items, tenant_id=None) -> None:  # noqa: ANN001, ARG001
    rows = list(items)
    names = vendor_names(db, {r.lab_vendor_id for r in rows if getattr(r, "lab_vendor_id", None)})
    today = utc_today()
    for r in rows:
        r.lab_vendor_name = names.get(r.lab_vendor_id) if getattr(r, "lab_vendor_id", None) else None
        r.lab_status = (
            derive_lab_status(r.lab_sent_on, r.lab_due_on, r.lab_received_on, today)
            if r.has_lab else None
        )


# ── labs catalog ─────────────────────────────────────────────────────────────
def _norm_name(value: str | None) -> str:
    return " ".join((value or "").split()).lower()


def lab_name_matches(
    db: Session, tenant_id: int | None, name: str, *, exclude_id: int | None = None,
) -> list[Lab]:
    wanted = _norm_name(name)
    if not wanted:
        return []
    # DB pre-filter: whitespace runs as ``%`` so it can over-match, never miss.
    pattern = "%".join(_like(part) for part in wanted.split())
    stmt = select(Lab).where(Lab.is_active.is_(True), func.lower(Lab.name).like(pattern, escape="\\"))
    if tenant_id is not None:
        stmt = stmt.where(Lab.tenant_id == tenant_id)
    if exclude_id is not None:
        stmt = stmt.where(Lab.id != exclude_id)
    # The exact compare finishes in Python (whitespace runs collapse) so a
    # doubled space still collides with the single-spaced name.
    return [lab for lab in db.execute(stmt).scalars() if _norm_name(lab.name) == wanted]


class LabCRUD(CRUDBase[Lab]):
    """Create-only duplicate-name guard (INS-PT-13 shape). A rename onto a
    taken name is usually a deliberate merge, so PATCH is not guarded."""

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        allow = bool(payload.pop("allow_duplicate_name", False))
        payload["name"] = " ".join(str(payload.get("name") or "").split())
        if not payload["name"]:
            raise ValidationError("name is required", details={"code": "lab_name_required", "field": "name"})
        if not allow:
            matches = lab_name_matches(db, tenant_id, payload["name"])
            if matches:
                raise ConflictError(
                    f"An active lab named '{matches[0].name}' already exists",
                    details={
                        "code": "duplicate_lab_name",
                        "field": "name",
                        "matches": [{"id": m.id, "name": m.name, "office_id": m.office_id} for m in matches],
                        "override": "allow_duplicate_name",
                    },
                )
        return super().create(db, payload, tenant_id=tenant_id, created_by=created_by)

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        payload = dict(data)
        payload.pop("allow_duplicate_name", None)
        if "name" in payload and payload["name"] is not None:
            payload["name"] = " ".join(str(payload["name"]).split())
        return super().update(db, obj_id, payload, tenant_id=tenant_id, updated_by=updated_by)


# ── office-wide lab-case view (LAB-2 / LAB-5) ────────────────────────────────
def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _patient_name(p: Patient | None) -> str | None:
    if p is None:
        return None
    name = ", ".join(x for x in (p.last_name, p.first_name) if x)
    return name or p.chart_no or f"Patient {p.id}"


def _base_stmt(tenant_id: int):  # noqa: ANN202
    return (
        select(Appointment, Patient, Provider, Office, Lab)
        .join(Office, Office.id == Appointment.office_id)
        .outerjoin(Patient, Patient.id == Appointment.patient_id)
        .outerjoin(Provider, Provider.id == Appointment.provider_id)
        .outerjoin(Lab, Lab.id == Appointment.lab_vendor_id)
        .where(Office.tenant_id == tenant_id, Appointment.has_lab.is_(True))
    )


def _apply_filters(  # noqa: PLR0913
    stmt, *, office_id=None, patient_id=None, provider_id=None, lab_vendor_id=None,  # noqa: ANN001
    short_notice=None, date_from=None, date_to=None, lab_sent_from=None, lab_sent_to=None,
    lab_due_from=None, lab_due_to=None, lab_received_from=None, lab_received_to=None,
    include_archived=False, search=None,
):
    if not include_archived:  # LAB-11: tombstones stay out unless asked for
        stmt = stmt.where(Appointment.is_archived.is_(False))
    if office_id is not None:
        stmt = stmt.where(Appointment.office_id == office_id)
    if patient_id is not None:
        stmt = stmt.where(Appointment.patient_id == patient_id)
    if provider_id is not None:
        stmt = stmt.where(Appointment.provider_id == provider_id)
    if lab_vendor_id is not None:
        stmt = stmt.where(Appointment.lab_vendor_id == lab_vendor_id)
    if short_notice is not None:
        stmt = stmt.where(Appointment.lab_short_notice.is_(bool(short_notice)))
    for column, lo, hi in (
        (Appointment.date, date_from, date_to),
        (Appointment.lab_sent_on, lab_sent_from, lab_sent_to),
        (Appointment.lab_due_on, lab_due_from, lab_due_to),
        (Appointment.lab_received_on, lab_received_from, lab_received_to),
    ):
        if lo is not None:
            stmt = stmt.where(column >= lo)
        if hi is not None:
            stmt = stmt.where(column <= hi)
    term = (search or "").strip()
    if term:
        like = f"%{_like(term)}%"
        stmt = stmt.where(or_(
            Patient.last_name.ilike(like, escape="\\"),
            Patient.first_name.ilike(like, escape="\\"),
            Patient.chart_no.ilike(like, escape="\\"),
            Appointment.procedure_label.ilike(like, escape="\\"),
            Appointment.lab_dds.ilike(like, escape="\\"),
            Lab.name.ilike(like, escape="\\"),
            Appointment.id.ilike(like, escape="\\"),
            cast(Appointment.patient_id, String).ilike(like, escape="\\"),
        ))
    return stmt


_SORT_COLUMNS = {
    "date": (Appointment.date, Appointment.start_time),
    "lab_sent_on": (Appointment.lab_sent_on,),
    "lab_due_on": (Appointment.lab_due_on,),
    "lab_received_on": (Appointment.lab_received_on,),
    "lab_cost": (Appointment.lab_cost,),
    "patient_name": (Patient.last_name, Patient.first_name),
    "provider_name": (Provider.name,),
    "lab_vendor_name": (Lab.name,),
    "created_at": (Appointment.created_at,),
    "updated_at": (Appointment.updated_at,),
}


def _row(appt: Appointment, patient, provider, office, lab, today: date) -> dict:  # noqa: ANN001
    status = derive_lab_status(appt.lab_sent_on, appt.lab_due_on, appt.lab_received_on, today)
    days_overdue = None
    if status in ("sent", "overdue") and appt.lab_due_on is not None:
        days_overdue = (today - appt.lab_due_on).days
    return {
        "id": appt.id,
        "office_id": appt.office_id,
        "office_name": office.name if office else None,
        "patient_id": appt.patient_id,
        "patient_name": _patient_name(patient),
        "chart_no": patient.chart_no if patient else None,
        "patient_phone": (patient.cell_phone or patient.phone) if patient else None,
        "provider_id": appt.provider_id,
        "provider_name": provider.name if provider else None,
        "date": appt.date,
        "start_time": appt.start_time,
        "status": appt.status,
        "is_archived": bool(appt.is_archived),
        "procedure_label": appt.procedure_label,
        "lab_vendor_id": appt.lab_vendor_id,
        "lab_vendor_name": lab.name if lab else None,
        "lab_dds": appt.lab_dds,
        "lab_cost": appt.lab_cost,
        "lab_short_notice": bool(appt.lab_short_notice),
        "lab_sent_on": appt.lab_sent_on,
        "lab_due_on": appt.lab_due_on,
        "lab_received_on": appt.lab_received_on,
        "lab_status": status,
        "days_overdue": days_overdue,
        "updated_at": appt.updated_at,
    }


def list_lab_cases(  # noqa: PLR0913
    db: Session, tenant_id: int, *, lab_status: str | None = None, page: int = 1, size: int = 50,
    sort: str | None = None, order: str = "desc", as_of: date | None = None, **filters: Any,
) -> dict:
    """Denormalised lab cases + per-status counts + total cost, server-paged.

    ``counts`` / ``total_cost`` are computed over every filter **except**
    ``lab_status`` (and ``total_cost`` over the selected status too), so the
    review tabs keep their badges while one tab is selected.
    """
    today = as_of or resolve_as_of(db, filters.get("office_id"))
    if lab_status is not None and lab_status not in LAB_STATUS_FILTERS:
        lab_status_clause(lab_status, today)  # raises the 422

    base = _apply_filters(_base_stmt(tenant_id), **filters)

    # One aggregate over the un-statused id set: counts per status + costs.
    status_expr = _status_case(today)
    id_sub = base.with_only_columns(Appointment.id).subquery()
    agg_stmt = (
        select(
            func.count(Appointment.id),
            func.coalesce(func.sum(Appointment.lab_cost), 0),
            *[func.sum(case((status_expr == s, 1), else_=0)) for s in LAB_STATUSES],
        )
        .select_from(Appointment)
        .where(Appointment.id.in_(select(id_sub.c.id)))
    )
    total_all, cost_all, n_not_sent, n_sent, n_overdue, n_received = db.execute(agg_stmt).one()
    counts = {
        "all": int(total_all or 0),
        "not_sent": int(n_not_sent or 0),
        "sent": int(n_sent or 0),
        "overdue": int(n_overdue or 0),
        "received": int(n_received or 0),
    }
    counts["not_received"] = counts["sent"] + counts["overdue"]

    stmt = base
    if lab_status is not None:
        stmt = stmt.where(lab_status_clause(lab_status, today))
        total_cost = db.execute(
            select(func.coalesce(func.sum(Appointment.lab_cost), 0))
            .select_from(Appointment)
            .where(Appointment.id.in_(select(stmt.with_only_columns(Appointment.id).subquery().c.id)))
        ).scalar_one()
        total = counts.get(lab_status, 0)
    else:
        total_cost = cost_all
        total = counts["all"]

    sort_key = sort if sort in _SORT_COLUMNS else "date"
    columns = _SORT_COLUMNS[sort_key]
    order_by = [c.desc() if order == "desc" else c.asc() for c in columns]
    order_by.append(Appointment.id.asc())
    records = db.execute(
        stmt.order_by(*order_by).offset((page - 1) * size).limit(size)
    ).all()
    items = [_row(a, p, pr, o, lab, today) for a, p, pr, o, lab in records]
    pages = (total + size - 1) // size if size else 0
    return {
        "items": items,
        "meta": {"page": page, "size": size, "total": total, "pages": pages},
        "counts": counts,
        "total_cost": Decimal(str(total_cost or 0)),
        "as_of": today,
    }


def all_lab_cases(db: Session, tenant_id: int, *, lab_status: str | None = None,
                  as_of: date | None = None, sort: str | None = None, order: str = "desc",
                  **filters: Any) -> list[dict]:
    """Every matching case, unpaged (the PDF / CSV exports)."""
    today = as_of or resolve_as_of(db, filters.get("office_id"))
    stmt = _apply_filters(_base_stmt(tenant_id), **filters)
    if lab_status is not None:
        stmt = stmt.where(lab_status_clause(lab_status, today))
    sort_key = sort if sort in _SORT_COLUMNS else "date"
    columns = _SORT_COLUMNS[sort_key]
    order_by = [c.desc() if order == "desc" else c.asc() for c in columns]
    order_by.append(Appointment.id.asc())
    return [_row(a, p, pr, o, lab, today) for a, p, pr, o, lab in db.execute(stmt.order_by(*order_by)).all()]


# ── LAB-4: Lab Cost Report ───────────────────────────────────────────────────
_BASIS_COLUMN = {
    "appointment": Appointment.date,
    "sent": Appointment.lab_sent_on,
    "due": Appointment.lab_due_on,
    "received": Appointment.lab_received_on,
}


def lab_cost_report(  # noqa: PLR0913
    db: Session, tenant_id: int, *, date_from: date | None, date_to: date | None,
    date_basis: str = "appointment", group_by: str = "vendor", office_id: int | None = None,
    provider_id: str | None = None, lab_vendor_id: int | None = None,
    include_archived: bool = False,
) -> dict:
    if date_basis not in COST_REPORT_DATE_BASIS:
        raise ValidationError("Unknown date_basis", details={"code": "invalid_date_basis", "field": "date_basis",
                                                             "allowed": list(COST_REPORT_DATE_BASIS)})
    if group_by not in COST_REPORT_GROUPS:
        raise ValidationError("Unknown group_by", details={"code": "invalid_group_by", "field": "group_by",
                                                           "allowed": list(COST_REPORT_GROUPS)})
    basis = _BASIS_COLUMN[date_basis]
    stmt = (
        select(Appointment, Provider, Office, Lab)
        .join(Office, Office.id == Appointment.office_id)
        .outerjoin(Provider, Provider.id == Appointment.provider_id)
        .outerjoin(Lab, Lab.id == Appointment.lab_vendor_id)
        .where(Office.tenant_id == tenant_id, Appointment.has_lab.is_(True))
    )
    if not include_archived:
        stmt = stmt.where(Appointment.is_archived.is_(False))
    if date_from is not None:
        stmt = stmt.where(basis >= date_from)
    if date_to is not None:
        stmt = stmt.where(basis <= date_to)
    if date_basis != "appointment":
        stmt = stmt.where(basis.is_not(None))
    if office_id is not None:
        stmt = stmt.where(Appointment.office_id == office_id)
    if provider_id is not None:
        stmt = stmt.where(Appointment.provider_id == provider_id)
    if lab_vendor_id is not None:
        stmt = stmt.where(Appointment.lab_vendor_id == lab_vendor_id)

    buckets: dict[str | None, dict] = {}
    grand = Decimal("0")
    n = 0
    for appt, provider, office, lab in db.execute(stmt).all():
        if group_by == "vendor":
            key, label = (str(lab.id) if lab else None), (lab.name if lab else "(no lab)")
        elif group_by == "provider":
            key, label = appt.provider_id, (provider.name if provider else appt.provider_id or "(no provider)")
        elif group_by == "office":
            key, label = str(appt.office_id), office.name
        elif group_by == "dds":
            key = (appt.lab_dds or "").strip() or None
            label = key or "(no DDS)"
        else:  # month, on the basis date
            d = getattr(appt, basis.key)
            key = d.strftime("%Y-%m") if d else None
            label = d.strftime("%b %Y") if d else "(undated)"
        b = buckets.setdefault(key, {"key": key, "label": label, "case_count": 0, "total_cost": Decimal("0")})
        cost = Decimal(str(appt.lab_cost or 0))
        b["case_count"] += 1
        b["total_cost"] += cost
        grand += cost
        n += 1
    rows = sorted(buckets.values(), key=lambda r: (r["key"] is None, str(r["label"]).lower()))
    return {
        "date_from": date_from, "date_to": date_to, "date_basis": date_basis, "group_by": group_by,
        "rows": rows, "case_count": n, "total_cost": grand,
    }


# ── exports (LAB-4) ──────────────────────────────────────────────────────────
CSV_COLUMNS = (
    "id", "office_name", "patient_id", "patient_name", "chart_no", "provider_name", "date",
    "start_time", "procedure_label", "lab_vendor_name", "lab_dds", "lab_cost", "lab_short_notice",
    "lab_sent_on", "lab_due_on", "lab_received_on", "lab_status", "days_overdue",
)


def lab_cases_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in rows:
        writer.writerow(["" if r.get(c) is None else r.get(c) for c in CSV_COLUMNS])
    return buf.getvalue()


def _office_header(db: Session, tenant_id: int, office_id: int | None, title: str, extra: list) -> Any:  # noqa: ANN401
    from app.services.pdf_report import ReportHeader  # noqa: PLC0415 - reportlab is lazy

    office = db.get(Office, office_id) if office_id is not None else None
    if office is not None and office.tenant_id != tenant_id:
        office = None
    address = None
    phone = None
    name = "All offices"
    if office is not None:
        name = office.name
        parts = [office.address_line1, office.address_line2,
                 ", ".join(x for x in (office.city, office.state) if x), office.zip]
        address = " ".join(p for p in parts if p) or None
        phone = office.phone
    return ReportHeader(title=title, office_name=name, office_address=address, office_phone=phone,
                        extra=extra, show_patient=False)


def render_lab_report_pdf(  # noqa: PLR0913
    db: Session, tenant_id: int, rows: list[dict], *, office_id: int | None, lab_status: str | None,
    date_from: date | None, date_to: date | None, as_of: date,
) -> bytes:
    """The legacy Lab Report (Not Sent / Not Received / Due / Received)."""
    from app.services import pdf_report  # noqa: PLC0415

    extra = [("Report", LAB_STATUS_LABELS.get(lab_status or "", "All lab cases"))]
    if date_from or date_to:
        extra.append(("Appointment dates", f"{pdf_report.fmt_date(date_from)} - {pdf_report.fmt_date(date_to)}"))
    extra.append(("As of", pdf_report.fmt_date(as_of)))
    report = pdf_report.PatientReport(
        _office_header(db, tenant_id, office_id, "Lab Report", extra), landscape=True,
    )
    report.section_title(f"Lab cases ({len(rows)})")
    body = []
    total = Decimal("0")
    for r in rows:
        total += Decimal(str(r["lab_cost"] or 0))
        body.append([
            pdf_report.cell(r["patient_name"]), pdf_report.cell(r["patient_id"]),
            pdf_report.fmt_date(r["date"]), pdf_report.cell(r["provider_name"]),
            pdf_report.cell(r["procedure_label"]), pdf_report.cell(r["lab_vendor_name"]),
            pdf_report.cell(r["lab_dds"]), "Yes" if r["lab_short_notice"] else "",
            pdf_report.fmt_date(r["lab_sent_on"]), pdf_report.fmt_date(r["lab_due_on"]),
            pdf_report.fmt_date(r["lab_received_on"]), LAB_STATUS_LABELS[r["lab_status"]],
            pdf_report.money(r["lab_cost"]),
        ])
    report.data_table(
        ["Patient", "ID", "Appt Date", "Provider", "Description", "Lab", "DDS", "Short",
         "Sent On", "Due On", "Recvd On", "Status", "Cost"],
        body, right=(12,), center=(7,),
        foot=["Total", "", "", "", "", "", "", "", "", "", "", "", pdf_report.money(total)],
        foot_span=12, empty="No lab cases match the selected filters.",
    )
    return report.render()


def render_lab_cost_report_pdf(db: Session, tenant_id: int, data: dict, *, office_id: int | None) -> bytes:
    from app.services import pdf_report  # noqa: PLC0415

    extra = [
        ("Period", f"{pdf_report.fmt_date(data['date_from'])} - {pdf_report.fmt_date(data['date_to'])}"
                   f" ({data['date_basis']} date)"),
        ("Grouped by", data["group_by"]),
    ]
    report = pdf_report.PatientReport(_office_header(db, tenant_id, office_id, "Lab Cost Report", extra))
    report.section_title("Lab cost by " + data["group_by"])
    body = [[pdf_report.cell(r["label"]), str(r["case_count"]), pdf_report.money(r["total_cost"])]
            for r in data["rows"]]
    report.data_table(
        [data["group_by"].capitalize(), "Cases", "Total cost"], body, right=(1, 2),
        foot=["Total", str(data["case_count"]), pdf_report.money(data["total_cost"])],
        empty="No lab cases in the selected period.",
    )
    return report.render()


# ── published rule table (GET /metadata/lab-tracking-rules) ──────────────────
def lab_tracking_rules() -> dict:
    return {
        "model": "A lab case is an appointment with has_lab=true; there is no lab-case resource.",
        "fields": {
            "has_lab": "the switch",
            "lab_vendor_id": "FK -> /labs (the lab company); lab_vendor_name is denormalised on reads",
            "lab_dds": f"the dentist the case is for (free text, max {LAB_DDS_MAX_LENGTH}) - NOT the vendor",
            "lab_cost": f">= 0, max_digits={LAB_COST_MAX_DIGITS}, decimal_places={LAB_COST_DECIMAL_PLACES}",
            "lab_short_notice": "bool, default false",
            "lab_sent_on / lab_due_on / lab_received_on": "dates",
        },
        "statuses": list(LAB_STATUSES),
        "status_filters": list(LAB_STATUS_FILTERS),
        "status_derivation": {
            "received": "lab_received_on is set",
            "overdue": "lab_sent_on set, lab_received_on null, lab_due_on < today",
            "sent": "lab_sent_on set, lab_received_on null, lab_due_on null or >= today",
            "not_sent": "otherwise",
            "not_received": "sent OR overdue (legacy Lab Report filter)",
            "today": "the office's local date when office_id is given (lab-cases view), else UTC",
        },
        "implications": [
            {"when": "has_lab = false", "then": "lab_vendor_id/lab_dds/lab_cost/lab_sent_on/lab_due_on/"
                                              "lab_received_on -> null, lab_short_notice -> false "
                                              "(values in the same payload are cleared too)"},
            {"when": "any lab detail is sent on a has_lab=false row without has_lab in the payload",
             "then": "has_lab -> true"},
        ],
        "errors": {
            "lab_date_order": "422 - lab_due_on or lab_received_on is before lab_sent_on (merge of payload + stored)",
            "lab_vendor_not_found": "422 - lab_vendor_id is not one of this tenant's labs",
            "lab_vendor_inactive": "422 - lab_vendor_id moved onto an inactive lab",
            "duplicate_lab_name": "409 - POST /labs with an active lab of the same name (allow_duplicate_name overrides)",
            "extra_forbidden": "422 - an unknown key on AppointmentCreate/Update (LAB-10)",
        },
        "list_filters": {
            "/appointments": ["has_lab", "lab_vendor_id", "lab_short_notice", "lab_status",
                              "lab_sent_on_from/_to", "lab_due_on_from/_to", "lab_received_on_from/_to"],
            "/appointments/lab-cases": ["office_id", "patient_id", "provider_id", "lab_vendor_id",
                                        "lab_short_notice", "lab_status", "date_from/_to",
                                        "lab_sent_from/_to", "lab_due_from/_to", "lab_received_from/_to",
                                        "include_archived", "search", "sort", "order", "page", "size"],
        },
        "lab_case_sorts": list(LAB_CASE_SORTS),
        "cost_report": {"group_by": list(COST_REPORT_GROUPS), "date_basis": list(COST_REPORT_DATE_BASIS)},
        "archived": "DELETE /appointments/{id} is a soft archive; archived rows are excluded from "
                    "GET /appointments and /appointments/lab-cases by default (?is_archived=true / "
                    "?include_archived=true opt back in)",
    }
