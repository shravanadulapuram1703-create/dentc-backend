"""MH-5 / MH-12: the published answer semantics and contradiction rules for the
Patient Medical History screen.

MH-5 — what ``response`` means
------------------------------
The stored vocabulary is ``yes | no | unknown`` and a **missing row is "Not
Answered"**. Those are three different clinical facts and the API keeps them
distinct: absence is never rewritten to ``unknown``, and ``unknown`` is never
collapsed to absence. "The patient does not know whether they are allergic to
penicillin" and "nobody asked" must not read alike on a medical record. A client
that models only NO / NOT ANSWERED / YES simply never sends ``unknown`` — the
composite write deletes a row whose response comes in null/empty, which is
exactly the legacy reset-to-Not-Answered behaviour.

MH-12 — contradictions
----------------------
"No Known Allergies = Yes" alongside "Penicillin = Yes" was storable, as was "No
Change Since Last Recorded = Yes" alongside edits in the same save. Legacy runs
on the same honour system, but re-implementing the check in each client means it
holds only where someone remembered it, so it is enforced server-side on every
write path and **published** at ``GET /metadata/medical-history-rules`` so the
form can grey the boxes out from the same table.

The rules are *exclusions*, not implications, so they are **422s** rather than
auto-corrections — following the Add/Edit-Patient precedent in
``patient_rules_service``: there is no way to know which of the two the user
meant, and silently dropping one discards intent on a clinical record. A caller
that genuinely means it can pass ``allow_contradictions=true``; the override is
recorded in the change log.
"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import ValidationError
from app.services.medical_history_catalog import to_code

#: The "I have no allergies at all" row. Yes here excludes any *specific*
#: allergy answered Yes.
NO_KNOWN_ALLERGIES = to_code("No Known Allergies")

#: The "nothing has changed since the last recording" row. Yes here excludes an
#: edit in the same save.
NO_CHANGE_SINCE_LAST_RECORDED = to_code("No Change Since Last Recorded")

#: Catalog ``section`` values treated as specific allergies. Derived from the
#: catalog rather than a hardcoded code list so a seeded allergy the built-in
#: catalog does not know about is still covered.
ALLERGY_SECTIONS: tuple[str, ...] = ("allergic to", "allergies", "allergy")

POSITIVE = "yes"


def _is_allergy(code: str, section: str | None) -> bool:
    if code == NO_KNOWN_ALLERGIES:
        return False
    return (section or "").strip().lower() in ALLERGY_SECTIONS


def check_alert_contradictions(
    answers: dict[str, str | None],
    sections: dict[str, str | None],
    *,
    changed_codes: set[str] | None = None,
    allow: bool = False,
) -> list[dict[str, Any]]:
    """Return the contradictions in a merged answer set.

    ``answers`` is ``{alert_code: response}`` for the **merge of the payload and
    the stored rows** — a PATCH carrying only the touched box still has to be
    judged against the answers already in the database, the same way
    ``patient_rules_service`` evaluates its implications.

    Raises :class:`ValidationError` (422) unless ``allow`` is set, in which case
    the list is returned for the caller to record.
    """
    found: list[dict[str, Any]] = []

    if (answers.get(NO_KNOWN_ALLERGIES) or "").lower() == POSITIVE:
        offenders = sorted(
            code
            for code, response in answers.items()
            if (response or "").lower() == POSITIVE and _is_allergy(code, sections.get(code))
        )
        if offenders:
            found.append(
                {
                    "rule": "no_known_allergies_excludes_specific_allergy",
                    "code": NO_KNOWN_ALLERGIES,
                    "conflicts_with": offenders,
                    "message": (
                        "'No Known Allergies' is answered Yes while a specific allergy is "
                        "also answered Yes."
                    ),
                }
            )

    if (answers.get(NO_CHANGE_SINCE_LAST_RECORDED) or "").lower() == POSITIVE:
        edits = sorted((changed_codes or set()) - {NO_CHANGE_SINCE_LAST_RECORDED})
        if edits:
            found.append(
                {
                    "rule": "no_change_since_last_recorded_excludes_edits",
                    "code": NO_CHANGE_SINCE_LAST_RECORDED,
                    "conflicts_with": edits,
                    "message": (
                        "'No Change Since Last Recorded' is answered Yes while answers are "
                        "being changed in the same save."
                    ),
                }
            )

    if found and not allow:
        raise ValidationError(
            "The medical alerts contain contradictory answers.",
            code="contradictory_medical_alerts",
            details={"contradictions": found},
        )
    return found


def published_rules() -> dict[str, Any]:
    """The rule table + answer vocabulary the API enforces, served to the form so
    a rule added here reaches the UI without a frontend release."""
    return {
        "response_values": ["yes", "no", "unknown"],
        "not_answered_is": "absent_row",
        "response_semantics": {
            "yes": "Answered yes.",
            "no": "Answered no.",
            "unknown": "Asked, but the answer is genuinely not known.",
            "absent_row": "Not Answered - nobody has asked. Distinct from 'unknown'.",
        },
        "reset_to_not_answered": (
            "Send the code with a null/empty response in PUT /patients/{id}/medical-history; "
            "the row is deleted and the change is recorded in the change log."
        ),
        "exclusions": [
            {
                "rule": "no_known_allergies_excludes_specific_allergy",
                "code": NO_KNOWN_ALLERGIES,
                "excludes": {"sections": list(ALLERGY_SECTIONS), "when": "yes"},
                "enforcement": "422 contradictory_medical_alerts",
            },
            {
                "rule": "no_change_since_last_recorded_excludes_edits",
                "code": NO_CHANGE_SINCE_LAST_RECORDED,
                "excludes": {"any_changed_answer_in_the_same_save": True, "when": "yes"},
                "enforcement": "422 contradictory_medical_alerts",
            },
        ],
        "override": {
            "field": "allow_contradictions",
            "effect": "Stores the contradiction and records it in the change log.",
        },
        "code_convention": {
            "derivation": "lowercase, non-alphanumeric runs -> '_', trimmed",
            "example": {"label": "Latex Rubber", "code": "latex_rubber"},
        },
        "emergency_contact_authority": "patient_emergency_contacts",
    }
