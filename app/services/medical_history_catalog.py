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

#: GAP-AP-20: the derivation cap, mirroring the frontend's
#: ``CATALOG_CODE_MAX_LENGTH`` in ``legacyCatalogs.ts``. It was 60 on both sides
#: while the columns were ``VARCHAR(50)``, so the 12 legacy questions whose slug
#: runs 51–60 characters could never be saved (HTTP 500). The frontend clamped
#: to 50 (all 50-char prefixes verified unique per catalog); this must match it
#: exactly, because an answer is keyed by the derived code — a backend catalog
#: still deriving 60-char codes would read every one of those 12 answers as
#: Not Answered. The *storage* bound is wider (100, ``patient_catalog.
#: CATALOG_CODE_MAX_LENGTH``) so the cap can grow without another migration.
CODE_MAX_LENGTH = 50


def to_code(label: str) -> str:
    """``"Latex Rubber" -> "latex_rubber"``.

    The frontend derives an answer's ``alert_code``/``question_code`` from the
    label this way. Seeding ``key1`` with anything else orphans every answered
    row, so the derivation is published here and used by the seeder, the
    composite write and ``GET /metadata/medical-history-rules``.
    """
    return _NON_ALNUM.sub("_", (label or "").strip().lower()).strip("_")[:CODE_MAX_LENGTH]


def _item(label: str, *, section: str | None = None, kind: str | None = None) -> dict[str, Any]:
    return {"code": to_code(label), "label": label, "section": section, "input_kind": kind}


# ── Medical Alerts (MEDALERT) ────────────────────────────────────────────────
# MA-3: this is a **verbatim transcription of the frontend's**
# ``src/features/add-patient/legacyCatalogs.ts`` (``LEGACY_MEDICAL_ALERT_GROUPS``),
# in the same order and with the same three group titles as ``section``. It has
# to be: every stored ``alert_code`` was derived by the frontend from *these*
# labels (``cardiac_pacemaker``, ``frequent_headaches``, ``autoimmune_disease``…),
# so a built-in list authored independently ("Heart Pacemaker" under "Medical
# Conditions") resolved a null section and a null label for the very rows the
# screen writes. ``no_known_allergies`` and ``no_change_since_last_recorded``
# are the two rows MH-12's contradiction rules key off.
_ALLERGIC_TO = "Allergic To"
_CHECK_IF_APPLICABLE = "Check, if applicable"
_OTHER = "Other"

ALERT_CATALOG: tuple[dict[str, Any], ...] = (
    *(
        _item(label, section=_ALLERGIC_TO)
        for label in (
            "No Known Allergies",
            "Aspirin",
            "Barbiturates / Sleeping Pills",
            "Codeine",
            "Erythromycin",
            "Iodine",
            "Latex Rubber",
            "Local Anesthetics",
            "Metals",
            "No Epinephrine",
            "Penicillin",
            "Prior Hepatitis",
            "Sulfa Drugs",
            "Other Narcotics",
        )
    ),
    *(
        _item(label, section=_CHECK_IF_APPLICABLE)
        for label in (
            "No Change Since Last Recorded",
            "No Known Concerns or Issues",
            "Abnormal Bleeding",
            "AIDS/HIV Infection",
            "Alcohol/Drug Abuse",
            "Angina",
            "Anemia",
            "Ankles Swell",
            "Anorexia",
            "Arteriosclerosis",
            "Arthritis",
            "Asthma",
            "Autoimmune Disease",
            "Bladder Trouble",
            "Blood Clotting Problems",
            "Blood Transfusion",
            "Bulimia",
            "Bronchitis",
            "Cancer / Tumor or Growth",
            "Cardiac Pacemaker",
            "Cardiovascular Disease",
            "Chemotherapy",
            "Chest Pain Upon Exertion",
            "Color Blindness",
            "Congenital Heart Defect",
            "Contact Lenses",
            "Congestive Heart Failure",
            "Damaged Heart Valve",
            "Diabetes",
            "Emphysema",
            "Environmental Allergies",
            "Epilepsy",
            "Fainting Spells",
            "Fever Blisters",
            "Frequent Headaches",
            "Frequently Dry Mouth / Sjogren",
            "Gag Reflex",
            "Gall Bladder Trouble",
            "Hay Fever",
            "Heart Attack",
            "Heart Disease",
            "Heart Murmur",
            "Hepatitis",
            "Herpes",
            "High Blood Pressure",
            "Hives",
            "Jaundice",
            "Joint Replacement",
            "Kidney",
            "Leukemia",
            "Liver Disease",
            "Low Blood Pressure",
            "Lupus",
            "Mental Health Problems",
            "Mitral Valve Prolapse",
            "Pacemaker",
            "Persistent Diarrhea",
            "Premedicate",
            "Radiation Treatment",
            "Rheumatic Fever",
            "Rheumatic Heart Disease",
            "Rheumatoid Arthritis",
            "Seizures",
            "Sexually Transmitted Disease",
            "Shortness of Breath",
            "Skin Rash",
            "Sinus Trouble",
            "Stomach Ulcers",
            "Stroke",
            "Thyroid Problems",
            "Tuberculosis",
            "Unusual Weight Loss",
            "Urinate Frequently",
        )
    ),
    _item("See Scanned Documents: Pt Note", section=_OTHER),
)

#: MA-3: the group order the legacy screen (and the frontend banner) renders —
#: allergies first, because that is the prescribing-critical block.
ALERT_SECTION_ORDER: tuple[str, ...] = (_ALLERGIC_TO, _CHECK_IF_APPLICABLE, _OTHER)

