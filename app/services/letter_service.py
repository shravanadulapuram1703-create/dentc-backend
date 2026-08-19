"""Letters: merge-field catalog, server-side render, batch runs (LTR-3..6).

Why this exists
---------------
Every letter used to be merged and rendered in the browser, which had two costs:
the 56-token merge catalog was duplicated in the frontend (free to drift from
whatever the legacy engine did), and **batch letter runs were impossible** — nine
seeded templates are explicitly collection sweeps (``CS001…CS009 - Batch Coll N
Letter``) that need to run over a queue, not one click per patient.

The catalog below is derived from the seeded corpus itself: exactly the 56
distinct ``#TOKEN#`` merge fields that appear across the 153 migrated templates.
Adding a token here is the only place it has to be registered.

Three public surfaces sit on one context builder:

* :func:`build_context`  -> ``GET /patients/{id}/letter-context`` (LTR-6): the
  2–6 round trips the dialog used to make, in one call.
* :func:`render_template` -> ``POST /letters/render`` (LTR-5).
* :func:`run_batch`      -> ``POST /letters/render-batch`` (LTR-5), a durable job.

Safety properties the frontend relies on, preserved here:

* Merged **values are HTML-escaped** before substitution, so patient data can
  never inject markup into the rendered letter.
* The template body itself is passed through :func:`sanitize_html` — a template
  row is tenant-editable content, and the render is now server-side.
* A token with no backing data is left *blank* and reported in
  ``unresolved_tokens`` rather than printing ``#TOKEN#`` at the patient.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.datetimes import DEFAULT_TIMEZONE, office_today
from app.core.exceptions import NotFoundError, ValidationError
from app.core.html_sanitize import sanitize_html
from app.db.models import (
    AccountSettings,
    Appointment,
    LetterBatchItem,
    LetterBatchRun,
    LetterTemplate,
    Office,
    Patient,
    Provider,
    Referral,
    ResponsibleParty,
    TreatmentPlan,
    TreatmentPlanItem,
)
from app.services import balance_service
from app.services.patient_overview_service import resolve_responsible_party

# ── Merge-field catalog ──────────────────────────────────────────────────────
# (token, group, label) — the group is what the Setup UI can render as a section.
# Keep in step with the frontend's src/features/letters/mergeFields.ts; this list
# is the authoritative one and is served by GET /letters/merge-fields.
MERGE_FIELDS: tuple[tuple[str, str, str], ...] = (
    # Patient
    ("PAT_ID", "patient", "Patient id"),
    ("PAT_FIRST_NAME", "patient", "First name"),
    ("PAT_NAME_FIRST", "patient", "First name (legacy alias)"),
    ("PAT_LAST_NAME", "patient", "Last name"),
    ("PAT_MID_INITIAL", "patient", "Middle initial"),
    ("PAT_BIRTHDATE", "patient", "Date of birth"),
    ("PAT_ADDRESS", "patient", "Street address"),
    ("PAT_CITY", "patient", "City"),
    ("PAT_STATE", "patient", "State"),
    ("PAT_ZIP", "patient", "ZIP"),
    ("PAT_EMAIL", "patient", "Email"),
    ("PAT_HOMEPHONE", "patient", "Home phone"),
    ("PAT_CELLPHONE", "patient", "Cell phone"),
    ("PAT_WORKPHONE", "patient", "Work phone"),
    ("LASTVISIT_DATE", "patient", "Last visit date"),
    # Preferred provider letterhead (LTR-3)
    ("PAT_PREF_PROV", "provider", "Preferred provider name"),
    ("PAT_PREF_PROV_Address", "provider", "Preferred provider address"),
    ("PAT_PREF_PROV_CITY", "provider", "Preferred provider city"),
    ("PAT_PREF_PROV_STATE", "provider", "Preferred provider state"),
    ("PAT_PREF_PROV_ZIP", "provider", "Preferred provider ZIP"),
    ("PAT_PREF_PROV_PHONE", "provider", "Preferred provider phone"),
    ("DOC_LAST_NAME", "provider", "Doctor last name"),
    # Referral
    ("PAT_REF_BY", "referral", "Referred by"),
    ("PAT_REF_BY_ADDRESS", "referral", "Referred-by address"),
    ("PAT_REF_BY_CITY", "referral", "Referred-by city"),
    ("PAT_REF_BY_STATE", "referral", "Referred-by state"),
    ("PAT_REF_BY_ZIP", "referral", "Referred-by ZIP"),
    ("PAT_REF_TO", "referral", "Referred to"),
    ("PAT_REF_TO_DATE", "referral", "Referral-to date"),
    # Office
    ("OFFICE_NAME", "office", "Office name"),
    ("OFFICE_CNAME", "office", "Office corporate / DBA name"),
    ("OFFICE_ADDRESS", "office", "Office address"),
    ("OFFICE_CITY", "office", "Office city"),
    ("OFFICE_STATE", "office", "Office state"),
    ("OFFICE_ZIP", "office", "Office ZIP"),
    ("OFFICE_PHONE1", "office", "Office phone"),
    ("OFFICE_EMAIL", "office", "Office email"),
    # Marketing / practice identity (LTR-3)
    ("MARKET_NAME", "marketing", "Marketing name"),
    ("MARKET_ADDRESS", "marketing", "Marketing address"),
    ("MARKET_CITY", "marketing", "Marketing city"),
    ("MARKET_STATE", "marketing", "Marketing state"),
    ("MARKET_ZIP", "marketing", "Marketing ZIP"),
    ("MARKET_PHONE", "marketing", "Marketing phone"),
    # Responsible party
    ("RP_FIRST_NAME", "responsible_party", "Responsible party first name"),
    ("RP_LAST_NAME", "responsible_party", "Responsible party last name"),
    ("RP_MID_INITIAL", "responsible_party", "Responsible party middle initial"),
    ("RP_ADDRESS", "responsible_party", "Responsible party address"),
    ("RP_CITY", "responsible_party", "Responsible party city"),
    ("RP_STATE", "responsible_party", "Responsible party state"),
    ("RP_ZIP", "responsible_party", "Responsible party ZIP"),
    ("RP_EMAIL", "responsible_party", "Responsible party email"),
    ("RP_TOTAL_BAL", "responsible_party", "Account balance"),
    # Appointment. LTR-13: these mean "the appointment this letter is about" —
    # the upcoming one when there is one, otherwise the most recent past one.
    # A consent form is printed at the chair *after* the visit is under way, so
    # binding them to the future alone left "Dr. ___" blank on a signed document.
    ("APPT_DATE", "appointment", "Appointment date (next, else last)"),
    ("APPT_DATETIME", "appointment", "Appointment date and time (next, else last)"),
    ("APPT_PRDR", "appointment", "Appointment provider (next, else last, else preferred)"),
    # Misc
    ("TODAY_DATE", "misc", "Today's date, in the printing office's timezone"),
    ("TX_PLAN_TH_NUMBER", "treatment_plan", "Treatment-plan tooth number(s)"),
)

MERGE_FIELD_NAMES = frozenset(token for token, _g, _l in MERGE_FIELDS)

#: The 56 tokens actually present in the seeded 153-template corpus. The catalog
#: above is a **superset**: ``APPT_DATETIME`` is an extension the frontend asked
#: for (LTR-13) that no migrated template uses yet. Keeping the corpus set
#: explicit is what lets ``tests/test_letters_module.py`` prove the catalog still
#: covers every token a real template can contain.
CORPUS_TOKENS = MERGE_FIELD_NAMES - {"APPT_DATETIME"}

#: LTR-13 fallback tiers for the appointment block, best first.
APPOINTMENT_TIERS = ("next", "last", "preferred")

#: Tokens whose value costs a full balance aggregate. The dialog only pays for
#: that when the chosen template actually contains one (LTR-6).
BALANCE_TOKENS = frozenset({"RP_TOTAL_BAL"})
#: Tokens that need a treatment plan to bind to (LTR-4).
TREATMENT_PLAN_TOKENS = frozenset({"TX_PLAN_TH_NUMBER"})

_TOKEN_RE = re.compile(r"#([A-Za-z0-9_]+)#")


def merge_field_catalog() -> list[dict]:
    return [
        {
            "token": token,
            "placeholder": f"#{token}#",
            "group": group,
            "label": label,
            "requires_balance": token in BALANCE_TOKENS,
            "requires_treatment_plan": token in TREATMENT_PLAN_TOKENS,
        }
        for token, group, label in MERGE_FIELDS
    ]


def tokens_in(body_html: str | None) -> list[str]:
    """Distinct ``#TOKEN#`` names in a template body, in first-appearance order."""
    seen: dict[str, None] = {}
    for match in _TOKEN_RE.findall(body_html or ""):
        seen.setdefault(match, None)
    return list(seen)


