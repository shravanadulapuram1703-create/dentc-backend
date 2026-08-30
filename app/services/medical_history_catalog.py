"""MH-1: the Medical Alerts / Dental Questionnaire / Medical Questionnaire
catalogs, and the ``key1`` code convention that binds an answer to a catalog row.

Why this module exists
----------------------
``definition_groups`` held only stray test rows for all three ``group_type``s
(``MEDALERT_TEST``, ``DENTQUEST_TEST``, ``MEDQUEST_TEST``), each with fewer than
ten definitions — so the frontend's ``MIN_TENANT_CATALOG_ITEMS`` guard rejected
them and rendered its own verbatim legacy transcription instead.

That makes seeding a **one-way door**: answers are keyed by a code the frontend
derives from the label (``toCode("Latex Rubber") -> "latex_rubber"``), so the
moment a tenant catalog passes the size guard the frontend switches to it, and
any label whose derived code differs orphans every already-answered row. The
code derivation therefore lives here, server-side, as :func:`to_code` — the same
algorithm on both sides is what keeps the two halves from drifting.

``key2`` carries the input kind (``text``/``date``/``textarea``; **null means
Yes/No**, which is what the frontend already assumes) and is mirrored into
``definitions.input_type``. ``section`` drives the collapse/expand grouping.

The bundled catalogs below are a transcription of the legacy Denticon lists.
``scripts/seed_medical_history_catalogs.py`` seeds them, but also takes
``--from-json`` so the frontend's ``legacyCatalogs.ts`` can be handed over
verbatim and used as the source of truth instead — which is the safer route,
because a label that differs by one word silently orphans answers.

**MH-11:** the legacy Medical Questionnaire's Emergency Contact block is
deliberately *absent* from ``MEDQUEST`` here. ``patient_emergency_contacts`` is
the authoritative store (it is what the rest of the app reads); duplicating the
three questions into the questionnaire is what made the two drift.
"""

from __future__ import annotations

import re
from typing import Any

# definition_groups.group_type values, and the group_code we seed per type.
ALERT_GROUP_TYPE = "MEDALERT"
DENTAL_GROUP_TYPE = "DENTQUEST"
MEDICAL_GROUP_TYPE = "MEDQUEST"

GROUP_TYPES: tuple[str, ...] = (ALERT_GROUP_TYPE, DENTAL_GROUP_TYPE, MEDICAL_GROUP_TYPE)

#: questionnaire_type on ``patient_questionnaire_responses`` -> catalog group type
QUESTIONNAIRE_GROUP_TYPES: dict[str, str] = {
    "dental": DENTAL_GROUP_TYPE,
    "medical": MEDICAL_GROUP_TYPE,
}

#: Input kinds a catalog row may declare in ``key2``. Anything else (including
#: null, the common case) means a Yes/No control.
INPUT_KINDS: tuple[str, ...] = ("text", "textarea", "date", "number")

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def to_code(label: str) -> str:
    """``"Latex Rubber" -> "latex_rubber"``.

    The frontend derives an answer's ``alert_code``/``question_code`` from the
    label this way. Seeding ``key1`` with anything else orphans every answered
    row, so the derivation is published here and used by the seeder, the
    composite write and ``GET /metadata/medical-history-rules``.
    """
    return _NON_ALNUM.sub("_", (label or "").strip().lower()).strip("_")


def _item(label: str, *, section: str | None = None, kind: str | None = None) -> dict[str, Any]:
    return {"code": to_code(label), "label": label, "section": section, "input_kind": kind}


