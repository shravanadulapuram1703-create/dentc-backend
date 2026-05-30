"""
migration/utils/parsers.py
---------------------------
Value transformation helpers used across all migration steps.

All parsers return Python-native types that psycopg2 can bind directly:
  - None        → SQL NULL
  - datetime    → TIMESTAMP
  - date        → DATE
  - bool        → BOOLEAN
  - Decimal     → NUMERIC
  - str/int     → TEXT / INTEGER
"""

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Optional
import re

# ─────────────────────────────────────────────────────────────────────────────
# Dates & Times
# ─────────────────────────────────────────────────────────────────────────────

# Denticon uses these as sentinel "no date" values — treat as NULL
_NULL_YEARS = {1900, 1990}

_DATE_FORMATS = (
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
)


def parse_datetime(val: str) -> Optional[datetime]:
    """
    Parse a Denticon datetime string to a Python datetime, or None.
    Returns None for empty values or placeholder years (1900, 1990).
    """
    if not val or not val.strip():
        return None
    val = val.strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(val, fmt)
            if dt.year in _NULL_YEARS:
                return None
            return dt
        except ValueError:
            continue
    return None


def parse_date(val: str) -> Optional[date]:
    """
    Parse a Denticon date string to a Python date, or None.
    """
    dt = parse_datetime(val)
    return dt.date() if dt else None


# ─────────────────────────────────────────────────────────────────────────────
# Booleans
# ─────────────────────────────────────────────────────────────────────────────

def parse_bool(val: str) -> bool:
    """
    Parse Denticon boolean strings: "True" → True, everything else → False.
    Also handles "1"/"0", "Y"/"N", "yes"/"no".
    """
    if not val:
        return False
    v = str(val).strip().lower()
    return v in ("true", "1", "y", "yes")


# ─────────────────────────────────────────────────────────────────────────────
# Numbers
# ─────────────────────────────────────────────────────────────────────────────

def parse_decimal(val: str, default: Decimal = Decimal("0")) -> Decimal:
    """
    Parse a Denticon numeric string to Decimal. Returns default on empty/invalid.
    """
    if not val or not val.strip():
        return default
    try:
        return Decimal(val.strip().replace(",", ""))
    except InvalidOperation:
        return default


def parse_int(val: str, default: Optional[int] = None) -> Optional[int]:
    """
    Parse a string to int, returning default on empty/invalid.
    """
    if not val or not val.strip():
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


# ─────────────────────────────────────────────────────────────────────────────
# String cleaning
# ─────────────────────────────────────────────────────────────────────────────

def clean(val: str) -> Optional[str]:
    """
    Strip whitespace. Return None if empty.
    """
    if val is None:
        return None
    v = val.strip()
    return v if v else None


def clean_lower(val: str) -> Optional[str]:
    v = clean(val)
    return v.lower() if v else None


# ─────────────────────────────────────────────────────────────────────────────
# Domain-specific lookups
# ─────────────────────────────────────────────────────────────────────────────

# Denticon APPTSTATUS codes → human-readable strings
APPT_STATUS_MAP = {
    "1": "Scheduled",
    "2": "Unconfirmed",
    "3": "Confirmed",
    "4": "Left Message",
    "5": "In Reception",
    "6": "Available",
    "7": "In Operatory",
    "8": "Checked Out",
    "X": "Checked Out",
}


def map_appt_status(row: dict) -> str:
    if parse_bool(row.get("ISCANCELLED", "")):
        return "Cancelled"
    if parse_bool(row.get("ISMISSED", "")):
        return "Missed"
    code = (row.get("APPTSTATUS") or "").strip()
    return APPT_STATUS_MAP.get(code, "Scheduled")


# Denticon BILLINGORDER codes (may have trailing spaces)
def map_billing_order(val: str) -> Optional[str]:
    if not val:
        return None
    v = val.strip()
    if v.startswith("D"):
        return "primary"
    if v.startswith("S"):
        return "secondary"
    if v.startswith("T"):
        return "tertiary"
    return clean(val)


# Denticon LTYPE codes
LTYPE_PAYMENT_TYPE = {
    "P": "patient",
    "I": "insurance",
    "A": "adjustment",
}


def route_ledger_row(row: dict) -> Optional[str]:
    """
    Return the target table name for a LEDGER row based on LTYPE.
    Returns None for unknown types (skip them).
    """
    ltype = (row.get("LTYPE") or "").strip()
    if ltype == "C":
        return "patient_procedures"
    elif ltype in ("P", "I", "A"):
        return "patient_payments"
    return None


# Denticon claim status codes
CLAIM_STATUS_MAP = {
    "S": "submitted",
    "P": "pending",
    "R": "paid",
    "H": "draft",
    "D": "denied",
    "C": "closed",
}


def map_claim_status(val: str) -> str:
    return CLAIM_STATUS_MAP.get((val or "").strip(), "draft")


# Denticon payment method (TYPE2 field)
PAYMENT_METHOD_MAP = {
    "CA": "cash",
    "CK": "check",
    "CC": "card",
    "MC": "card",
    "VI": "card",
    "AM": "card",
    "DS": "card",
    "EFT": "ach",
}


def map_payment_method(val: str) -> Optional[str]:
    return PAYMENT_METHOD_MAP.get((val or "").strip().upper())


# Denticon gender ('M'/'F')
def map_gender(val: str) -> Optional[str]:
    v = (val or "").strip().upper()
    if v == "M":
        return "Male"
    if v == "F":
        return "Female"
    return None


# Denticon PLANTYPE integer → string
PLAN_TYPE_MAP = {
    "1": "PPO",
    "2": "HMO",
    "3": "Medicaid",
    "4": "Indemnity",
    "5": "Prepaid",
}


def map_plan_type(val: str) -> Optional[str]:
    return PLAN_TYPE_MAP.get((val or "").strip())


# Denticon eligibility status
ELIG_STATUS_MAP = {
    "Y": "verified",
    "N": "not_eligible",
    "U": "unknown",
}


def map_elig_status(val: str) -> str:
    return ELIG_STATUS_MAP.get((val or "").strip().upper(), "unknown")


# Denticon provider type (PROVIDERTYPE field)
PROVIDER_TYPE_MAP = {
    "1": "dentist",
    "2": "hygienist",
}


def map_provider_type(val: str) -> str:
    return PROVIDER_TYPE_MAP.get((val or "").strip(), "staff")


# ─────────────────────────────────────────────────────────────────────────────
# Lookup helpers
# ─────────────────────────────────────────────────────────────────────────────

def lookup(maps_dict: dict, key: str, warn_missing: bool = False) -> Optional[int]:
    """
    Resolve a legacy Denticon ID to the new DB integer ID using a lookup map.
    Returns None (→ NULL FK) if the key is missing or empty.
    """
    if not key or not key.strip():
        return None
    result = maps_dict.get(key.strip())
    if result is None and warn_missing and key.strip() not in ("0", ""):
        pass  # caller can enable warnings
    return result
