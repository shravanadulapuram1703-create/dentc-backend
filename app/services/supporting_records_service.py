"""Supporting-records readiness (PROC-7c / PROC-7d).

A procedure code can declare that a clinician must have certain *records* on
file before the charge is claimed — an attachment, a perio chart, a photo, a
radiograph, missing-tooth information (``procedure_codes.requires_*``, PROC-7a).
The flags say *that* a record is required; this module is the one place that
says what **satisfies** each, so the Add Procedure pop-up, the treatment-plan
post, the claim fill-out and the submit path all judge the same evidence.

Enforcement point (PROC-7c, decided): **claim submission**, not posting. The
record is normally captured *after* the chair — the x-ray is taken, the
narrative written, the photo uploaded — so a 422 on ``POST patient_procedures``
would block the very charge the record is about. Posting and treatment-plan
items are therefore advisory (the readiness endpoints are the checklist), and
``POST /insurance-claims/{id}/submit`` is a 422 ``supporting_records_missing``
while any procedure on the claim still lacks a record, with
``allow_missing_records`` as the override (warning-and-override, the same
shape as every other guard in this codebase — a carrier may accept a claim the
practice knows is thin, and refusing outright would push staff to un-flag the
code). Claim *creation* is deliberately not guarded: the frontend's Create
Claim is ``POST /insurance-claims`` followed by ``PATCH /patient-procedures``
per line, and a 422 on the PATCH would leave a half-built claim.

What counts as "on file" (also published at ``/metadata/procedure-entry-rules``):

* ``requires_attachment`` — a ``patient_documents`` row linked to the procedure
  (``procedure_id``) or its claim (``claim_id``), or a ``claim_attachments`` row
  on the claim. Only judgeable once the charge exists — before that it is
  reported as *deferred*, never as missing, so the pop-up can say "will need an
  attachment" without claiming it is already late.
* ``requires_perio_chart`` — a non-voided ``perio_exams`` row dated on/before
  the date of service, and, when ``SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS``
  (or ``?perio_max_age_months=``) is set, not older than that.
* ``requires_photo`` — a ``patient_documents`` row typed ``PH`` (Patient Photo),
  or a DICOM study whose modality is a photographic one (``XC``/``ES``).
* ``requires_xray`` — a ``patient_documents`` row typed ``XR``, or a DICOM
  study dated on/before the DOS with a radiographic modality (``IO``, ``PX``,
  ``DX``, ``CR``, ``RG``, ``XA``, ``RF``, ``CT``). ``?strict_tooth=true`` narrows
  to instances whose ``tooth_numbers`` include the procedure's tooth.
* ``requires_missing_tooth_info`` — an active ``chart_conditions`` row charted
  as missing/extracted/pontic **with** an ``activity_date`` (the date of loss),
  or a posted, non-void extraction charge (``D7111``–``D7251``) for the patient —
  its date of service *is* the extraction date. Tooth is not matched: the
  missing tooth is, by definition, not the tooth being restored.

Two things deliberately do **not** count. Document upload time is not capture
date, so ``patient_documents`` are never filtered by DOS. And the legacy
``image_details`` rows carry no type at all — they are reported under
``untyped_legacy_images`` and never satisfy a rule: "unknown" and "on file" are
different answers.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.db.models import (
    ChartCondition,
    ClaimAttachment,
    DicomInstance,
    DicomSeries,
    DicomStudy,
    ImageDetail,
    ImageGroup,
    InsuranceClaim,
    Patient,
    PatientDocument,
    PatientProcedure,
    PerioExam,
    ProcedureCode,
)
from app.services.procedure_rules_service import SUPPORTING_RECORD_FLAGS, parse_tooth

# ── vocabulary ───────────────────────────────────────────────────────────────
#: ``patient_documents.document_type`` codes (NOTE-DOC-4 seed) that are a photo
#: / a radiograph.
PHOTO_DOCUMENT_TYPES: frozenset[str] = frozenset({"PH"})
XRAY_DOCUMENT_TYPES: frozenset[str] = frozenset({"XR"})
#: DICOM modality codes. Intraoral cameras export ``XC`` (external-camera
#: photography); the Apteryx archive's radiographs are ``IO`` / ``PX``.
PHOTO_MODALITIES: frozenset[str] = frozenset({"XC", "ES"})
RADIOGRAPH_MODALITIES: frozenset[str] = frozenset({"IO", "PX", "DX", "CR", "RG", "XA", "RF", "CT"})
#: ``chart_conditions.condition_code`` glyph keys that chart a tooth as gone.
MISSING_CONDITION_CODES: frozenset[str] = frozenset({
    "MISSING", "FND-MISSING", "EXTRACTED", "EXTRACTION", "BRIDGE_PONTIC", "PONTIC",
})
#: CDT extraction codes — a posted one records the extraction date.
EXTRACTION_CODES: frozenset[str] = frozenset({
    "D7111", "D7140", "D7210", "D7220", "D7230", "D7240", "D7241", "D7250", "D7251",
})
#: Claim-attachment catalog code (INS-PAY-8) each flag asks for, for the ADA
#: Enclosures box (PROC-7d).
FLAG_ATTACHMENT_TYPE: dict[str, str] = {
    "requires_xray": "XRAY",
    "requires_photo": "PHOTO",
    "requires_perio_chart": "PERIO",
    "requires_attachment": "NARRATIVE",
}

#: The rule table. ``key`` is the short name on the wire (``requires`` /
#: ``satisfied`` / ``missing`` lists), ``stage`` says when it can first be judged.
RULES: dict[str, dict[str, str]] = {
    "requires_attachment": {
        "key": "attachment", "label": "Attachments Required", "stage": "claim",
        "error_code": "attachment_required",
        "satisfied_when": "a patient document is linked to the procedure or its claim, "
                          "or the claim carries a claim attachment",
    },
    "requires_perio_chart": {
        "key": "perio_chart", "label": "Perio Chart Required", "stage": "post",
        "error_code": "perio_chart_required",
        "satisfied_when": "a non-voided perio exam is dated on/before the date of service "
                          "(and within perio_max_age_months when set)",
    },
    "requires_photo": {
        "key": "photo", "label": "Photo Required", "stage": "post",
        "error_code": "photo_required",
        "satisfied_when": "a patient document typed PH, or a DICOM study with a photographic "
                          "modality (XC/ES), is on file",
    },
    "requires_xray": {
        "key": "xray", "label": "X-Ray Required", "stage": "post",
        "error_code": "xray_required",
        "satisfied_when": "a patient document typed XR, or a DICOM study dated on/before the "
                          "date of service with a radiographic modality, is on file "
                          "(strict_tooth narrows to instances tagged with the tooth)",
    },
    "requires_missing_tooth_info": {
        "key": "missing_tooth_info", "label": "Missing Tooth Info Required", "stage": "post",
        "error_code": "missing_tooth_info_required",
        "satisfied_when": "a charted missing/extracted/pontic condition with an activity date, "
                          "or a posted extraction charge, exists for the patient",
    },
}
KEY_TO_FLAG: dict[str, str] = {r["key"]: flag for flag, r in RULES.items()}


def rules_catalog() -> list[dict[str, Any]]:
    """Published on ``/metadata/procedure-entry-rules`` -> ``supporting_records.rules``."""
    return [{"flag": flag, **spec} for flag, spec in RULES.items()]


# ── evidence (patient-level queries cached per evaluation) ───────────────────
class _Evidence:
    """Lazy, per-patient evidence cache so a claim with eight lines runs each
    patient-level query once rather than eight times."""

    def __init__(self, db: Session, tenant_id: int, patient_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.patient_id = patient_id
        self._perio: list[tuple[int, date]] | None = None
        self._doc_types: dict[str, int] | None = None
        self._dicom: list[tuple[int, date | None, set[str]]] | None = None
        self._legacy_images: int | None = None
        self._missing: dict[str, Any] | None = None

    # perio ------------------------------------------------------------------
    def perio_exams(self) -> list[tuple[int, date]]:
        if self._perio is None:
            self._perio = [
                (int(i), d) for i, d in self.db.execute(
                    select(PerioExam.id, PerioExam.exam_date)
                    .where(PerioExam.patient_id == self.patient_id,
                           PerioExam.is_voided.is_(False))
                    .order_by(PerioExam.exam_date.desc(), PerioExam.id.desc())
                ).all()
            ]
        return self._perio

    # documents --------------------------------------------------------------
    def document_types(self) -> dict[str, int]:
        """Active document count per ``document_type`` (``""`` = untyped)."""
        if self._doc_types is None:
            rows = self.db.execute(
                select(PatientDocument.document_type, func.count())
                .where(PatientDocument.tenant_id == self.tenant_id,
                       PatientDocument.patient_id == self.patient_id,
                       PatientDocument.is_deleted.is_(False))
                .group_by(PatientDocument.document_type)
            ).all()
            self._doc_types = {}
            for t, n in rows:
                key = (t or "").strip().upper()
                self._doc_types[key] = self._doc_types.get(key, 0) + int(n)
        return self._doc_types

    def documents_of(self, types: frozenset[str]) -> int:
        return sum(n for t, n in self.document_types().items() if t in types)

    # DICOM ------------------------------------------------------------------
    def dicom_studies(self) -> list[tuple[int, date | None, set[str]]]:
        """(study_id, study_date, modalities) per active study — the study's own
        ``modalities`` list unioned with its series' ``modality`` so either
        being filled is enough."""
        if self._dicom is None:
            rows = self.db.execute(
                select(DicomStudy.id, DicomStudy.study_date, DicomStudy.modalities,
                       DicomSeries.modality)
                .outerjoin(DicomSeries, (DicomSeries.study_id == DicomStudy.id)
                           & DicomSeries.is_deleted.is_(False))
                .where(DicomStudy.tenant_id == self.tenant_id,
                       DicomStudy.patient_id == self.patient_id,
                       DicomStudy.is_deleted.is_(False))
            ).all()
            by_id: dict[int, tuple[int, date | None, set[str]]] = {}
            for sid, sdate, mods, series_mod in rows:
                entry = by_id.setdefault(int(sid), (int(sid), sdate, set()))
                for m in (mods or []):
                    if m:
                        entry[2].add(str(m).upper())
                if series_mod:
                    entry[2].add(str(series_mod).upper())
            self._dicom = list(by_id.values())
        return self._dicom

    def dicom_studies_with(
        self, modalities: frozenset[str], on_or_before: date | None,
    ) -> list[dict]:
        out = []
        for sid, sdate, mods in self.dicom_studies():
            if not (mods & modalities):
                continue
            if on_or_before is not None and sdate is not None and sdate > on_or_before:
                continue
            out.append({"study_id": sid, "study_date": sdate, "modalities": sorted(mods)})
        return out

    def instances_tagged_with(self, study_ids: list[int], tooth: str) -> int:
        if not study_ids:
            return 0
        rows = self.db.execute(
            select(DicomInstance.tooth_numbers)
            .join(DicomSeries, DicomSeries.id == DicomInstance.series_id)
            .where(DicomSeries.study_id.in_(study_ids),
                   DicomInstance.is_deleted.is_(False),
                   DicomInstance.tooth_numbers.is_not(None))
        ).scalars().all()
        want = tooth.upper()
        return sum(1 for teeth in rows if any(str(t).upper() == want for t in (teeth or [])))

    def legacy_images(self) -> int:
        if self._legacy_images is None:
            self._legacy_images = int(self.db.execute(
                select(func.count()).select_from(ImageDetail)
                .join(ImageGroup, ImageGroup.id == ImageDetail.image_group_id)
                .where(ImageGroup.patient_id == self.patient_id,
                       ImageDetail.tenant_id == self.tenant_id,
                       ImageDetail.is_deleted.is_(False),
                       ImageGroup.is_deleted.is_(False))
            ).scalar_one())
        return self._legacy_images

    # missing tooth ----------------------------------------------------------
    def missing_tooth_info(self) -> dict[str, Any]:
        if self._missing is None:
            charted = self.db.execute(
                select(ChartCondition.tooth, ChartCondition.activity_date,
                       ChartCondition.condition_code)
                .where(ChartCondition.patient_id == self.patient_id,
                       ChartCondition.is_inactive.is_(False),
                       func.upper(ChartCondition.condition_code).in_(sorted(MISSING_CONDITION_CODES)))
            ).all()
            extractions = self.db.execute(
                select(PatientProcedure.tooth, PatientProcedure.date_of_service,
                       PatientProcedure.procedure_code)
                .where(PatientProcedure.patient_id == self.patient_id,
                       PatientProcedure.is_void.is_(False),
                       PatientProcedure.is_archived.is_(False),
                       PatientProcedure.procedure_code.in_(sorted(EXTRACTION_CODES)))
            ).all()
            self._missing = {
                "charted_missing": [
                    {"tooth": t, "date": d, "condition_code": c}
                    for t, d, c in charted if d is not None
                ],
                "undated_missing": sum(1 for _t, d, _c in charted if d is None),
                "extractions": [
                    {"tooth": t, "date": d, "procedure_code": c} for t, d, c in extractions
                ],
            }
        return self._missing


# ── per-flag judgement ───────────────────────────────────────────────────────
def _months_before(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 - months, 12)
    year, month = d.year + y, m + 1
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    days_in_month = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, days_in_month))


def _judge(
    flag: str, ev: _Evidence, *, tooth: str | None, dos: date | None,
    procedure_id: str | None, claim_id: str | None,
    perio_max_age_months: int | None, strict_tooth: bool,
) -> tuple[str, dict[str, Any]]:
    """-> (``satisfied`` | ``missing`` | ``deferred``, evidence)."""
    db = ev.db
    if flag == "requires_attachment":
        if procedure_id is None and claim_id is None:
            return "deferred", {"deferred": True,
                                "reason": "nothing to attach to until the charge is posted"}
        clauses = [PatientDocument.tenant_id == ev.tenant_id, PatientDocument.is_deleted.is_(False)]
        links = []
        if procedure_id is not None:
            links.append(PatientDocument.procedure_id == procedure_id)
        if claim_id is not None:
            links.append(PatientDocument.claim_id == claim_id)
        docs = int(db.execute(
            select(func.count()).select_from(PatientDocument).where(*clauses, or_(*links))
        ).scalar_one())
        claim_atts = 0
        if claim_id is not None:
            claim_atts = int(db.execute(
                select(func.count()).select_from(ClaimAttachment)
                .where(ClaimAttachment.claim_id == claim_id, ClaimAttachment.is_deleted.is_(False))
            ).scalar_one())
        evidence = {"documents": docs, "claim_attachments": claim_atts}
        return ("satisfied" if docs + claim_atts > 0 else "missing"), evidence

    if flag == "requires_perio_chart":
        exams = ev.perio_exams()
        eligible = [(i, d) for i, d in exams if dos is None or d <= dos]
        floor = None
        if perio_max_age_months is not None and dos is not None:
            floor = _months_before(dos, perio_max_age_months)
            eligible = [(i, d) for i, d in eligible if d >= floor]
        latest = eligible[0] if eligible else None
        evidence = {
            "exams_on_file": len(exams),
            "latest_exam_id": latest[0] if latest else None,
            "latest_exam_date": latest[1] if latest else None,
            "max_age_months": perio_max_age_months,
            "not_before": floor,
        }
        return ("satisfied" if latest else "missing"), evidence

    if flag == "requires_photo":
        docs = ev.documents_of(PHOTO_DOCUMENT_TYPES)
        studies = ev.dicom_studies_with(PHOTO_MODALITIES, None)
        evidence = {"documents": docs, "dicom_studies": len(studies),
                    "untyped_legacy_images": ev.legacy_images()}
        return ("satisfied" if docs + len(studies) > 0 else "missing"), evidence

    if flag == "requires_xray":
        docs = ev.documents_of(XRAY_DOCUMENT_TYPES)
        studies = ev.dicom_studies_with(RADIOGRAPH_MODALITIES, dos)
        tagged = None
        real_tooth = None
        if tooth:
            parsed = parse_tooth(tooth)
            if parsed is not None and not parsed.is_quadrant:
                real_tooth = parsed.raw
        if real_tooth:
            tagged = ev.instances_tagged_with([s["study_id"] for s in studies], real_tooth)
        evidence = {
            "documents": docs, "dicom_studies": len(studies),
            "latest_study_date": max(
                (s["study_date"] for s in studies if s["study_date"]), default=None),
            "tooth": real_tooth, "tooth_tagged_instances": tagged, "strict_tooth": strict_tooth,
            "untyped_legacy_images": ev.legacy_images(),
        }
        if strict_tooth and real_tooth:
            ok = (tagged or 0) > 0
        else:
            ok = docs + len(studies) > 0
        return ("satisfied" if ok else "missing"), evidence

    if flag == "requires_missing_tooth_info":
        info = ev.missing_tooth_info()
        ok = bool(info["charted_missing"] or info["extractions"])
        return ("satisfied" if ok else "missing"), dict(info)

    raise KeyError(flag)


# ── public API ───────────────────────────────────────────────────────────────
def _code_row(db: Session, code: str) -> ProcedureCode:
    row = db.get(ProcedureCode, code)
    if row is None:
        raise NotFoundError(f"ProcedureCode '{code}' was not found")
    return row


def _require_patient(db: Session, patient_id: int, tenant_id: int) -> Patient:
    p = db.execute(
        select(Patient).where(Patient.id == patient_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if p is None:
        raise NotFoundError(f"Patient '{patient_id}' was not found")
    return p


def _evaluate(
    ev: _Evidence, code_row: ProcedureCode, *, tooth: str | None, dos: date | None,
    procedure_id: str | None, claim_id: str | None,
    perio_max_age_months: int | None, strict_tooth: bool,
) -> dict[str, Any]:
    if perio_max_age_months is None:
        perio_max_age_months = settings.SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS
    requires: list[str] = []
    satisfied: list[str] = []
    missing: list[str] = []
    deferred: list[str] = []
    evidence: dict[str, Any] = {}
    rules: dict[str, Any] = {}
    buckets = {"satisfied": satisfied, "missing": missing, "deferred": deferred}
    for flag in SUPPORTING_RECORD_FLAGS:
        if not getattr(code_row, flag, False):
            continue
        key = RULES[flag]["key"]
        requires.append(key)
        rules[key] = {k: RULES[flag][k] for k in ("label", "stage", "satisfied_when", "error_code")}
        state, ev_block = _judge(
            flag, ev, tooth=tooth, dos=dos, procedure_id=procedure_id, claim_id=claim_id,
            perio_max_age_months=perio_max_age_months, strict_tooth=strict_tooth,
        )
        evidence[key] = ev_block
        buckets[state].append(key)
    return {
        "patient_id": ev.patient_id,
        "procedure_code": code_row.code,
        "tooth": tooth,
        "date_of_service": dos,
        "procedure_id": procedure_id,
        "claim_id": claim_id,
        "requires": requires,
        "satisfied": satisfied,
        "missing": missing,
        "deferred": deferred,
        "ready": not missing,
        "evidence": evidence,
        "rules": rules,
    }


def procedure_readiness(
    db: Session, tenant_id: int, patient_id: int, *, procedure_code: str,
    tooth: str | None = None, date_of_service: date | None = None,
    perio_max_age_months: int | None = None, strict_tooth: bool = False,
) -> dict[str, Any]:
    """The pre-post checklist: "if I post this code on this tooth today, what is
    already on file?" ``requires_attachment`` comes back *deferred* here."""
    _require_patient(db, patient_id, tenant_id)
    code_row = _code_row(db, procedure_code)
    ev = _Evidence(db, tenant_id, patient_id)
    return _evaluate(
        ev, code_row, tooth=tooth, dos=date_of_service, procedure_id=None, claim_id=None,
        perio_max_age_months=perio_max_age_months, strict_tooth=strict_tooth,
    )