# ── Medical Alerts (MEDALERT) ────────────────────────────────────────────────
# Sections mirror the legacy screen's collapsible blocks. ``no_known_allergies``
# and ``no_change_since_last_recorded`` are the two rows MH-12's contradiction
# rules key off, so their codes are also named in ``medical_history_rules``.
ALERT_CATALOG: tuple[dict[str, Any], ...] = (
    _item("No Known Allergies", section="Allergic To"),
    _item("Aspirin", section="Allergic To"),
    _item("Codeine", section="Allergic To"),
    _item("Penicillin", section="Allergic To"),
    _item("Erythromycin", section="Allergic To"),
    _item("Tetracycline", section="Allergic To"),
    _item("Sulfa Drugs", section="Allergic To"),
    _item("Local Anesthetics", section="Allergic To"),
    _item("Barbiturates", section="Allergic To"),
    _item("Sedatives", section="Allergic To"),
    _item("Iodine", section="Allergic To"),
    _item("Latex Rubber", section="Allergic To"),
    _item("Metals", section="Allergic To"),
    _item("Acrylic", section="Allergic To"),
    _item("Nuts", section="Allergic To"),
    _item("Eggs", section="Allergic To"),
    _item("Other Allergies", section="Allergic To", kind="text"),
    _item("Anemia", section="Medical Conditions"),
    _item("Angina", section="Medical Conditions"),
    _item("Arthritis", section="Medical Conditions"),
    _item("Artificial Heart Valve", section="Medical Conditions"),
    _item("Artificial Joint", section="Medical Conditions"),
    _item("Asthma", section="Medical Conditions"),
    _item("Bisphosphonate Therapy", section="Medical Conditions"),
    _item("Bleeding Disorder", section="Medical Conditions"),
    _item("Blood Transfusion", section="Medical Conditions"),
    _item("Cancer", section="Medical Conditions"),
    _item("Chemotherapy", section="Medical Conditions"),
    _item("Chest Pain", section="Medical Conditions"),
    _item("COPD", section="Medical Conditions"),
    _item("Cortisone Treatment", section="Medical Conditions"),
    _item("Diabetes", section="Medical Conditions"),
    _item("Dizziness", section="Medical Conditions"),
    _item("Drug or Alcohol Use", section="Medical Conditions"),
    _item("Emphysema", section="Medical Conditions"),
    _item("Epilepsy or Seizures", section="Medical Conditions"),
    _item("Fainting Spells", section="Medical Conditions"),
    _item("Glaucoma", section="Medical Conditions"),
    _item("Acid Reflux", section="Medical Conditions"),
    _item("Frequent Headaches", section="Medical Conditions"),
    _item("Heart Attack", section="Medical Conditions"),
    _item("Heart Murmur", section="Medical Conditions"),
    _item("Heart Pacemaker", section="Medical Conditions"),
    _item("Heart Surgery", section="Medical Conditions"),
    _item("Hemophilia", section="Medical Conditions"),
    _item("Hepatitis A", section="Medical Conditions"),
    _item("Hepatitis B", section="Medical Conditions"),
    _item("Hepatitis C", section="Medical Conditions"),
    _item("High Blood Pressure", section="Medical Conditions"),
    _item("HIV or AIDS", section="Medical Conditions"),
    _item("Hives or Rash", section="Medical Conditions"),
    _item("Jaundice", section="Medical Conditions"),
    _item("Kidney Disease", section="Medical Conditions"),
    _item("Liver Disease", section="Medical Conditions"),
    _item("Low Blood Pressure", section="Medical Conditions"),
    _item("Lung Disease", section="Medical Conditions"),
    _item("Mitral Valve Prolapse", section="Medical Conditions"),
    _item("Nervous Disorders", section="Medical Conditions"),
    _item("Organ Transplant", section="Medical Conditions"),
    _item("Osteoporosis", section="Medical Conditions"),
    _item("Psychiatric Care", section="Medical Conditions"),
    _item("Radiation Treatment", section="Medical Conditions"),
    _item("Recent Hospitalization", section="Medical Conditions"),
    _item("Recent Weight Loss", section="Medical Conditions"),
    _item("Respiratory Problems", section="Medical Conditions"),
    _item("Rheumatic Fever", section="Medical Conditions"),
    _item("Rheumatism", section="Medical Conditions"),
    _item("Scarlet Fever", section="Medical Conditions"),
    _item("Shortness of Breath", section="Medical Conditions"),
    _item("Sickle Cell Disease", section="Medical Conditions"),
    _item("Sinus Trouble", section="Medical Conditions"),
    _item("Sleep Apnea", section="Medical Conditions"),
    _item("Stomach Ulcers", section="Medical Conditions"),
    _item("Stroke", section="Medical Conditions"),
    _item("Swelling of Limbs", section="Medical Conditions"),
    _item("Thyroid Problem", section="Medical Conditions"),
    _item("Tobacco Use", section="Medical Conditions"),
    _item("Tonsillitis", section="Medical Conditions"),
    _item("Tuberculosis", section="Medical Conditions"),
    _item("Venereal Disease", section="Medical Conditions"),
    _item("Pregnant", section="Women Only"),
    _item("Due Date", section="Women Only", kind="date"),
    _item("Nursing", section="Women Only"),
    _item("Taking Birth Control Pills", section="Women Only"),
    _item("Premedication Required", section="Other"),
    _item("Currently Taking Medications", section="Other", kind="textarea"),
    _item("Physician Name", section="Other", kind="text"),
    _item("Physician Phone", section="Other", kind="text"),
    _item("Last Physical Exam", section="Other", kind="date"),
    _item("No Change Since Last Recorded", section="Other"),
)

