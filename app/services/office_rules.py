"""Office Setup validation rules (OFF-QA-2/4/5/8/9 of
docs/office-scope/office_setup_new_office_qa_backend_devreport.md).

One home for the vocabularies and format checks the Office Setup tabs write
through, so the schemas, the services, the data migration and the published
metadata cannot disagree. Everything here is pure (no DB).
"""

from __future__ import annotations

import re
from datetime import time
from typing import Any
from urllib.parse import urlparse

# ── OFF-QA-2: enum vocabularies (canonical casing) ───────────────────────────
LOGO_OPTIONS = ("office", "custom", "none")          # lowercase
ADDRESS_SOURCES = ("office", "custom")               # lowercase
HOLIDAY_STATUSES = ("CLOSED", "OPEN", "HALF_DAY")    # uppercase
HOLIDAY_TYPES = ("FEDERAL", "CUSTOM")                # uppercase

# Spellings older frontend builds wrote, folded on write (and by the migration).
_HOLIDAY_STATUS_ALIASES = {"HALF DAY": "HALF_DAY", "HALFDAY": "HALF_DAY", "HALF-DAY": "HALF_DAY"}


def fold_lower(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def fold_upper(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


def fold_holiday_status(value: Any) -> Any:
    v = fold_upper(value)
    return _HOLIDAY_STATUS_ALIASES.get(v, v) if isinstance(v, str) else v


# ── OFF-QA-4: one day of a weekly schedule ───────────────────────────────────
def schedule_day_errors(day: dict) -> list[tuple[str, str]]:
    """``[(field, message)]`` for one schedule day; empty when valid.

    A closed day carries no times worth judging. An open day needs start and
    end with end after start; lunch is both-or-neither, ends after it starts and
    sits inside the day.
    """
    if day.get("is_closed"):
        return []
    errs: list[tuple[str, str]] = []
    start: time | None = day.get("start_time")
    end: time | None = day.get("end_time")
    ls: time | None = day.get("lunch_start")
    le: time | None = day.get("lunch_end")
    if start is None:
        errs.append(("start_time", "An open day needs a start time"))
    if end is None:
        errs.append(("end_time", "An open day needs an end time"))
    if start is not None and end is not None and end <= start:
        errs.append(("end_time", "end_time must be after start_time"))
    if (ls is None) != (le is None):
        errs.append(("lunch_end" if le is None else "lunch_start",
                     "lunch_start and lunch_end must both be set or both be empty"))
    elif ls is not None and le is not None:
        if le <= ls:
            errs.append(("lunch_end", "lunch_end must be after lunch_start"))
        elif start is not None and end is not None and (ls < start or le > end):
            errs.append(("lunch_start", "Lunch must fall inside the day's hours"))
    return errs


# ── OFF-QA-5: integrations ───────────────────────────────────────────────────
_URL_SCHEMES = ("http", "https")


def http_url_error(value: str) -> str | None:
    """A link the UI will render and open: http(s) with a host, nothing else
    (``javascript:``/``data:`` would be stored XSS in any client that renders it)."""
    parsed = urlparse(value.strip())
    if parsed.scheme.lower() not in _URL_SCHEMES or not parsed.netloc:
        return "Must be an http:// or https:// URL"
    return None


# ── OFF-QA-8: advanced settings ──────────────────────────────────────────────
#: Words older frontend builds stored in ``place_of_service`` -> CMS POS code.
LEGACY_PLACE_OF_SERVICE = {
    "office": "11", "hospital": "22", "nursing_home": "32", "school": "03", "other": "99",
}
_POS = re.compile(r"^\d{2}$")
_AREA_CODE = re.compile(r"^\d{3}$")
_STATE = re.compile(r"^[A-Z]{2}$")


def canonical_place_of_service(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    v = value.strip()
    if not v:
        return None
    return LEGACY_PLACE_OF_SERVICE.get(v.lower(), v)


def is_pos_code(value: str) -> bool:
    return bool(_POS.match(value))


def is_area_code(value: str) -> bool:
    return bool(_AREA_CODE.match(value))


def is_state_code(value: str) -> bool:
    return bool(_STATE.match(value))


# ── OFF-QA-9: NPI / taxonomy ─────────────────────────────────────────────────
_TAXONOMY = re.compile(r"^[0-9]{3}[0-9A-Z]{6}X$")


def npi_is_valid(npi: str) -> bool:
    """10 digits passing the CMS Luhn check over ``80840`` + the first nine
    digits (the tenth is the check digit)."""
    if not re.fullmatch(r"\d{10}", npi or ""):
        return False
    digits = [int(c) for c in "80840" + npi[:9]]
    total = 0
    # Luhn: double every second digit from the right of the payload (which is
    # the check digit's left neighbour).
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10 == int(npi[9])


def taxonomy_is_valid(code: str) -> bool:
    return bool(_TAXONOMY.match(code or ""))


def rules_metadata() -> dict:
    """Published at ``GET /offices/setup-rules`` so the form validates against
    the same table."""
    return {
        "logo_options": list(LOGO_OPTIONS),
        "address_sources": list(ADDRESS_SOURCES),
        "holiday_statuses": list(HOLIDAY_STATUSES),
        "holiday_types": list(HOLIDAY_TYPES),
        "legacy_place_of_service": dict(LEGACY_PLACE_OF_SERVICE),
        "url_schemes": list(_URL_SCHEMES),
        "npi": {"length": 10, "check": "luhn_80840"},
        "taxonomy_code_pattern": _TAXONOMY.pattern,
        "advanced_settings": {
            "percent_range": [0, 100], "money_min": 0, "days_before_charge_min": 0,
            "area_code_pattern": _AREA_CODE.pattern, "default_state_pattern": _STATE.pattern,
            "place_of_service_pattern": _POS.pattern,
        },
    }