# ── Formatting helpers ───────────────────────────────────────────────────────
def _date(value: date | datetime | None) -> str:
    """Legacy letters print US short dates; keep that, they are patient-facing."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%m/%d/%Y")


def _datetime(day: date | None, at: time | None) -> str:
    """``08/19/2026 9:00 AM`` — LTR-13's ``#APPT_DATETIME#``."""
    if day is None:
        return ""
    if at is None:
        return _date(day)
    return f"{_date(day)} {at.strftime('%I:%M %p').lstrip('0')}"


def _money(value: Decimal | float | int | None) -> str:
    return f"${float(value or 0):,.2f}"


def _street(line1: str | None, line2: str | None) -> str:
    return " ".join(part.strip() for part in (line1, line2) if part and part.strip())


def _full_name(first: str | None, last: str | None) -> str:
    return " ".join(part.strip() for part in (first, last) if part and part.strip())


def _last_name_of(name: str | None) -> str:
    """Provider rows carry a single ``name`` (\"Dr. Jane Smith\") as often as a
    split first/last, so fall back to the trailing word."""
    parts = [p for p in (name or "").replace(",", " ").split() if p]
    return parts[-1] if parts else ""


# ── Context assembly ─────────────────────────────────────────────────────────
def _require_patient(db: Session, tenant_id: int, patient_id: int) -> Patient:
    patient = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if patient is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return patient