# ── Dental Questionnaire (DENTQUEST) ─────────────────────────────────────────
DENTAL_CATALOG: tuple[dict[str, Any], ...] = (
    _item("Reason For Today's Visit", section="Dental History", kind="textarea"),
    _item("Date Of Last Dental Visit", section="Dental History", kind="date"),
    _item("Name Of Previous Dentist", section="Dental History", kind="text"),
    _item("Date Of Last Dental X-Rays", section="Dental History", kind="date"),
    _item("Are Your Teeth Sensitive To Hot Or Cold", section="Symptoms"),
    _item("Are Your Teeth Sensitive To Sweets", section="Symptoms"),
    _item("Do Your Gums Bleed When Brushing Or Flossing", section="Symptoms"),
    _item("Do You Have Loose Teeth", section="Symptoms"),
    _item("Do You Have Food Impaction Between Teeth", section="Symptoms"),
    _item("Do You Have A Bad Taste Or Odor In Your Mouth", section="Symptoms"),
    _item("Do You Have Dry Mouth", section="Symptoms"),
    _item("Do You Have Difficulty Chewing", section="Symptoms"),
    _item("Do You Have Jaw Pain Clicking Or Popping", section="Symptoms"),
    _item("Do You Clench Or Grind Your Teeth", section="Habits"),
    _item("Do You Smoke Or Chew Tobacco", section="Habits"),
    _item("How Often Do You Brush", section="Habits", kind="text"),
    _item("How Often Do You Floss", section="Habits", kind="text"),
    _item("Do You Use Fluoride Toothpaste", section="Habits"),
    _item("Have You Had Periodontal Gum Treatment", section="Previous Treatment"),
    _item("Have You Had Orthodontic Treatment", section="Previous Treatment"),
    _item("Have You Had Oral Surgery Or Extractions", section="Previous Treatment"),
    _item("Do You Wear Dentures Or Partials", section="Previous Treatment"),
    _item("Have You Had A Serious Injury To Head Or Mouth", section="Previous Treatment"),
    _item("Are You Happy With The Appearance Of Your Teeth", section="Concerns"),
    _item("Are You Nervous About Dental Treatment", section="Concerns"),
    _item("Have You Had A Bad Dental Experience", section="Concerns"),
    _item("Do You Snore Or Have Sleep Apnea", section="Concerns"),
    _item("Additional Dental Comments", section="Concerns", kind="textarea"),
)