def _get_procedure(db: Session, procedure_id: str, tenant_id: int) -> PatientProcedure:
    row = db.execute(
        select(PatientProcedure).join(Patient, Patient.id == PatientProcedure.patient_id)
        .where(PatientProcedure.id == procedure_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"PatientProcedure '{procedure_id}' was not found")
    return row


def posted_procedure_readiness(
    db: Session, tenant_id: int, procedure_id: str, *,
    perio_max_age_months: int | None = None, strict_tooth: bool = False,
    _ev: _Evidence | None = None, _proc: PatientProcedure | None = None,
) -> dict[str, Any]:
    """Readiness of a posted charge — the tooth/DOS/claim come from the row."""
    proc = _proc or _get_procedure(db, procedure_id, tenant_id)
    code_row = _code_row(db, proc.procedure_code)
    ev = _ev or _Evidence(db, tenant_id, proc.patient_id)
    return _evaluate(
        ev, code_row, tooth=proc.tooth, dos=proc.date_of_service, procedure_id=proc.id,
        claim_id=proc.claim_id, perio_max_age_months=perio_max_age_months,
        strict_tooth=strict_tooth,
    )


def _get_claim(db: Session, claim_id: str, tenant_id: int) -> InsuranceClaim:
    row = db.execute(
        select(InsuranceClaim).join(Patient, Patient.id == InsuranceClaim.patient_id)
        .where(InsuranceClaim.id == claim_id, Patient.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"InsuranceClaim '{claim_id}' was not found")
    return row


def _enclosures(db: Session, claim: InsuranceClaim, flags_on_claim: set[str]) -> dict[str, Any]:
    """PROC-7d: the ADA claim-form *Enclosures* box, derived — radiograph /
    oral-image / model counts from what is actually attached, plus which
    attachment types the claim's codes ask for. There is no fill-out column to
    persist this on yet (CLM-FO-*), so the fill-out modal reads it from here."""
    att_rows = db.execute(
        select(ClaimAttachment.attachment_type, func.count())
        .where(ClaimAttachment.claim_id == claim.id, ClaimAttachment.is_deleted.is_(False))
        .group_by(ClaimAttachment.attachment_type)
    ).all()
    doc_rows = db.execute(
        select(PatientDocument.document_type, func.count())
        .where(PatientDocument.claim_id == claim.id, PatientDocument.is_deleted.is_(False))
        .group_by(PatientDocument.document_type)
    ).all()
    by_type: dict[str, int] = {}
    for t, n in att_rows:
        code = (t or "OTHER").upper()
        by_type[code] = by_type.get(code, 0) + int(n)
    doc_map = {"XR": "XRAY", "PH": "PHOTO", "TP": "TXPLAN", "EOB": "EOB", "RF": "REFERRAL"}
    for t, n in doc_rows:
        code = doc_map.get((t or "").upper(), "OTHER")
        by_type[code] = by_type.get(code, 0) + int(n)
    required = sorted({
        FLAG_ATTACHMENT_TYPE[f] for f in flags_on_claim if f in FLAG_ATTACHMENT_TYPE
    })
    return {
        "radiographs": by_type.get("XRAY", 0),
        "oral_images": by_type.get("PHOTO", 0),
        "models": 0,  # no model/impression attachment type exists in the catalog
        "narratives": by_type.get("NARRATIVE", 0),
        "perio_charts": by_type.get("PERIO", 0),
        "other": sum(n for t, n in by_type.items()
                     if t not in ("XRAY", "PHOTO", "NARRATIVE", "PERIO")),
        "attachments_enclosed": sum(by_type.values()) > 0,
        "required_attachment_types": required,
        "missing_attachment_types": [t for t in required if by_type.get(t, 0) == 0],
    }


def claim_readiness(
    db: Session, tenant_id: int, claim_id: str, *,
    perio_max_age_months: int | None = None, strict_tooth: bool = False,
    _claim: InsuranceClaim | None = None,
) -> dict[str, Any]:
    """Every non-void procedure on the claim judged against its code's flags,
    flattened ``missing`` for the 422 body, and the derived Enclosures block."""
    claim = _claim or _get_claim(db, claim_id, tenant_id)
    procs = list(db.execute(
        select(PatientProcedure)
        .where(PatientProcedure.claim_id == claim.id, PatientProcedure.is_void.is_(False))
        .order_by(PatientProcedure.date_of_service, PatientProcedure.id)
    ).scalars().all())
    ev = _Evidence(db, tenant_id, claim.patient_id)
    per_proc: list[dict[str, Any]] = []
    flat_missing: list[dict[str, Any]] = []
    flags_on_claim: set[str] = set()
    code_rows: dict[str, ProcedureCode] = {}
    for proc in procs:
        code_row = code_rows.get(proc.procedure_code)
        if code_row is None:
            code_row = code_rows[proc.procedure_code] = _code_row(db, proc.procedure_code)
        flags_on_claim.update(f for f in SUPPORTING_RECORD_FLAGS if getattr(code_row, f, False))
        result = posted_procedure_readiness(
            db, tenant_id, proc.id, perio_max_age_months=perio_max_age_months,
            strict_tooth=strict_tooth, _ev=ev, _proc=proc,
        )
        per_proc.append(result)
        for key in result["missing"]:
            flat_missing.append({
                "procedure_id": proc.id, "procedure_code": proc.procedure_code,
                "tooth": proc.tooth,
                # ISO string: this list is also the 422 body, which is plain json.dumps.
                "date_of_service": (proc.date_of_service.isoformat()
                                    if proc.date_of_service else None),
                "record": key, "code": RULES[KEY_TO_FLAG[key]]["error_code"],
            })
    return {
        "claim_id": claim.id,
        "claim_number": claim.claim_number,
        "patient_id": claim.patient_id,
        "status": claim.status,
        "ready": not flat_missing,
        "enforced_on_submit": bool(settings.SUPPORTING_RECORDS_ENFORCE_ON_SUBMIT),
        "procedures": per_proc,
        "missing": flat_missing,
        "enclosures": _enclosures(db, claim, flags_on_claim),
    }


def assert_claim_ready(
    db: Session, tenant_id: int, claim: InsuranceClaim, *, allow_missing_records: bool = False,
) -> bool:
    """Submit-time gate. Returns True when the check found missing records but
    the caller overrode it (so the submit result can say so); False when nothing
    was missing or enforcement is off. Raises 422 ``supporting_records_missing``
    otherwise."""
    if not settings.SUPPORTING_RECORDS_ENFORCE_ON_SUBMIT:
        return False
    report = claim_readiness(db, tenant_id, claim.id, _claim=claim)
    if report["ready"]:
        return False
    if allow_missing_records:
        return True
    raise ValidationError(
        "One or more procedures on this claim require a supporting record that is not on file",
        details={
            "code": "supporting_records_missing",
            "claim_id": claim.id,
            "missing": report["missing"],
            "hint": "Attach / capture the listed records, or resubmit with "
                    "allow_missing_records=true to send the claim anyway.",
        },
    )