def _referred_by(db: Session, tenant_id: int, patient: Patient) -> Referral | None:
    """``patients.referred_by`` holds either a legacy referral id or a free-text
    name (PO-6). Resolve the id form to the row so the address block populates."""
    key = (patient.referred_by or "").strip()
    if not key:
        return None
    return db.execute(
        select(Referral).where(
            Referral.tenant_id == tenant_id,
            Referral.legacy_id == key,
        ).limit(1)
    ).scalar_one_or_none()


def _appointments(db: Session, patient_id: int, today: date) -> tuple[Appointment | None, Appointment | None]:
    """(next upcoming, most recent past) — one scan, the rows are few per patient."""
    rows = list(db.execute(
        select(Appointment).where(
            Appointment.patient_id == patient_id,
            Appointment.is_archived.is_(False),
            Appointment.is_cancelled.is_(False),
        ).order_by(Appointment.date, Appointment.start_time)
    ).scalars().all())
    upcoming = next((a for a in rows if a.date >= today), None)
    past = next((a for a in reversed(rows) if a.date < today), None)
    return upcoming, past


def _treatment_plan_teeth(db: Session, plan_id: str) -> tuple[TreatmentPlan | None, list[str]]:
    """LTR-4: the tooth numbers a treatment-plan letter interpolates.

    The Letters dialog has no plan context of its own, so a plan is only bound
    when the caller passes ``treatment_plan_id`` (i.e. the letter was launched
    *from* a plan). Without it the token stays unresolved, which is the honest
    outcome — the alternative is printing an arbitrary patient's tooth number.
    """
    plan = db.get(TreatmentPlan, plan_id)
    if plan is None:
        return None, []
    teeth = list(db.execute(
        select(TreatmentPlanItem.tooth).where(
            TreatmentPlanItem.plan_id == plan_id,
            TreatmentPlanItem.is_archived.is_(False),
            TreatmentPlanItem.tooth.is_not(None),
        ).order_by(TreatmentPlanItem.priority, TreatmentPlanItem.id)
    ).scalars().all())
    # De-duplicate, preserve plan order.
    seen: dict[str, None] = {}
    for tooth in teeth:
        value = (tooth or "").strip()
        if value:
            seen.setdefault(value, None)
    return plan, list(seen)


