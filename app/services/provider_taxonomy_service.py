"""Healthcare Provider Taxonomy codes for dentistry (ADA-BE-14).

The ADA claim form's Item 56a and the 837D ``PRV03`` element want a
**taxonomy code**, not a specialty label. ``providers.specialty`` is free text
(the ``provider_specialty`` definitions group is un-enumerated and blank on 96
of 97 migrated rows), so the only honest server-side answer is the same one the
frontend had been computing in the browser — a keyword map — published once
here and stored on the row when Setup fills ``providers.taxonomy_code``.

``effective_taxonomy_code`` on ``ProviderRead`` is the stored code when set,
else the keyword resolution of ``specialty``, else ``122300000X`` (General
Dentist) — the default the ADA instructions give for a dentist who reports no
specialty. The catalog is deliberately the dental subset of the NUCC list; a
practice with an out-of-list code stores it verbatim (no 422 — an unfamiliar
code is a lookup problem, not a data-entry error).
"""

from __future__ import annotations

import re

GENERAL_DENTIST = "122300000X"

#: (code, label, keywords that map a free-text specialty onto it). Order matters
#: — the first keyword hit wins, so the more specific families sit above the
#: generic "dent" catch-all.
TAXONOMY_CODES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("1223E0200X", "Endodontics", ("endo",)),
    ("1223X0400X", "Orthodontics and Dentofacial Orthopedics", ("ortho",)),
    ("1223P0221X", "Pediatric Dentistry", ("pedi", "pedo", "child")),
    ("1223P0300X", "Periodontics", ("perio",)),
    ("1223P0700X", "Prosthodontics", ("prostho",)),
    ("1223S0112X", "Oral and Maxillofacial Surgery", ("surg", "maxillofacial")),
    ("1223X0008X", "Oral and Maxillofacial Radiology", ("radiol",)),
    ("1223D0008X", "Oral and Maxillofacial Pathology", ("patho",)),
    ("1223D0001X", "Dental Public Health", ("public health",)),
    ("1223G0001X", "General Practice", ("general practice", "gp")),
    ("124Q00000X", "Dental Hygienist", ("hygien",)),
    ("126800000X", "Dental Assistant", ("assist",)),
    ("122400000X", "Denturist", ("dentur",)),
    (GENERAL_DENTIST, "Dentist", ("dent",)),
)

_LABELS = {code: label for code, label, _ in TAXONOMY_CODES}
_CODE_RE = re.compile(r"^[0-9A-Z]{9}X$")


def label_for(code: str | None) -> str | None:
    return _LABELS.get((code or "").strip().upper()) if code else None


def is_taxonomy_shaped(value: str | None) -> bool:
    """10 chars, ending in X — the NUCC shape. Used only to *report* an
    unfamiliar code as such, never to reject it."""
    return bool(value) and bool(_CODE_RE.match(value.strip().upper()))


def resolve_from_specialty(specialty: str | None) -> str | None:
    """Keyword-map a free-text specialty (``"Endodontist"`` → ``1223E0200X``).
    ``None`` when nothing matches so the caller can tell "derived" from
    "defaulted"."""
    text = (specialty or "").strip().lower()
    if not text:
        return None
    for code, _label, keywords in TAXONOMY_CODES:
        if any(k in text for k in keywords):
            return code
    return None


def effective_code(taxonomy_code: str | None, specialty: str | None) -> tuple[str, str]:
    """-> (code, source) where source is ``stored`` | ``specialty`` | ``default``."""
    stored = (taxonomy_code or "").strip().upper()
    if stored:
        return stored, "stored"
    derived = resolve_from_specialty(specialty)
    if derived:
        return derived, "specialty"
    return GENERAL_DENTIST, "default"


def catalog() -> list[dict]:
    return [
        {"code": code, "label": label, "keywords": list(keywords)}
        for code, label, keywords in TAXONOMY_CODES
    ]