# ── Medical Questionnaire (MEDQUEST) ─────────────────────────────────────────
# Deliberately excludes the emergency-contact block (MH-11) and anything the
# MEDALERT catalog already asks, so one fact is never captured in two places.
MEDICAL_CATALOG: tuple[dict[str, Any], ...] = (
    _item("Physician Name", section="Physician", kind="text"),
    _item("Physician Phone", section="Physician", kind="text"),
    _item("Date Of Last Physical Exam", section="Physician", kind="date"),
    _item("Are You Under A Physician's Care Now", section="Physician"),
    _item("If Yes What Condition", section="Physician", kind="text"),
    _item("Have You Been Hospitalized In The Last Five Years", section="General Health"),
    _item("Have You Had A Serious Illness Or Operation", section="General Health"),
    _item("If Yes Describe", section="General Health", kind="textarea"),
    _item("Height", section="General Health", kind="text"),
    _item("Weight", section="General Health", kind="text"),
    _item("Are You Taking Any Medications", section="Medications"),
    _item("List All Medications", section="Medications", kind="textarea"),
    _item("Are You Taking Blood Thinners", section="Medications"),
    _item("Are You Taking Bisphosphonates", section="Medications"),
    _item("Have You Taken Diet Drugs", section="Medications"),
    _item("Do You Use Alcohol", section="Lifestyle"),
    _item("Do You Use Recreational Drugs", section="Lifestyle"),
    _item("Do You Use Tobacco", section="Lifestyle"),
    _item("Are You Pregnant", section="Women Only"),
    _item("Expected Due Date", section="Women Only", kind="date"),
    _item("Are You Nursing", section="Women Only"),
    _item("Are You Taking Birth Control Pills", section="Women Only"),
    _item("Additional Medical Comments", section="Other", kind="textarea"),
)

CATALOGS: dict[str, tuple[dict[str, Any], ...]] = {
    ALERT_GROUP_TYPE: ALERT_CATALOG,
    DENTAL_GROUP_TYPE: DENTAL_CATALOG,
    MEDICAL_GROUP_TYPE: MEDICAL_CATALOG,
}

#: Default group_code seeded per type (one group per type; the legacy screens
#: render a single flat catalog per tab and use ``section`` for the sub-blocks).
DEFAULT_GROUP_CODES: dict[str, str] = {
    ALERT_GROUP_TYPE: "MEDALERT",
    DENTAL_GROUP_TYPE: "DENTQUEST",
    MEDICAL_GROUP_TYPE: "MEDQUEST",
}

GROUP_DESCRIPTIONS: dict[str, str] = {
    ALERT_GROUP_TYPE: "Medical Alerts",
    DENTAL_GROUP_TYPE: "Dental Questionnaire",
    MEDICAL_GROUP_TYPE: "Medical Questionnaire",
}


def input_type_for(kind: str | None) -> str:
    """``key2`` -> ``definitions.input_type``. Null/unknown means Yes/No."""
    return kind if kind in INPUT_KINDS else "yesno"


def normalize_catalog(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Accept a hand-over catalog (e.g. the frontend's ``legacyCatalogs.ts``
    exported to JSON) in either ``{code,label,...}`` or bare-label form, and
    return the canonical shape. A row without a ``code`` gets :func:`to_code` of
    its label — the same derivation the frontend uses."""
    out: list[dict[str, Any]] = []
    for raw in rows:
        if isinstance(raw, str):
            out.append(_item(raw))
            continue
        label = (raw.get("label") or raw.get("description") or "").strip()
        if not label:
            continue
        kind = raw.get("input_kind") or raw.get("key2") or raw.get("input_type")
        out.append(
            {
                "code": (raw.get("code") or raw.get("key1") or to_code(label)).strip(),
                "label": label,
                "section": raw.get("section"),
                "input_kind": kind if kind in INPUT_KINDS else None,
            }
        )
    return out