def build_context(
    db: Session,
    tenant_id: int,
    patient_id: int,
    *,
    office_id: int | None = None,
    treatment_plan_id: str | None = None,
    include_balance: bool = False,
) -> dict[str, Any]:
    """Everything a letter merge needs, in one round trip (LTR-6).

    ``include_balance`` is opt-in because the balance aggregate is the expensive
    part; :func:`render_template` turns it on automatically when the chosen
    template actually contains ``#RP_TOTAL_BAL#``.
    """
    patient = _require_patient(db, tenant_id, patient_id)

    office = db.execute(
        select(Office).where(
            Office.id == (office_id or patient.home_office_id),
            Office.tenant_id == tenant_id,
        )
    ).scalar_one_or_none() if (office_id or patient.home_office_id) else None

    # LTR-14: "today" is the *printing office's* today, not the server's. Every
    # US practice is UTC-negative, so a UTC date is tomorrow's date for the last
    # few hours of the working day — which post-dates an evening consent form.
    tz_name = (getattr(office, "timezone", None) or DEFAULT_TIMEZONE)
    today = office_today(tz_name)

    provider = db.get(Provider, patient.preferred_provider_id) if patient.preferred_provider_id else None
    if provider is not None and provider.tenant_id != tenant_id:
        provider = None

    account = db.execute(
        select(AccountSettings).where(AccountSettings.tenant_id == tenant_id)
    ).scalar_one_or_none()

    rp = resolve_responsible_party(db, tenant_id, patient.responsible_party_id)
    referred_by = _referred_by(db, tenant_id, patient)
    next_appt, last_appt = _appointments(db, patient_id, today)
    # LTR-13: resolve BOTH appointment providers. The merge falls back from the
    # upcoming appointment to the last one, so a consent form printed mid-visit
    # names the treating doctor instead of "Dr. ___".
    next_appt_provider = db.get(Provider, next_appt.provider_id) if next_appt else None
    last_appt_provider = db.get(Provider, last_appt.provider_id) if last_appt else None

    plan, plan_teeth = _treatment_plan_teeth(db, treatment_plan_id) if treatment_plan_id else (None, [])

    balance = (
        balance_service.get_patient_balance(db, patient_id, tenant_id)
        if include_balance else None
    )

    return {
        "patient": patient,
        "office": office,
        "provider": provider,
        "account": account,
        "responsible_party": rp,
        "referred_by": referred_by,
        "next_appointment": next_appt,
        "next_appointment_provider": next_appt_provider,
        "last_appointment": last_appt,
        "last_appointment_provider": last_appt_provider,
        "treatment_plan": plan,
        "treatment_plan_teeth": plan_teeth,
        "balance": balance,
        "today": today,
        "timezone": tz_name,
    }


# ── LTR-17: which tier of the fallback chain actually answered ───────────────
def appointment_sources(ctx: dict[str, Any]) -> dict[str, str | None]:
    """Report where the appointment block's values came from.

    The LTR-13 chain is a real improvement over a blank doctor, but it can now
    print a provider with no connection to the visit — for a patient with no
    appointment rows at all, ``#APPT_PRDR#`` is simply the preferred provider.
    "Caught at the chair" only works if the person at the chair can see it, so
    the tier is reported rather than left implicit.

    Two separate answers because they can genuinely disagree: a last appointment
    whose ``provider_id`` no longer resolves gives ``appointment_source="last"``
    with ``appointment_provider_source="preferred"``.
    """
    if ctx.get("next_appointment"):
        appt_src = "next"
    elif ctx.get("last_appointment"):
        appt_src = "last"
    else:
        appt_src = None

    if ctx.get("next_appointment_provider"):
        prov_src = "next"
    elif ctx.get("last_appointment_provider"):
        prov_src = "last"
    elif ctx.get("provider"):
        prov_src = "preferred"
    else:
        prov_src = None

    return {"appointment_source": appt_src, "appointment_provider_source": prov_src}


def fallback_tokens(sources: dict[str, str | None]) -> dict[str, str]:
    """``{token: tier}`` for tokens that did **not** come from the ideal source.

    Only degraded resolutions are listed, so a non-empty map is exactly the set
    of values the preview should annotate. A token resolved from the upcoming
    appointment is not a fallback and never appears.
    """
    out: dict[str, str] = {}
    if sources.get("appointment_source") == "last":
        out["APPT_DATE"] = "last"
        out["APPT_DATETIME"] = "last"
    prov = sources.get("appointment_provider_source")
    if prov in ("last", "preferred"):
        out["APPT_PRDR"] = prov
    return out


