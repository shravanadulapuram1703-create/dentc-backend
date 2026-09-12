"""Server-rendered patient reports — Overview · Ledger · Transactions · Insurance
(PRINT-1..10 of docs/print/patient_print_backend_devreport.md).

Until now every Print button rebuilt its report in the browser from whatever the
screen had loaded, so a print could only ever contain what the browser held
(the 500-row ledger cap, the 25-member roster cap), the layout lived in four
``*Print.ts`` files, nothing recorded who printed what, and a print could not be
produced without opening the screen. These four renderers compose each report
from the canonical data — the same services the screens read — and hand it to
``pdf_report`` (the reportlab twin of the FE's ``patientPdf.ts``), so a server
PDF lays out like the client one and the FE builders can collapse to
``window.open(url)``.

* Section titles and column headers are the legacy names the ``*Print.ts``
  files carry, in the same order, so the printed page is recognisable.
* ``resolve_letterhead`` is the one place that decides which logo / name /
  address prints for an office (PRINT-2) — the same resolution ``OfficeRead``
  publishes, so the screen header and the printed header agree.
* Every print writes an ``audit_logs`` row (``action='PRINT'``) — the legacy
  server reports audited who printed what, and ``AuditMiddleware`` only records
  mutations.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datetimes import office_today
from app.core.exceptions import NotFoundError
from app.core.logging import client_ip_ctx, get_logger, request_id_ctx
from app.db.models import (
    AccountSettings,
    Appointment,
    AuditLog,
    Definition,
    Employer,
    FeeSchedule,
    InsuranceCarrier,
    InsurancePlan,
    InsuranceSubscriber,
    Office,
    OfficeStatementSettings,
    Operatory,
    OrthoPlan,
    Patient,
    PatientDocument,
    PatientInsurance,
    PatientPaymentPlan,
    PatientProcedure,
    PatientRecall,
    PatientRefund,
    PatientRegPlan,
    PerioExam,
    Provider,
    Referral,
)
from app.services import (
    account_scope,
    balance_service,
    estimate_service,
    insurance_service,
    ledger_service,
    medical_alert_summary_service,
    patient_intake_service,
    patient_overview_service,
)
from app.services.pdf_report import (
    PatientReport,
    ReportHeader,
    age_from_dob,
    cell,
    fmt_date,
    fmt_time,
    money,
    money_or_dash,
    sex_letter,
    sex_word,
)

logger = get_logger(__name__)

REPORT_KINDS = ("overview", "ledger", "transactions", "insurance")

# Legacy Overview "Contact Pref" labels (format.ts contact_pref_label).
_CONTACT_PREF = {
    "home_phone": "Home Phone", "cell_phone": "Cell Phone", "work_phone": "Work Phone",
    "email": "Email", "text": "Text", "mail": "Mail",
}
# ``referral_type`` is a legacy code: "0" = Referred By, "1" = Referred To.
_REFERRAL_DIRECTION = {"0": "Referred By", "1": "Referred To"}

_ZERO = Decimal("0")


# ── small helpers ─────────────────────────────────────────────────────────────
def _f(value: Any) -> float:  # noqa: ANN401
    return float(value or 0)


def _patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    return account_scope.load_patient(db, patient_id, tenant_id)


def display_name(p: Any) -> str:  # noqa: ANN401
    """``Last, First M (Preferred)`` as the legacy header renders it."""
    if p is None:
        return "-"
    # GAP-AP-19: the full middle name when the record has one, else the initial.
    middle = getattr(p, "middle_name", None) or getattr(p, "middle_initial", None) or ""
    given = " ".join(
        v.strip() for v in ((getattr(p, "first_name", None) or ""), middle)
        if v and v.strip()
    )
    last = (getattr(p, "last_name", None) or "").strip()
    base = ", ".join(x for x in (last, given) if x)
    if not base:
        return "-"
    preferred = getattr(p, "preferred_name", None)
    return f"{base} ({preferred})" if preferred else base


def _last_first(last: str | None, first: str | None) -> str:
    return ", ".join(x for x in (last, first) if x) or "-"


def _join(*parts: str | None, sep: str = ", ") -> str:
    return sep.join(p.strip() for p in parts if p and p.strip())


def _address_line(a1: str | None, a2: str | None, city: str | None, state: str | None, zip_: str | None) -> str | None:
    street = _join(a1, a2)
    locality = _join(_join(city, state), zip_, sep=" ")
    line = " · ".join(x for x in (street, locality) if x)
    return line or None


def _labels(db: Session, tenant_id: int, group_code: str) -> dict[str, str]:
    """``definitions`` key1 → description for one dropdown group."""
    rows = db.execute(
        select(Definition.key1, Definition.description).where(
            Definition.tenant_id == tenant_id, Definition.group_code == group_code,
        )
    ).all()
    return {str(k).strip(): d for k, d in rows if k is not None}


def _label(labels: dict[str, str], code: str | None) -> str:
    if not code:
        return "-"
    return labels.get(str(code).strip(), str(code))


def _provider_names(db: Session, ids: set) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {p.id: (p.name or _last_first(p.last_name, p.first_name)) for p in db.execute(
        select(Provider).where(Provider.id.in_(ids))).scalars()}


def _office_map(db: Session, tenant_id: int) -> dict[int, Office]:
    return {o.id: o for o in db.execute(select(Office).where(Office.tenant_id == tenant_id)).scalars()}


def _office_code(office: Office | None) -> str:
    if office is None:
        return "-"
    return office.short_id or office.office_code or office.name or "-"


def _local_path(url_or_path: str | None) -> str | None:
    """A ``/uploads/<sub>/<file>`` url (or a bare relative path) → the file on
    disk under ``UPLOAD_DIR``, only when it exists. Anything remote → None."""
    if not url_or_path:
        return None
    text = str(url_or_path)
    if text.startswith(("http://", "https://", "gs://")):
        return None
    base = settings.UPLOAD_URL_BASE.rstrip("/")
    rel = text[len(base):] if base and text.startswith(base) else text
    candidate = Path(settings.UPLOAD_DIR) / rel.lstrip("/\\")
    return str(candidate) if candidate.is_file() else None


# ── PRINT-2: letterhead resolution (shared by the PDFs and OfficeRead) ────────
def resolve_letterhead(db: Session, office: Office | None, tenant_id: int) -> dict[str, Any]:
    """Which name / address / phone / logo print for this office.

    ``office_statement_settings`` (Setup → Office → Statement) already lets an
    office choose ``logo_option`` = office (the practice logo from
    ``account_settings.logo_url``) | custom (its own upload) | none, and
    ``address_source`` = office | custom (the statement address block). That is
    the practice's stated print branding, so it drives every report header —
    not only statements. A blank custom field falls back to the office row.
    """
    stmt_row = None
    if office is not None:
        stmt_row = db.execute(
            select(OfficeStatementSettings).where(
                OfficeStatementSettings.office_id == office.id,
                OfficeStatementSettings.tenant_id == tenant_id,
            )
        ).scalar_one_or_none()
    account = db.execute(
        select(AccountSettings).where(AccountSettings.tenant_id == tenant_id)
    ).scalar_one_or_none()

    logo_option = (stmt_row.logo_option if stmt_row and stmt_row.logo_option else "office").lower()
    logo_url: str | None = None
    logo_source = "none"
    if logo_option == "custom" and stmt_row and stmt_row.logo_url:
        logo_url, logo_source = stmt_row.logo_url, "office"
    elif logo_option != "none" and account is not None and account.logo_url:
        logo_url, logo_source = account.logo_url, "tenant"

    custom_address = bool(stmt_row and (stmt_row.address_source or "office").lower() == "custom")
    pick = (lambda custom, base: (custom or base)) if custom_address else (lambda custom, base: base)  # noqa: E731
    o = office
    return {
        "name": (stmt_row.correspondence_name if stmt_row and stmt_row.correspondence_name else None)
        or (o.name if o else None),
        "address_line1": pick(stmt_row.statement_address_1 if stmt_row else None, o.address_line1 if o else None),
        "address_line2": pick(stmt_row.statement_address_2 if stmt_row else None, o.address_line2 if o else None),
        "city": pick(stmt_row.statement_city if stmt_row else None, o.city if o else None),
        "state": pick(stmt_row.statement_state if stmt_row else None, o.state if o else None),
        "zip": pick(stmt_row.statement_zip if stmt_row else None, o.zip if o else None),
        "phone": pick(stmt_row.statement_phone if stmt_row else None, (o.phone or o.phone_2) if o else None),
        "logo_url": logo_url,
        "logo_source": logo_source,
        "logo_path": _local_path(logo_url),
    }


def _header(
    db: Session, patient: Patient, office: Office | None, tenant_id: int, *,
    title: str, extra: list[tuple[str, str]] | None = None, photo: bool = False,
) -> ReportHeader:
    lh = resolve_letterhead(db, office, tenant_id)
    printed = datetime.now(timezone.utc)
    if office is not None:
        try:
            from zoneinfo import ZoneInfo  # noqa: PLC0415

            printed = printed.astimezone(ZoneInfo(office.timezone or "America/New_York"))
        except Exception:  # noqa: BLE001 - an unknown zone prints in UTC
            pass
    return ReportHeader(
        title=title,
        office_name=lh["name"] or "Dental Practice",
        office_address=_address_line(lh["address_line1"], lh["address_line2"], lh["city"], lh["state"], lh["zip"]),
        office_phone=lh["phone"],
        patient_name=display_name(patient),
        patient_id=patient.id,
        chart_no=patient.chart_no,
        dob=fmt_date(patient.dob) if patient.dob else None,
        extra=extra or [],
        logo_path=lh["logo_path"],
        photo_path=_photo_path(db, patient) if photo else None,
        printed_at=printed.strftime("%m/%d/%Y %I:%M %p"),
    )


def _photo_path(db: Session, patient: Patient) -> str | None:
    """PRINT-10: the patient photo (``patients.photo_document_id``, PO-10) when
    it is a locally stored image. A bucket-stored photo is skipped rather than
    fetched — a header decoration must not add a network round trip."""
    if not patient.photo_document_id:
        return None
    doc = db.get(PatientDocument, patient.photo_document_id)
    if doc is None or doc.is_deleted or doc.patient_id != patient.id:
        return None
    if (doc.storage_backend or "local") != "local":
        return None
    if not (doc.content_type or "").lower().startswith("image/"):
        return None
    candidate = Path(settings.UPLOAD_DIR) / (doc.storage_path or doc.file_path)
    return str(candidate) if candidate.is_file() else None


def _home_office(db: Session, patient: Patient) -> Office | None:
    return db.get(Office, patient.home_office_id) if patient.home_office_id else None


# ── audit ─────────────────────────────────────────────────────────────────────
def record_print(
    db: Session, *, tenant_id: int, user_id: int | None, patient_id: int | None,
    report: str, path: str, params: dict[str, Any] | None = None,
    resource_type: str = "patient_report",
) -> None:
    """One ``audit_logs`` row per print (``action='PRINT'``). Exception-safe —
    a failed audit write must never withhold the report."""
    try:
        db.add(AuditLog(
            tenant_id=tenant_id, user_id=user_id, action="PRINT",
            resource_type=resource_type, resource_id=report, patient_id=patient_id,
            method="GET", path=path[:500], status_code=200,
            ip_address=client_ip_ctx.get(), request_id=request_id_ctx.get(),
            details={"report": report, "params": {k: str(v) for k, v in (params or {}).items() if v is not None}},
        ))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("Failed to record print audit for patient %s/%s: %s", patient_id, report, exc)


# ── insurance slots (shared by Overview + Insurance Details) ──────────────────
def _insurance_slots(db: Session, patient_id: int, *, active_only: bool = True) -> list[dict]:
    stmt = (
        select(PatientInsurance, InsurancePlan, InsuranceCarrier, InsuranceSubscriber, Employer)
        .outerjoin(InsurancePlan, InsurancePlan.id == PatientInsurance.ins_plan_id)
        .outerjoin(InsuranceCarrier, InsuranceCarrier.id == InsurancePlan.carrier_id)
        .outerjoin(InsuranceSubscriber, InsuranceSubscriber.id == PatientInsurance.subscriber_id)
        .outerjoin(Employer, Employer.id == InsurancePlan.employer_id)
        .where(PatientInsurance.patient_id == patient_id)
    )
    if active_only:
        stmt = stmt.where(PatientInsurance.is_active.is_(True))
    out = []
    for rec, plan, carrier, sub, employer in db.execute(stmt.order_by(PatientInsurance.id)).all():
        out.append({"record": rec, "plan": plan, "carrier": carrier, "subscriber": sub, "employer": employer})
    return out


def _slot_category(slot: dict) -> str:
    return (slot["record"].legacy_plan_type or "").strip().upper()[:1]


def _slot_order(slot: dict) -> str:
    return (slot["record"].insurance_type or "").strip().lower()


def _pick_slot(slots: list[dict], category: str, order: str) -> dict | None:
    """The FE's ``insurance_slots`` rule: category from ``legacy_plan_type``
    (``D``/``M``), order from ``insurance_type``; a category with no explicitly
    ranked slot falls back to positional order."""
    same = [s for s in slots if _slot_category(s) == category]
    exact = next((s for s in same if _slot_order(s) == order), None)
    if exact is not None:
        return exact
    fallback = {"primary": 0, "secondary": 1, "tertiary": 2, "quaternary": 3}.get(order, 0)
    return same[fallback] if len(same) > fallback else None


def _slot_subscriber_line(slot: dict | None) -> str:
    if not slot:
        return "-"
    sub = slot["subscriber"]
    who = _last_first(sub.sub_last_name, sub.sub_first_name) if sub else "-"
    rel = slot["record"].relationship
    if who == "-":
        return f"({rel})" if rel else "-"
    return f"{who} ({rel})" if rel else who


# ── 1. Patient Overview ───────────────────────────────────────────────────────
def render_overview(db: Session, patient_id: int, tenant_id: int) -> bytes:
    patient = _patient(db, patient_id, tenant_id)
    office = _home_office(db, patient)
    offices = _office_map(db, tenant_id)
    today = office_today(office.timezone if office else None)

    report = PatientReport(_header(
        db, patient, office, tenant_id, title="Patient Overview",
        extra=[("PGID / OID", f"{patient.id} / {patient.home_office_id or '-'}")], photo=True,
    ))

    pattype = _labels(db, tenant_id, "PATTYPE")
    reftype = _labels(db, tenant_id, "REFTYPE")
    rptype = _labels(db, tenant_id, "RPTYPE")

    # ---- Patient Information ------------------------------------------------
    last_visit, next_visit = patient_intake_service._visits(db, patient.id, today)
    providers = _provider_names(db, {patient.preferred_provider_id, patient.preferred_hygienist_id})
    last_perio = db.execute(
        select(func.max(PerioExam.exam_date)).where(
            PerioExam.patient_id == patient.id, PerioExam.is_voided.is_(False))
    ).scalar_one()
    fee_schedule = db.get(FeeSchedule, patient.fee_schedule_id) if patient.fee_schedule_id else None
    alerts = medical_alert_summary_service.summarize_one(db, tenant_id, patient.id)
    alert_text = "; ".join(
        " — ".join(x for x in (a.get("label"), a.get("comments")) if x) for a in alerts.get("alerts", [])
    )

    report.section_title("Patient Information")
    report.key_value_table([
        ["Name", display_name(patient), "Age / Sex", f"{age_from_dob(patient.dob, today) if patient.dob else '-'} / {sex_word(patient.gender)}"],
        ["Date of Birth", fmt_date(patient.dob), "Cell", cell(patient.cell_phone)],
        ["ID", str(patient.id), "Email", cell(patient.email)],
        ["Legacy ID", cell(patient.legacy_id), "Chart", cell(patient.chart_no)],
        ["Next Visit", fmt_date(next_visit), "Next Recall", fmt_date(patient.next_recall)],
        ["Last Visit", fmt_date(last_visit or patient.last_visit), "First Visit", fmt_date(patient.first_visit)],
        ["Provider", cell(providers.get(patient.preferred_provider_id)), "Referral Type", _label(reftype, patient.referral_type)],
        ["Hygienist", cell(providers.get(patient.preferred_hygienist_id)), "Referred By", cell(patient.referred_by)],
        ["Home Office", office.name if office else "-", "Referred To", cell(patient.referred_to)],
        ["Last Perio Chart", fmt_date(last_perio), "Contact Pref",
         _CONTACT_PREF.get((patient.preferred_contact or "").strip().lower(), cell(patient.preferred_contact))],
        ["Home", cell(patient.phone), "Work", cell(patient.work_phone)],
        ["Fee Schedule", fee_schedule.name if fee_schedule else (f"#{patient.fee_schedule_id}" if patient.fee_schedule_id else "-"),
         "Type", _label(pattype, patient.patient_type)],
        ["Address", cell(_join(patient.address_line1, patient.address_line2)), "Preferred Language", cell(patient.preferred_language)],
        ["City, State and Zip", cell(_join(_join(patient.city, patient.state), patient.zip, sep=" ")),
         "Active", "No" if patient.is_active is False else "Yes"],
    ])
    report.paragraph("Patient Note", patient.patient_notes)
    report.paragraph("Medical Alerts", alert_text, red=True)

    # ---- Responsible Party --------------------------------------------------
    rp = patient_overview_service.resolve_responsible_party(db, tenant_id, patient.responsible_party_id)
    legacy_rp = (rp.legacy_id if rp and rp.legacy_id else None) or (patient.responsible_party_id or "")
    report.section_title("Responsible Party")
    report.key_value_table([
        ["Name", _last_first(rp.last_name, rp.first_name) if rp else _last_first(patient.last_name, patient.first_name),
         "Cell", cell((rp.cell_phone if rp else None) or patient.cell_phone)],
        ["Resp ID", f"{rp.id if rp else '-'}{f' (Legacy ID {legacy_rp})' if legacy_rp else ''}",
         "Email", cell((rp.email if rp else None) or patient.email)],
        ["Type", _label(rptype, rp.resp_party_type) if rp and rp.resp_party_type else _label(pattype, patient.patient_type),
         "Home Office", office.name if office else "-"],
    ])

    # ---- Insurance ----------------------------------------------------------
    slots = _insurance_slots(db, patient.id)
    four = [_pick_slot(slots, "D", "primary"), _pick_slot(slots, "D", "secondary"),
            _pick_slot(slots, "M", "primary"), _pick_slot(slots, "M", "secondary")]

    def _slot_value(slot: dict | None, key: str) -> str:
        if not slot:
            return "-"
        rec, plan, carrier, sub = slot["record"], slot["plan"], slot["carrier"], slot["subscriber"]
        if key == "carrier":
            return cell(carrier.name if carrier else None)
        if key == "group":
            return cell((plan.group_number if plan else None) or (sub.group_number if sub else None))
        if key == "phone":
            return cell(carrier.phone if carrier else None)
        if key == "subscriber":
            return _slot_subscriber_line(slot)
        if key == "max":
            v = rec.max_remaining if rec.max_remaining is not None else (plan.individual_max if plan else None)
            return money_or_dash(v)
        if key == "ded":
            v = rec.deductible_remaining if rec.deductible_remaining is not None else (plan.individual_deductible if plan else None)
            return money_or_dash(v)
        return "-"

    report.section_title("Insurance")
    report.data_table(
        ["", "Dental Primary", "Dental Secondary", "Medical Primary", "Medical Secondary"],
        [[label, *[_slot_value(s, key) for s in four]] for label, key in (
            ("Carrier Name", "carrier"), ("Group #", "group"), ("Carrier Phone", "phone"),
            ("Subscriber (Rel.)", "subscriber"), ("Indi. Max (Rem.)", "max"), ("Ind. Ded. (Rem.)", "ded"),
        )],
        widths={0: 96}, bold_first_col=True,
    )

    # ---- Account Members (PRINT-5: the whole account, no 25/50-member cap) ---
    members = account_scope.account_members(db, patient, tenant_id)
    member_rows = []
    member_balances: dict[int, dict] = {}
    for m in members:
        try:
            member_balances[m.id] = balance_service.get_patient_balance(db, m.id, tenant_id)
        except Exception:  # noqa: BLE001 - one member's balance failure must not sink the print
            member_balances[m.id] = {}
        m_last, m_next = patient_intake_service._visits(db, m.id, today)
        sched = patient_intake_service._scheduled_recall(db, m.id)
        member_rows.append([
            f"{display_name(m)}{' *' if m.id == patient.id else ''}",
            f"{age_from_dob(m.dob, today) if m.dob else '-'} / {sex_letter(m.gender)}",
            fmt_date(m_next), fmt_date(m.next_recall), fmt_date(sched),
            fmt_date(m.last_visit or m_last), "Yes" if m.is_active else "No",
        ])
    report.section_title("Account Members")
    report.data_table(
        ["Member", "Age / Sex", "Next Visit", "Next Recall", "Sched Recall", "Last Visit", "Active"],
        member_rows, center=(6,), empty="No account members",
    )

    # ---- Appointments -------------------------------------------------------
    appts = db.execute(
        select(Appointment).where(
            Appointment.patient_id == patient.id, Appointment.is_archived.is_(False)
        ).order_by(Appointment.date.desc(), Appointment.start_time.desc()).limit(100)
    ).scalars().all()
    appt_providers = _provider_names(db, {a.provider_id for a in appts})
    op_ids = {a.operatory_id for a in appts if a.operatory_id}
    operatories = {o.id: o.name for o in db.execute(
        select(Operatory).where(Operatory.id.in_(op_ids))).scalars()} if op_ids else {}
    report.section_title("Appointments")
    report.data_table(
        ["Appt Date", "Appt Time", "Office", "Operatory", "Provider", "Duration", "Status", "Last Updated"],
        [[
            fmt_date(a.date), fmt_time(a.start_time), _office_code(offices.get(a.office_id)),
            cell(operatories.get(a.operatory_id)), cell(appt_providers.get(a.provider_id)),
            cell(a.duration), f"{a.status or '-'}{' (cancelled)' if a.is_cancelled else ''}",
            fmt_date(a.updated_at or a.created_at),
        ] for a in appts],
        right=(5,), empty="No appointments",
    )

    # ---- Recalls ------------------------------------------------------------
    recalls = db.execute(
        select(PatientRecall).where(
            PatientRecall.patient_id == patient.id, PatientRecall.is_active.is_(True)
        ).order_by(PatientRecall.due_date)
    ).scalars().all()

    def _interval(r: PatientRecall) -> str:
        if r.interval_months is None:
            return "-"
        unit = (r.interval_unit or "month").strip().lower()
        suffix = "Y" if unit.startswith("y") else "W" if unit.startswith("w") else "D" if unit.startswith("d") else "M"
        return f"{r.interval_months} {suffix}"

    report.section_title("Recalls")
    report.data_table(
        ["Code", "Interval", "Recall Date", "Reason", "Sch Date", "Sch Time"],
        [[cell(r.procedure_code), _interval(r), fmt_date(r.due_date), cell(r.recall_type),
          fmt_date(r.scheduled_date), fmt_time(r.scheduled_time)] for r in recalls],
        empty="No recalls",
    )

    # ---- Balances -----------------------------------------------------------
    b = member_balances.get(patient.id) or {}
    report.section_title("Balances")
    report.key_value_table([
        ["Account Balance", money(b.get("account_balance", b.get("balance"))), "Opening Balance", money(b.get("opening_balance"))],
        ["Today's Charges", money(b.get("today_charges")), "Total Charged", money(b.get("total_charged"))],
        ["Total Paid", money(b.get("total_paid")), "Insurance Balance", money(b.get("insurance_balance"))],
    ])
    totals = {k: 0.0 for k in ("current", "b30", "b60", "b90", "b120", "balance", "est_pat", "est_ins")}
    aging_rows = []
    for m in members:
        mb = member_balances.get(m.id) or {}
        aging = mb.get("aging") or {}
        vals = [_f(aging.get("current")), _f(aging.get("b30")), _f(aging.get("b60")), _f(aging.get("b90")),
                _f(aging.get("b120")), _f(mb.get("account_balance", mb.get("balance"))),
                _f(mb.get("estimated_patient")), _f(mb.get("estimated_insurance"))]
        for k, v in zip(totals, vals, strict=True):
            totals[k] += v
        aging_rows.append([display_name(m), *[money(v) for v in vals]])
    report.data_table(
        ["Member", "Current", "Over 30", "Over 60", "Over 90", "Over 120", "Balance", "Est Pat", "Est Ins"],
        aging_rows, right=(1, 2, 3, 4, 5, 6, 7, 8),
        foot=["Account Balance", *[money(v) for v in totals.values()]],
    )

    # ---- Billing + Contract summary -----------------------------------------
    recent = b.get("recent_activity") or {}
    report.section_title("Billing")
    report.data_table(
        ["", "Amount", "Date"],
        [["Last Pat Pay", money(recent.get("last_pat_amount")), fmt_date(recent.get("last_pat"))],
         ["Last Ins Pay", money(recent.get("last_ins_amount")), fmt_date(recent.get("last_ins"))]],
        right=(1,), widths={0: 120, 1: 100},
    )

    reg_plans = db.execute(select(PatientRegPlan).where(
        PatientRegPlan.patient_id == patient.id, PatientRegPlan.is_active.is_(True)).order_by(PatientRegPlan.id)
    ).scalars().all()
    pay_plans = db.execute(select(PatientPaymentPlan).where(
        PatientPaymentPlan.patient_id == patient.id, PatientPaymentPlan.is_active.is_(True)).order_by(PatientPaymentPlan.id)
    ).scalars().all()
    ortho_plans = db.execute(select(OrthoPlan).where(
        OrthoPlan.patient_id == patient.id, OrthoPlan.is_active.is_(True)).order_by(OrthoPlan.id)
    ).scalars().all()
    is_ortho = lambda t: (t or "").strip().lower().startswith("o")  # noqa: E731
    reg = next((p for p in pay_plans if not is_ortho(p.plan_type)), None) or (reg_plans[0] if reg_plans else None)
    ortho = ortho_plans[0] if ortho_plans else None
    report.section_title("Contract")
    report.data_table(
        ["", "Reg", "Ortho"],
        [["Rem. Amount", money_or_dash(reg.rem_total_amt if reg else None), money_or_dash(ortho.pat_rem_amt if ortho else None)],
         ["Rem. Payments", cell(reg.rem_payments if reg else None), cell(ortho.pat_rem_payments if ortho else None)]],
        right=(1, 2), widths={0: 120, 1: 100, 2: 100},
    )

    # ---- Contracts (full detail, as on the CONTRACTS tab) -------------------
    contract_rows = []
    for p in reg_plans:
        contract_rows.append(["Regular", fmt_date(p.setup_date), money_or_dash(p.amt_financed), money_or_dash(p.down_payment),
                              cell(p.apr), money_or_dash(p.fin_charge), cell(p.interval_type), cell(p.num_payments),
                              money_or_dash(p.periodic_amt), fmt_date(p.first_due_date), cell(p.rem_payments),
                              money_or_dash(p.rem_total_amt)])
    for p in pay_plans:
        contract_rows.append([p.plan_type or "Payment Plan", fmt_date(p.setup_date), money_or_dash(p.amt_financed),
                              money_or_dash(p.down_payment), cell(p.apr), money_or_dash(p.fin_charge),
                              cell(p.interval_type), cell(p.num_payments), money_or_dash(p.periodic_amt),
                              fmt_date(p.first_due_date), cell(p.rem_payments), money_or_dash(p.rem_total_amt)])
    for p in ortho_plans:
        # PRINT-9: the ortho patient sub-plan maps onto the same columns (pat_*).
        contract_rows.append(["Ortho", fmt_date(p.treat_start_date), money_or_dash(p.pat_amt_financed),
                              money_or_dash(p.pat_down_pay), cell(p.pat_apr), money_or_dash(p.pat_fin_charge),
                              cell(p.pat_interval), cell(p.pat_num_payments), money_or_dash(p.pat_periodic_amt),
                              fmt_date(p.pat_first_due_date), cell(p.pat_rem_payments), money_or_dash(p.pat_rem_amt)])
    report.section_title("Contracts")
    report.data_table(
        ["Plan", "Setup Date", "Amt Financed", "Down Pay", "APR", "Fin Charge", "Interval", "# Pmts",
         "Periodic Amt", "First Due", "Rem Pmts", "Rem Amount"],
        contract_rows, right=(2, 3, 4, 5, 7, 8, 10, 11), font_size=7,
        empty="No payment plans or contracts on file",
    )

    # ---- Referrals ----------------------------------------------------------
    referrals = db.execute(
        select(Referral).where(Referral.patient_id == patient.id).order_by(Referral.id)
    ).scalars().all()
    report.section_title("Referrals")
    report.data_table(
        ["Direction", "Name", "Practice", "Specialty", "Phone", "Email", "City / State", "Reason", "Cost", "Created"],
        [[
            _REFERRAL_DIRECTION.get((r.referral_type or "").strip(), cell(r.referral_type)),
            _last_first(r.last_name, r.first_name), cell(r.practice_name), cell(r.specialty), cell(r.phone),
            cell(r.email), cell(_join(r.city, r.state)), cell(r.reason_code or r.notes),
            money_or_dash(r.cost), fmt_date(r.created_at),
        ] for r in referrals],
        right=(8,), font_size=7, empty="No referrals recorded for this patient",
    )

    return report.render()


# ── 2. Account / Patient Ledger ───────────────────────────────────────────────
_LEDGER_COLS = ["Date", "Patient", "Office", "A", "Code", "TH", "Surf", "T", "N", "Description",
                "Bill", "Provider", "Est Pat", "Est Ins", "Amount", "Balance", "User"]
_BALANCE_COLS = ["Patient", "Current", "Over 30", "Over 60", "Over 90", "Over 120", "Balance",
                 "Est Ins", "Est Pat", "Today's Charges", "Today's Payments",
                 "Last Ins. Pay", "Last Ins. Pay Date", "Last Pat. Pay", "Last Pat. Date"]
_TYPE_LABELS = {"all": "All", "charge": "Charges", "procedure": "Charges", "payment": "Payments",
                "adjustment": "Adjustments", "claim": "Claims"}
_SORT_LABELS = {"date": "Date", "code": "Code", "provider": "Provider", "amount": "Amount", "patient": "Patient"}


def _plan_value(v: Any) -> str:  # noqa: ANN401
    """ledgerContracts.ts fmtPlanValue: dates → MM/DD/YYYY, numbers → $, blank → —."""
    if v is None or v == "":
        return "—"
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, (date, datetime)):
        return fmt_date(v)
    if isinstance(v, Decimal):
        return money(v)
    text = str(v)
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return fmt_date(text)
    try:
        return money(Decimal(text))
    except Exception:  # noqa: BLE001
        return text


def render_ledger(
    db: Session, patient_id: int, tenant_id: int, *,
    scope: str = "patient", date_from: date | None = None, date_to: date | None = None,
    transaction_type: str = "all", include_claims: bool = False, include_archived: bool = False,
    sort_by: str = "date", order: str = "asc",
) -> bytes:
    """The legacy ledger statement: **every** row matching the filter (PRINT-3 —
    no 500-row cap), in the requested sort, with the running balance and grand
    total, then the BALANCES table and the CONTRACTS cards."""
    patient = _patient(db, patient_id, tenant_id)
    office = _home_office(db, patient)
    offices = _office_map(db, tenant_id)
    scope = (scope or "patient").lower()

    # One unfiltered pull (the running balance and the per-member Balance column
    # need every row); the display filter + sort are applied here exactly as
    # ledger_service applies them for the paged feed.
    feed = ledger_service.get_account_ledger(
        db, patient.id, tenant_id, scope=scope, date_from=date_from, date_to=date_to,
        transaction_type="all", include_claims=include_claims, include_archived=include_archived,
        sort_by="date", order="asc", page=1, size=1_000_000,
    )
    all_rows = feed["rows"]
    per_member_balance: dict[int, Decimal] = {}
    for r in all_rows:
        per_member_balance[r["patient_id"]] = per_member_balance.get(r["patient_id"], _ZERO) + (r["amount"] or _ZERO)

    tt = (transaction_type or "all").lower()
    rows = all_rows
    if tt != "all":
        wanted = "charge" if tt == "procedure" else tt
        rows = [r for r in rows if r["source_type"] == wanted]
    key = ledger_service.ACCOUNT_SORT_KEYS.get(sort_by, ledger_service.ACCOUNT_SORT_KEYS["date"])
    rows = sorted(rows, key=key, reverse=(order or "asc").lower() == "desc")

    members = account_scope.account_members(db, patient, tenant_id) if scope == "account" else [patient]
    scope_label = "Account Ledger" if scope == "account" else "Patient Ledger"
    range_text = (
        f"{fmt_date(date_from) if date_from else 'Start'} – {fmt_date(date_to) if date_to else 'Today'}"
        if (date_from or date_to) else "All dates"
    )
    report = PatientReport(_header(
        db, patient, office, tenant_id, title=scope_label,
        extra=[
            ("Scope", f"{scope_label}{f' ({len(members)} members)' if len(members) > 1 else ''}"),
            ("Date Range", f"{range_text}    Type: {_TYPE_LABELS.get(tt, tt.title())}    Sort: {_SORT_LABELS.get(sort_by, sort_by)}"),
            ("Balance", money(feed["grand_total"])),
        ],
    ), landscape=True)

    # ---- Transactions -------------------------------------------------------
    report.section_title(f"Transactions ({len(rows)})")
    body = []
    for r in rows:
        is_claim = r["source_type"] == "claim"
        bill = "H" if r.get("hold_claim") else (f"#{r['claim_number']}" if is_claim and r.get("claim_number") else cell(r.get("billing_status")))
        body.append([
            fmt_date(r["entry_date"]), cell(r.get("patient_name")), cell(r.get("office_short_id")),
            cell(r.get("apply_to")), cell(r.get("code")), cell(r.get("tooth")), cell(r.get("surface")),
            cell(r.get("transaction_kind")), "N" if r.get("unbilled") else "-",
            cell(r.get("description")), bill, cell(r.get("provider_name")),
            money(r.get("patient_estimate")), money(r.get("insurance_estimate")),
            "-" if is_claim else money(r["amount"]), money(r["running_balance"]), cell(r.get("user_label"), ""),
        ])
    report.data_table(
        _LEDGER_COLS, body,
        center=(3, 5, 6, 7, 8, 10), right=(12, 13, 14, 15),
        # Fixed widths for the narrow columns; Description takes what is left
        # (~78 pt on landscape Letter) so a migrated descriptor wraps to two
        # lines instead of five.
        widths={0: 50, 1: 70, 2: 36, 3: 18, 4: 40, 5: 22, 6: 28, 7: 16, 8: 16, 10: 50, 11: 60,
                12: 44, 13: 44, 14: 52, 15: 50, 16: 46},
        font_size=7, empty="No transactions match the current filter.",
        foot=["Total"] + [""] * 13 + [money(feed["grand_total"]), "", ""], foot_span=14,
    )

    # ---- Balances -----------------------------------------------------------
    member_balances: dict[int, dict] = {}
    for m in members:
        try:
            member_balances[m.id] = balance_service.get_patient_balance(db, m.id, tenant_id)
        except Exception:  # noqa: BLE001
            member_balances[m.id] = {}

    def _bal_row(label: str, bal: dict, balance: Decimal) -> list[str]:
        aging = bal.get("aging") or {}
        recent = bal.get("recent_activity") or {}
        return [
            label, money(aging.get("current")), money(aging.get("b30")), money(aging.get("b60")),
            money(aging.get("b90")), money(aging.get("b120")), money(balance),
            money(bal.get("estimated_insurance")), money(bal.get("estimated_patient")),
            money(bal.get("today_charges")), money(recent.get("today")),
            money(recent.get("last_ins_amount")), fmt_date(recent.get("last_ins")),
            money(recent.get("last_pat_amount")), fmt_date(recent.get("last_pat")),
        ]

    agg: dict[str, float] = {}
    for bal in member_balances.values():
        aging = bal.get("aging") or {}
        recent = bal.get("recent_activity") or {}
        for k, v in (("current", aging.get("current")), ("b30", aging.get("b30")), ("b60", aging.get("b60")),
                     ("b90", aging.get("b90")), ("b120", aging.get("b120")),
                     ("estimated_insurance", bal.get("estimated_insurance")),
                     ("estimated_patient", bal.get("estimated_patient")),
                     ("today_charges", bal.get("today_charges")), ("today", recent.get("today"))):
            agg[k] = agg.get(k, 0.0) + _f(v)
    last_ins = max(((b.get("recent_activity") or {}) for b in member_balances.values()),
                   key=lambda r: r.get("last_ins") or "", default={})
    last_pat = max(((b.get("recent_activity") or {}) for b in member_balances.values()),
                   key=lambda r: r.get("last_pat") or "", default={})
    account_row = _bal_row("Account Balance", {
        "aging": {k: agg.get(k) for k in ("current", "b30", "b60", "b90", "b120")},
        "estimated_insurance": agg.get("estimated_insurance"), "estimated_patient": agg.get("estimated_patient"),
        "today_charges": agg.get("today_charges"),
        "recent_activity": {"today": agg.get("today"), "last_ins_amount": last_ins.get("last_ins_amount"),
                            "last_ins": last_ins.get("last_ins"), "last_pat_amount": last_pat.get("last_pat_amount"),
                            "last_pat": last_pat.get("last_pat")},
    }, sum(per_member_balance.values(), _ZERO))
    report.section_title("Balances")
    report.data_table(
        _BALANCE_COLS,
        [account_row, *[_bal_row(display_name(m), member_balances.get(m.id) or {}, per_member_balance.get(m.id, _ZERO)) for m in members]],
        right=tuple(range(1, 15)), font_size=6.5, empty="No balance data available.", bold_first_col=True,
    )

    # ---- Contracts — the three plan cards ------------------------------------
    pay_plans = db.execute(select(PatientPaymentPlan).where(
        PatientPaymentPlan.patient_id == patient.id, PatientPaymentPlan.is_active.is_(True)).order_by(PatientPaymentPlan.id)
    ).scalars().all()
    reg_plans = db.execute(select(PatientRegPlan).where(
        PatientRegPlan.patient_id == patient.id, PatientRegPlan.is_active.is_(True)).order_by(PatientRegPlan.id)
    ).scalars().all()
    ortho_plans = db.execute(select(OrthoPlan).where(
        OrthoPlan.patient_id == patient.id, OrthoPlan.is_active.is_(True)).order_by(OrthoPlan.id)
    ).scalars().all()
    is_ortho = lambda t: (t or "").strip().lower().startswith("o")  # noqa: E731
    reg = next((p for p in pay_plans if not is_ortho(p.plan_type)), None)
    reg_legacy = reg_plans[0] if reg_plans else None
    ortho = ortho_plans[0] if ortho_plans else None
    g = lambda obj, attr: getattr(obj, attr) if obj is not None else None  # noqa: E731
    report.section_title("Contracts")
    report.cards([
        ("Regular - Patient Payment Plan", [
            ("Plan Amount", _plan_value(g(reg, "amt_financed") or g(reg, "plan_bal_amt") or g(reg_legacy, "amt_financed"))),
            ("Down Pay", _plan_value(g(reg, "down_payment") or g(reg_legacy, "down_payment"))),
            ("Next Per. Amt", _plan_value(g(reg, "periodic_amt") or g(reg_legacy, "periodic_amt"))),
            ("Next Date", _plan_value(g(reg, "first_due_date") or g(reg_legacy, "first_due_date"))),
            ("Rem. Total Amt", _plan_value(g(reg, "rem_total_amt") or g(reg_legacy, "rem_total_amt"))),
            ("Rem. # Of Pay", _plan_value(g(reg, "rem_payments") if reg else g(reg_legacy, "rem_payments"))),
        ]),
        # PRINT-9: ortho_plans.pat_* is the ortho patient sub-plan.
        ("Ortho - Patient Payment Plan", [
            ("Plan Amount", _plan_value(g(ortho, "pat_amt_financed"))),
            ("Down Pay", _plan_value(g(ortho, "pat_down_pay"))),
            ("Next Per. Amt", _plan_value(g(ortho, "pat_periodic_amt"))),
            ("Next Date", _plan_value(g(ortho, "pat_first_due_date"))),
            ("Rem. Total Amt", _plan_value(g(ortho, "pat_rem_amt"))),
            ("Rem. # Of Pay", _plan_value(g(ortho, "pat_rem_payments"))),
        ]),
        ("Ortho - Insurance Payment Plan", [
            ("Plan Amount", _plan_value(g(ortho, "ins_plan_amount"))),
            ("Down Pay", _plan_value(g(ortho, "ins_down_pay"))),
            ("Next Per. Amt", _plan_value(g(ortho, "ins_periodic_amt"))),
            ("Next Date", _plan_value(g(ortho, "ins_first_due_date"))),
            ("Rem. Total Amt", _plan_value(g(ortho, "ins_rem_amt"))),
            ("Rem. # Of Pay", _plan_value(g(ortho, "ins_rem_payments"))),
        ]),
    ])
    return report.render()


# ── 3. Transactions Entry (day sheet) ─────────────────────────────────────────
def day_totals(db: Session, patient_id: int, tenant_id: int, day: date | None = None) -> dict:
    """PRINT-6 / CHG-7: the Patient Dashboard's *Today's* block for one date —
    total charges, est. insurance, est. patient **and the deductible portion**.

    The deductible is not stored on a charge; it is what the estimate engine
    would consume across the day's charges (each priced at its *stored* fee, so
    the split reflects what was actually posted), against the primary slot's
    remaining deductible as it stands now. That is the same arithmetic
    ``POST /patients/{id}/estimate`` runs before a charge is posted.
    """
    patient = _patient(db, patient_id, tenant_id)
    office = _home_office(db, patient)
    day = day or office_today(office.timezone if office else None)
    charges = db.execute(
        select(PatientProcedure).where(
            PatientProcedure.patient_id == patient.id,
            PatientProcedure.date_of_service == day,
            PatientProcedure.is_void.is_(False),
            PatientProcedure.is_archived.is_(False),
        ).order_by(PatientProcedure.created_at, PatientProcedure.id)
    ).scalars().all()
    total = sum((c.fee or _ZERO for c in charges), _ZERO)
    est_ins = sum((c.insurance_estimate or _ZERO for c in charges), _ZERO)
    est_ded = _ZERO
    has_coverage = False
    if charges:
        try:
            est = estimate_service.estimate(
                db, patient.id, tenant_id,
                lines=[{"procedure_code": c.procedure_code, "fee": c.fee, "provider_id": c.provider_id} for c in charges],
                office_id=charges[0].office_id or patient.home_office_id,
            )
            est_ded = Decimal(str(est["estimated_deductible"]))
            has_coverage = bool(est["has_active_coverage"])
        except Exception:  # noqa: BLE001 - an unpriceable code must not sink the day sheet
            pass
    return {
        "patient_id": patient.id,
        "date": day,
        "transaction_count": len(charges),
        "total_charges": total,
        "insurance_estimate": est_ins,
        "patient_estimate": max(total - est_ins, _ZERO),
        "estimated_deductible": est_ded,
        "has_active_coverage": has_coverage,
    }


def _refund_rows(db: Session, patient_id: int, day: date) -> list[dict]:
    rows = db.execute(
        select(PatientRefund).where(
            PatientRefund.patient_id == patient_id, PatientRefund.refund_date == day,
            PatientRefund.is_void.is_(False),
        ).order_by(PatientRefund.id)
    ).scalars().all()
    return [{
        "patient_id": r.patient_id, "entry_date": r.refund_date, "source_type": "refund", "source_id": r.id,
        "code": "REFUND", "description": r.notes or r.reason or r.refund_method, "transaction_kind": "P",
        "apply_to": r.refund_method, "tooth": None, "surface": None, "provider_id": None,
        "office_id": r.office_id, "patient_estimate": None, "insurance_estimate": None,
        "billing_status": None, "hold_claim": None, "amount": r.amount or _ZERO,
        "charge": r.amount or _ZERO, "credit": _ZERO, "provider_name": None, "office_short_id": None,
    } for r in rows]


def render_transactions(db: Session, patient_id: int, tenant_id: int, day: date | None = None) -> bytes:
    """The day's check-out sheet: the Patient Dashboard block followed by the
    transaction grid for the selected date and its totals (landscape)."""
    patient = _patient(db, patient_id, tenant_id)
    office = _home_office(db, patient)
    offices = _office_map(db, tenant_id)
    day = day or office_today(office.timezone if office else None)
    day_text = fmt_date(day)

    report = PatientReport(_header(
        db, patient, office, tenant_id, title="Transactions Entry",
        extra=[("Transaction Date", day_text)],
    ), landscape=True)

    # ---- Patient Dashboard --------------------------------------------------
    try:
        balance = balance_service.get_patient_balance(db, patient.id, tenant_id)
    except Exception:  # noqa: BLE001
        balance = {}
    totals = day_totals(db, patient.id, tenant_id, day)
    rp = patient_overview_service.resolve_responsible_party(db, tenant_id, patient.responsible_party_id)
    slots = _insurance_slots(db, patient.id)
    prim = _pick_slot(slots, "D", "primary") or next(iter(slots), None)
    sec = _pick_slot(slots, "D", "secondary")

    def _carrier_line(slot: dict | None) -> str:
        if not slot or not slot["carrier"]:
            return "None on file"
        rec, plan, carrier = slot["record"], slot["plan"], slot["carrier"]
        parts = [carrier.name]
        if plan and plan.plan_type:
            parts.append(plan.plan_type)
        max_rem = rec.max_remaining if rec.max_remaining is not None else (plan.individual_max if plan else None)
        if max_rem is not None:
            parts.append(f"Max Rem {money(max_rem)}")
        return " · ".join(parts)

    report.section_title("Patient Dashboard")
    report.key_value_table([
        ["Responsible", _last_first(rp.last_name, rp.first_name) if rp else display_name(patient),
         "Today's Total Charges", money(totals["total_charges"])],
        ["RP BD", fmt_date(rp.dob) if rp and getattr(rp, "dob", None) else fmt_date(patient.dob),
         "Today's Est Ded", money(totals["estimated_deductible"])],
        ["Balance", money(balance.get("balance")), "Today's Est Ins Portion", money(totals["insurance_estimate"])],
        ["Est Ins", money(balance.get("estimated_insurance")), "Today's Est Pat Portion", money(totals["patient_estimate"])],
        ["Est Pat", money(balance.get("estimated_patient")), "Prim. Ins", _carrier_line(prim)],
        ["", "", "Sec. Ins", _carrier_line(sec)],
    ])

    # ---- Transactions for the date -------------------------------------------
    feed = ledger_service.get_account_ledger(
        db, patient.id, tenant_id, scope="patient", date_from=day, date_to=day,
        transaction_type="all", include_claims=False, sort_by="date", order="asc", page=1, size=1_000_000,
    )
    rows = feed["rows"] + _refund_rows(db, patient.id, day)
    body = []
    total_amount = total_est_pat = total_est_ins = _ZERO
    for r in rows:
        is_credit = r["source_type"] in ("payment", "adjustment") or r.get("transaction_kind") == "C"
        amount = r["amount"]
        est_pat = r.get("patient_estimate") or _ZERO
        est_ins = r.get("insurance_estimate") or _ZERO
        total_amount += amount
        total_est_pat += est_pat
        total_est_ins += est_ins
        body.append([
            "Y" if is_credit else "", fmt_date(r["entry_date"]), display_name(patient),
            cell(r.get("office_short_id") or _office_code(offices.get(r.get("office_id")))),
            cell(r.get("apply_to")), cell(r.get("code")), cell(r.get("tooth")), cell(r.get("surface")),
            cell(r.get("description")), cell(r.get("billing_status"), ""), cell(r.get("provider_name"), ""),
            money(est_pat) if est_pat else "", money(est_ins) if est_ins else "", money(amount),
        ])
    n = len(body)
    report.section_title(f"Transactions — {day_text}")
    report.data_table(
        ["Pm", "Date", "Patient", "Office", "A", "Code", "Th", "Surf", "Description", "Bill", "Provider",
         "Est Pat", "Est Ins", "Amount"],
        body, center=(0, 4, 6, 7), right=(11, 12, 13),
        widths={0: 22, 1: 58, 4: 50, 5: 46, 6: 26, 7: 34, 9: 50, 11: 54, 12: 54, 13: 58},
        font_size=7.5, empty="No records to display.",
        foot=[f"Total ({n} transaction{'' if n == 1 else 's'})"] + [""] * 10
        + [money(total_est_pat), money(total_est_ins), money(total_amount)],
        foot_span=11,
    )
    return report.render()


# ── 4. Insurance Details ──────────────────────────────────────────────────────
_ORDER_LABEL = {"primary": "Primary", "secondary": "Secondary", "tertiary": "Tertiary", "quaternary": "Quaternary"}
_CATEGORY_LABEL = {"D": ("Dental", "dental"), "M": ("Medical", "medical")}
_GENDER = {"M": "Male", "F": "Female", "O": "Other"}


def render_insurance(
    db: Session, patient_id: int, tenant_id: int, *, category: str = "D", order: str = "primary",
) -> bytes:
    """One slot (e.g. Primary Dental) as a report: plan + carrier + employer,
    benefit information, eligibility, subscriber information and notes."""
    patient = _patient(db, patient_id, tenant_id)
    office = _home_office(db, patient)
    category = (category or "D").strip().upper()[:1]
    order = (order or "primary").strip().lower()
    cat_label, cat_kind = _CATEGORY_LABEL.get(category, (category, category.lower()))
    slot_label = f"{_ORDER_LABEL.get(order, order.title())} {cat_label}"

    slot = _pick_slot(_insurance_slots(db, patient.id, active_only=False), category, order)
    if slot is None:
        raise NotFoundError(
            f"Patient '{patient_id}' has no {slot_label.lower()} insurance slot",
            code="insurance_slot_not_found",
        )
    rec, plan, carrier, sub, employer = (slot["record"], slot["plan"], slot["carrier"], slot["subscriber"], slot["employer"])

    report = PatientReport(_header(
        db, patient, office, tenant_id, title=f"Insurance Details — {slot_label}",
        extra=[("Plan Slot", f"{slot_label} ({cat_kind})")],
    ))
    group_number = (plan.group_number if plan else None) or (sub.group_number if sub else None)
    is_dental = insurance_service.carrier_is_dental(carrier.carrier_type) if carrier else None
    carrier_type = "Dental" if is_dental else "Medical" if is_dental is False else cell(carrier.carrier_type if carrier else None)

    report.section_title("Insurance Plan")
    report.key_value_table([
        ["Plan ID", cell(plan.id if plan else None), "Group #", cell(group_number)],
        ["Carrier Name", cell(carrier.name if carrier else None), "Payer ID", cell(carrier.payer_id if carrier else None)],
        ["Carrier ID", cell((carrier.legacy_id or carrier.id) if carrier else None), "Type", carrier_type],
        ["Carrier Phone", cell(carrier.phone if carrier else None), "Status", "Active" if rec.is_active else "Inactive"],
        ["Employer Name", cell(employer.name if employer else None),
         "Employer Location", cell(_join(employer.city, employer.state) if employer else None)],
    ])

    g = lambda obj, attr: getattr(obj, attr) if obj is not None else None  # noqa: E731
    report.section_title("Benefit Information")
    report.data_table(
        ["", "Ind.", "Ind. Rem.", "Fam.", "Fam. Rem."],
        [["Deductible", money_or_dash(g(plan, "individual_deductible")), money_or_dash(rec.deductible_remaining),
          money_or_dash(g(plan, "family_deductible")), money_or_dash(g(sub, "family_ded_remaining"))],
         ["Annual Max.", money_or_dash(g(plan, "individual_max")), money_or_dash(rec.max_remaining),
          money_or_dash(g(plan, "family_max")), money_or_dash(g(sub, "family_max_remaining"))],
         ["Ortho", money_or_dash(g(plan, "ortho_max")),
          money_or_dash(rec.ortho_remaining if rec.ortho_remaining is not None else g(sub, "ortho_remaining")), "", ""]],
        right=(1, 2, 3, 4), widths={0: 110}, bold_first_col=True,
    )

    # PRINT-8: the Plan Date column is the subscriber's plan_effective_date /
    # plan_term_date (INS-PT-6) — the legacy grid keeps plan and subscriber dates
    # side by side on the enrolment, not on the shared plan row.
    report.section_title("Eligibility")
    report.data_table(
        ["", "Plan Date", "Sub Date"],
        [["Effective Date", fmt_date(g(sub, "plan_effective_date")), fmt_date(g(sub, "effective_date"))],
         ["Term Date", fmt_date(g(sub, "plan_term_date")), fmt_date(g(sub, "term_date"))],
         ["Anni. Date Exp", fmt_date(g(plan, "anniversary_date")), fmt_date(g(sub, "anniversary_date"))]],
        center=(1, 2), widths={0: 110, 1: 120, 2: 120}, bold_first_col=True,
    )
    report.key_value_table([
        ["Status", cell(g(sub, "elig_status")), "Verified On", fmt_date(g(sub, "elig_verified_on"))],
        ["Verified By", cell(g(sub, "elig_verified_by")), "", ""],
    ])

    sex = _GENDER.get((g(sub, "sub_gender") or "").strip().upper()[:1], cell(g(sub, "sub_gender")))
    report.section_title("Subscriber Information")
    report.key_value_table([
        ["Last", cell(g(sub, "sub_last_name")), "First", cell(g(sub, "sub_first_name"))],
        ["SubID", cell(g(sub, "sub_member_id")), "Birth Date", fmt_date(g(sub, "sub_dob"))],
        # PRINT-7: marital_status / sub_phone (INS-PT-1/2) and the secondary
        # subscriber's relationship to the primary (INS-PT-3) are real columns.
        ["Sex", sex, "Marital Status", cell(g(sub, "marital_status"))],
        ["Address", cell(_join(g(sub, "sub_address"), g(sub, "sub_address2"))), "Phone", cell(g(sub, "sub_phone"))],
        ["City / St / Zip", cell(_join(_join(g(sub, "sub_city"), g(sub, "sub_state")), g(sub, "sub_zip"), sep=" ")),
         "Patient Rel to Sub", cell(rec.relationship)],
        ["Sec. Sub Rel to Prim. Sub", cell(rec.sec_sub_rel_to_prim_sub), "Group #", cell(group_number)],
    ])

    report.section_title("Notes")
    report.paragraph("", g(sub, "notes"))
    return report.render()