# ── Dental Questionnaire (DENTQUEST) ─────────────────────────────────────────
# Verbatim from ``LEGACY_DENTAL_QUESTION_GROUPS`` (same file), legacy order.
_DENTAL_Q = "Dental Questionnaire"
_ADDITIONAL_COMMENTS = "Additional Comments"

DENTAL_CATALOG: tuple[dict[str, Any], ...] = (
    _item("Name of previous Dentist", section=_DENTAL_Q, kind="text"),
    _item("Phone", section=_DENTAL_Q, kind="text"),
    _item("Date of your last cleaning", section=_DENTAL_Q, kind="date"),
    _item("Last exam date", section=_DENTAL_Q, kind="date"),
    _item("Date of your last full series x-rays", section=_DENTAL_Q, kind="date"),
    _item("Date of last cavity detection (bitewing) x-rays", section=_DENTAL_Q, kind="date"),
    _item("Do your gums bleed while brushing or flossing ?", section=_DENTAL_Q),
    _item("Are your teeth sensitive to hot, cold or sweets ?", section=_DENTAL_Q),
    _item("Do you get frequent fever blisters, mouth ulcers, or sores on your lips or in your mouth ?",
          section=_DENTAL_Q),
    _item("Have you ever had burning of the tongue or cracking of the corners of your mouth ?",
          section=_DENTAL_Q),
    _item("Do you chew/smoke tobacco in any form ?", section=_DENTAL_Q),
    _item("Have you had any head, neck or jaw injuries ?", section=_DENTAL_Q),
    _item("Do you notice popping, clicking or soreness of the jaws or points just in front of the ears ?",
          section=_DENTAL_Q),
    _item("Do you clench or grind your teeth ?", section=_DENTAL_Q),
    _item("Have you ever had orthodontic treatment ?", section=_DENTAL_Q),
    _item("If Yes, date of placement", section=_DENTAL_Q, kind="date"),
    _item("Do you wear dentures or partials ?", section=_DENTAL_Q),
    _item("If Yes, date of placement of dentures ?", section=_DENTAL_Q, kind="date"),
    _item("Are you happy with your dentures ?", section=_DENTAL_Q),
    _item("Are you having any specific problems with your teeth, gums, or mouth at this time ?",
          section=_DENTAL_Q),
    _item("Are you happy with your smile ?", section=_DENTAL_Q),
    _item("Do you have problems with teeth/fillings breaking ?", section=_DENTAL_Q),
    _item("Do you regularly use dental floss ?", section=_DENTAL_Q),
    _item("Do you have, or have you ever been told, that you have Pyorrhea (Periodontal Disease) ?",
          section=_DENTAL_Q),
    _item("Do you have difficulty in opening your mouth widely ?", section=_DENTAL_Q),
    _item("Do you have an unpleasant taste or odor in your teeth/mouth ?", section=_DENTAL_Q),
    _item("Does food catch between your teeth ?", section=_DENTAL_Q),
    _item("Do you want to learn to control your dental disease and retain your teeth ?",
          section=_DENTAL_Q),
    _item("Any Disease, Condition or Problem not Listed ? Please list",
          section=_ADDITIONAL_COMMENTS, kind="textarea"),
)

# ── Medical Questionnaire (MEDQUEST) ─────────────────────────────────────────
# Verbatim from ``LEGACY_MEDICAL_QUESTION_GROUPS`` **minus the Emergency Contact
# block** (MH-11: ``patient_emergency_contacts`` is authoritative, so one fact is
# never captured in two places).
_MEDICAL_Q = "Medical Questionnaire"
_WOMEN_ONLY = "Women Only"

MEDICAL_CATALOG: tuple[dict[str, Any], ...] = (
    _item("Family Physician", section=_MEDICAL_Q, kind="text"),
    _item("Phone", section=_MEDICAL_Q, kind="text"),
    _item("Are you currently under care of a Physician ?", section=_MEDICAL_Q),
    _item("If Yes, what is the condition being treated ?", section=_MEDICAL_Q, kind="textarea"),
    _item("Have you had any serious illness, operation or been hospitalized within the past 5 years ?",
          section=_MEDICAL_Q),
    _item("If Yes, what illness or problem ?", section=_MEDICAL_Q, kind="text"),
    _item("Are you currently taking any medication ?", section=_MEDICAL_Q),
    _item("If Yes, what ?", section=_MEDICAL_Q, kind="textarea"),
    _item("Have you taken bisphosphonates (Fosamax, Boniva, Zometa, Actonel, Didronel, Aredia, Skelid, Reclast)",
          section=_MEDICAL_Q),
    _item("Have you ever taken the diet control drug Fen-Phen ?", section=_MEDICAL_Q),
    _item("Do you use alcoholic beverages ?", section=_MEDICAL_Q),
    _item("Do you smoke ?", section=_MEDICAL_Q),
    _item("Are you pregnant?", section=_WOMEN_ONLY),
    _item("If Yes, what is your due date ?", section=_WOMEN_ONLY, kind="date"),
    _item("Are you currently nursing ?", section=_WOMEN_ONLY),
    _item("Do you have menstrual period problems ?", section=_WOMEN_ONLY),
    _item("Are you on hormone replacement therapy ?", section=_WOMEN_ONLY),
    _item("Are you on birth control pills / fertility drugs ?", section=_WOMEN_ONLY),
    _item("Any Disease, Condition or Problem not Listed ? Please list",
          section=_ADDITIONAL_COMMENTS, kind="textarea"),
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