# ── Token resolution ─────────────────────────────────────────────────────────
def resolve_merge_fields(ctx: dict[str, Any]) -> dict[str, str]:
    """Map every catalog token to its (unescaped) string value for this context.

    Fallbacks are deliberate and documented in the dev report (LTR-3): the
    provider letterhead and the marketing block fall back to the office, and the
    office corporate name falls back to the office name — a letter printing the
    office address is wrong, but a letter printing *nothing* is worse.
    """
    patient: Patient | None = ctx.get("patient")
    office: Office | None = ctx.get("office")
    provider: Provider | None = ctx.get("provider")
    account: AccountSettings | None = ctx.get("account")
    rp: ResponsibleParty | None = ctx.get("responsible_party")
    ref: Referral | None = ctx.get("referred_by")
    balance: dict | None = ctx.get("balance")
    teeth: list[str] = ctx.get("treatment_plan_teeth") or []
    today: date = ctx.get("today") or office_today(ctx.get("timezone"))

    # LTR-13: the appointment block means "the appointment this letter is
    # about". A consent form is printed at the chair, after the visit has
    # started, so there is no *upcoming* appointment — binding these to the
    # future alone printed "I hereby authorize Dr. ___" on a signed legal
    # document. Fall through: next appointment -> last appointment.
    appt: Appointment | None = ctx.get("next_appointment") or ctx.get("last_appointment")
    appt_prov: Provider | None = (
        ctx.get("next_appointment_provider")
        or ctx.get("last_appointment_provider")
        # Last resort: the patient's preferred provider. 15 templates use
        # #APPT_PRDR#, including consent forms, and a named doctor that might be
        # the wrong one is caught at the chair — a blank one is signed.
        or ctx.get("provider")
    )

    def _o(attr: str) -> str:
        return str(getattr(office, attr, None) or "") if office else ""

    # Provider letterhead, office fallback.
    prov_address = _street(getattr(provider, "address_line1", None), getattr(provider, "address_line2", None))
    prov_city = getattr(provider, "city", None) or ""
    prov_state = getattr(provider, "state", None) or ""
    prov_zip = getattr(provider, "zip", None) or ""
    prov_phone = getattr(provider, "phone", None) or ""
    if provider is None or not prov_address:
        prov_address = prov_address or _street(_o("address_line1"), _o("address_line2"))
        prov_city = prov_city or _o("city")
        prov_state = prov_state or _o("state")
        prov_zip = prov_zip or _o("zip")
    prov_phone = prov_phone or _o("phone")

    # Marketing block: account marketing -> account corporate -> office.
    mk_name = (getattr(account, "marketing_name", None)
               or getattr(office, "corporate_name", None)
               or _o("name"))
    mk_address = (getattr(account, "marketing_address_1", None)
                  or getattr(account, "corporate_address_1", None)
                  or _street(_o("address_line1"), _o("address_line2")))
    mk_city = (getattr(account, "marketing_city", None)
               or getattr(account, "corporate_city", None) or _o("city"))
    mk_state = (getattr(account, "marketing_state", None)
                or getattr(account, "corporate_state", None) or _o("state"))
    mk_zip = (getattr(account, "marketing_zip", None)
              or getattr(account, "corporate_zip", None) or _o("zip"))
    mk_phone = (getattr(account, "marketing_phone", None)
                or getattr(account, "phone", None) or _o("phone"))

    def _p(attr: str) -> str:
        return str(getattr(patient, attr, None) or "") if patient else ""

    def _rp(attr: str) -> str:
        return str(getattr(rp, attr, None) or "") if rp else ""

    # A self-guarantor has no responsible_parties row; the patient IS the account.
    rp_first = _rp("first_name") or _p("first_name")
    rp_last = _rp("last_name") or _p("last_name")
    rp_mid = _rp("middle_initial") or _p("middle_initial")
    rp_address = _street(getattr(rp, "address_line1", None), getattr(rp, "address_line2", None)) if rp \
        else _street(getattr(patient, "address_line1", None), getattr(patient, "address_line2", None))
    rp_city = _rp("city") or _p("city")
    rp_state = _rp("state") or _p("state")
    rp_zip = _rp("zip") or _p("zip")
    rp_email = _rp("email") or _p("email")

    provider_name = getattr(provider, "name", "") or _full_name(
        getattr(provider, "first_name", None), getattr(provider, "last_name", None)
    )

    values = {
        "PAT_ID": str(patient.id) if patient else "",
        "PAT_FIRST_NAME": _p("first_name"),
        "PAT_NAME_FIRST": _p("first_name"),
        "PAT_LAST_NAME": _p("last_name"),
        "PAT_MID_INITIAL": _p("middle_initial"),
        "PAT_BIRTHDATE": _date(getattr(patient, "dob", None)),
        "PAT_ADDRESS": _street(getattr(patient, "address_line1", None), getattr(patient, "address_line2", None)),
        "PAT_CITY": _p("city"),
        "PAT_STATE": _p("state"),
        "PAT_ZIP": _p("zip"),
        "PAT_EMAIL": _p("email"),
        "PAT_HOMEPHONE": _p("phone"),
        "PAT_CELLPHONE": _p("cell_phone"),
        "PAT_WORKPHONE": _p("work_phone"),
        "LASTVISIT_DATE": _date(
            getattr(patient, "last_visit", None)
            or getattr(ctx.get("last_appointment"), "date", None)
        ),
        "PAT_PREF_PROV": provider_name,
        "PAT_PREF_PROV_Address": prov_address,
        "PAT_PREF_PROV_CITY": prov_city,
        "PAT_PREF_PROV_STATE": prov_state,
        "PAT_PREF_PROV_ZIP": prov_zip,
        "PAT_PREF_PROV_PHONE": prov_phone,
        "DOC_LAST_NAME": (getattr(provider, "last_name", None) or _last_name_of(provider_name)),
        "PAT_REF_BY": (_full_name(getattr(ref, "first_name", None), getattr(ref, "last_name", None))
                       or getattr(ref, "practice_name", None) or _p("referred_by")),
        "PAT_REF_BY_ADDRESS": str(getattr(ref, "address", None) or ""),
        "PAT_REF_BY_CITY": str(getattr(ref, "city", None) or ""),
        "PAT_REF_BY_STATE": str(getattr(ref, "state", None) or ""),
        "PAT_REF_BY_ZIP": str(getattr(ref, "zip", None) or ""),
        "PAT_REF_TO": _p("referred_to"),
        "PAT_REF_TO_DATE": _date(getattr(patient, "referral_to_date", None)),
        "OFFICE_NAME": _o("name"),
        "OFFICE_CNAME": _o("corporate_name") or _o("name"),
        "OFFICE_ADDRESS": _street(_o("address_line1"), _o("address_line2")),
        "OFFICE_CITY": _o("city"),
        "OFFICE_STATE": _o("state"),
        "OFFICE_ZIP": _o("zip"),
        "OFFICE_PHONE1": _o("phone"),
        "OFFICE_EMAIL": _o("email"),
        "MARKET_NAME": str(mk_name or ""),
        "MARKET_ADDRESS": str(mk_address or ""),
        "MARKET_CITY": str(mk_city or ""),
        "MARKET_STATE": str(mk_state or ""),
        "MARKET_ZIP": str(mk_zip or ""),
        "MARKET_PHONE": str(mk_phone or ""),
        "RP_FIRST_NAME": rp_first,
        "RP_LAST_NAME": rp_last,
        "RP_MID_INITIAL": rp_mid,
        "RP_ADDRESS": rp_address,
        "RP_CITY": rp_city,
        "RP_STATE": rp_state,
        "RP_ZIP": rp_zip,
        "RP_EMAIL": rp_email,
        "RP_TOTAL_BAL": _money(balance.get("balance")) if balance else "",
        "APPT_DATE": _date(getattr(appt, "date", None)),
        "APPT_DATETIME": _datetime(
            getattr(appt, "date", None), getattr(appt, "start_time", None)
        ),
        "APPT_PRDR": (
            getattr(appt_prov, "name", "")
            or _full_name(
                getattr(appt_prov, "first_name", None), getattr(appt_prov, "last_name", None)
            )
        ) if appt_prov else "",
        "TODAY_DATE": _date(today),
        "TX_PLAN_TH_NUMBER": ", ".join(teeth),
    }
    return values


def render_body(body_html: str | None, values: dict[str, str]) -> tuple[str, list[str]]:
    """Substitute ``#TOKEN#`` placeholders, HTML-escaping every merged value.

    Returns ``(rendered_html, unresolved_tokens)``. A token is *unresolved* when
    it is unknown to the catalog or resolves to an empty value — either way the
    placeholder is replaced with nothing, never left visible to the patient, and
    the caller surfaces the list in the preview's "printed blank" warning.
    """
    unresolved: list[str] = []
    seen: set[str] = set()

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        value = values.get(token, "")
        if not value and token not in seen:
            seen.add(token)
            unresolved.append(token)
        return html.escape(value)

    rendered = _TOKEN_RE.sub(_sub, sanitize_html(body_html) or "")
    return rendered, unresolved


# ── Public operations ────────────────────────────────────────────────────────
def get_template(db: Session, tenant_id: int, template_id: int) -> LetterTemplate:
    tpl = db.execute(
        select(LetterTemplate).where(
            LetterTemplate.id == template_id, LetterTemplate.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if tpl is None:
        raise NotFoundError(f"Letter template '{template_id}' was not found")
    return tpl


#: LTR-15: which tokens ``signing_provider_id`` re-points. Deliberately just the
#: doctor *named in the body* — the ``PAT_PREF_PROV_*`` letterhead block is the
#: practice's return address and should not silently change because a different
#: dentist is chairside. Use ``overrides`` if you do want to move it too.
SIGNING_PROVIDER_TOKENS = ("APPT_PRDR", "DOC_LAST_NAME")


def apply_overrides(
    db: Session,
    tenant_id: int,
    values: dict[str, str],
    *,
    signing_provider_id: str | None = None,
    overrides: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Layer caller-supplied values over the resolved ones (LTR-15).

    Returns ``(values, applied, rejected)``. ``signing_provider_id`` is applied
    first so an explicit ``overrides`` entry always wins over it.

    Only catalog tokens are accepted — an unknown key is *reported*, not merged,
    because silently accepting one would let a typo look like it worked. The
    values themselves stay unescaped here; :func:`render_body` escapes every
    substitution, so a caller cannot inject markup this way.
    """
    applied: list[str] = []
    rejected: list[str] = []

    if signing_provider_id:
        provider = db.get(Provider, signing_provider_id)
        if provider is None or provider.tenant_id != tenant_id:
            raise NotFoundError(f"Provider '{signing_provider_id}' was not found")
        name = provider.name or _full_name(provider.first_name, provider.last_name)
        resolved = {
            "APPT_PRDR": name,
            "DOC_LAST_NAME": provider.last_name or _last_name_of(name),
        }
        for token in SIGNING_PROVIDER_TOKENS:
            values[token] = resolved[token]
            applied.append(token)

    for token, value in (overrides or {}).items():
        if token not in MERGE_FIELD_NAMES:
            rejected.append(token)
            continue
        values[token] = "" if value is None else str(value)
        if token not in applied:
            applied.append(token)

    return values, applied, rejected


def render_template(
    db: Session,
    tenant_id: int,
    *,
    template_id: int,
    patient_id: int,
    office_id: int | None = None,
    treatment_plan_id: str | None = None,
    signing_provider_id: str | None = None,
    overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
    """LTR-5: merge one template for one patient, server-side."""
    tpl = get_template(db, tenant_id, template_id)
    required = set(tokens_in(tpl.body_html))
    ctx = build_context(
        db, tenant_id, patient_id,
        office_id=office_id,
        treatment_plan_id=treatment_plan_id,
        # Only pay for the balance aggregate when the template actually needs it.
        include_balance=bool(required & BALANCE_TOKENS),
    )
    values = resolve_merge_fields(ctx)
    sources = appointment_sources(ctx)
    values, applied, rejected = apply_overrides(
        db, tenant_id, values,
        signing_provider_id=signing_provider_id, overrides=overrides,
    )
    # LTR-17: a token the caller supplied is not a fallback — its value came from
    # the dialog, not from the chain. Only report what this letter actually uses.
    fallbacks = {
        token: tier for token, tier in fallback_tokens(sources).items()
        if token in required and token not in applied
    }
    rendered, unresolved = render_body(tpl.body_html, values)
    return {
        "template_id": tpl.id,
        "patient_id": patient_id,
        # LTR-9: title is null on 103 of 153 migrated rows — name is the heading.
        "title": tpl.title or tpl.name,
        "letter_type": tpl.letter_type,
        "rendered_html": rendered,
        "unresolved_tokens": unresolved,
        "merge_fields": {k: v for k, v in values.items() if k in required},
        "unknown_tokens": sorted(required - MERGE_FIELD_NAMES),
        # LTR-15: what the caller changed, and which keys were not catalog tokens.
        "applied_overrides": sorted(applied),
        "rejected_overrides": sorted(rejected),
        # LTR-17: which tier of the appointment fallback chain answered, so the
        # preview can say "no appointment on file" instead of silently naming a doctor.
        "fallback_tokens": fallbacks,
        **sources,
        # LTR-14: the clock this render used, so the caller can stop second-guessing it.
        "timezone": ctx.get("timezone"),
        "today": ctx.get("today"),
    }


def run_batch(
    db: Session,
    tenant_id: int,
    *,
    template_id: int,
    patient_ids: list[int],
    office_id: int | None = None,
    store_html: bool = False,
    signing_provider_id: str | None = None,
    overrides: dict[str, str] | None = None,
    user_id: int | None = None,
) -> LetterBatchRun:
    """LTR-5: render one template across a patient list as a durable job.

    Runs inline and returns the completed run — the batches a practice actually
    sends (a collections queue, a recall sweep) are hundreds of rows, not
    millions, and an inline run means the caller gets a job id *and* a finished
    result without a worker tier. The row/item model is already the async shape,
    so moving the loop onto a queue later needs no contract change.

    One patient failing (deleted, wrong tenant, unresolvable office) records a
    ``failed`` item and the sweep continues — a single bad row must not lose the
    other 499 letters.
    """
    get_template(db, tenant_id, template_id)  # 404 before creating a run row
    if not patient_ids:
        raise ValidationError("patient_ids must not be empty", code="empty_batch")
    limit = settings.LETTERS_BATCH_MAX_PATIENTS
    if len(patient_ids) > limit:
        raise ValidationError(
            f"A batch run covers at most {limit} patients (got {len(patient_ids)})",
            code="batch_too_large",
        )

    run = LetterBatchRun(
        tenant_id=tenant_id, office_id=office_id, template_id=template_id,
        status="running", requested=len(patient_ids),
        options={
            "store_html": store_html,
            "signing_provider_id": signing_provider_id,
            "overrides": overrides or {},
        },
        created_by=user_id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    succeeded = failed = 0
    for patient_id in patient_ids:
        try:
            result = render_template(
                db, tenant_id, template_id=template_id,
                patient_id=patient_id, office_id=office_id,
                signing_provider_id=signing_provider_id, overrides=overrides,
            )
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the sweep
            failed += 1
            db.add(LetterBatchItem(
                batch_id=run.id, patient_id=patient_id, status="failed", error=str(exc)[:2000],
            ))
            continue
        succeeded += 1
        db.add(LetterBatchItem(
            batch_id=run.id, patient_id=patient_id, status="rendered",
            unresolved_tokens=result["unresolved_tokens"],
            rendered_html=result["rendered_html"] if store_html else None,
        ))

    run.processed = len(patient_ids)
    run.succeeded = succeeded
    run.failed = failed
    run.status = "completed" if failed == 0 else ("failed" if succeeded == 0 else "completed")
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


def get_batch(db: Session, tenant_id: int, batch_id: int) -> tuple[LetterBatchRun, list[LetterBatchItem]]:
    run = db.execute(
        select(LetterBatchRun).where(
            LetterBatchRun.id == batch_id, LetterBatchRun.tenant_id == tenant_id
        )
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Letter batch '{batch_id}' was not found")
    items = list(db.execute(
        select(LetterBatchItem).where(LetterBatchItem.batch_id == batch_id)
        .order_by(LetterBatchItem.id)
    ).scalars().all())
    return run, items


def list_batches(
    db: Session, tenant_id: int, *, template_id: int | None = None,
    office_id: int | None = None, page: int = 1, size: int = 20,
) -> tuple[list[LetterBatchRun], int]:
    clauses = [LetterBatchRun.tenant_id == tenant_id]
    if template_id is not None:
        clauses.append(LetterBatchRun.template_id == template_id)
    if office_id is not None:
        clauses.append(LetterBatchRun.office_id == office_id)
    total = db.execute(
        select(func.count()).select_from(LetterBatchRun).where(*clauses)
    ).scalar_one()
    rows = list(db.execute(
        select(LetterBatchRun).where(*clauses)
        .order_by(LetterBatchRun.id.desc())
        .offset((max(page, 1) - 1) * size).limit(size)
    ).scalars().all())
    return rows, total
