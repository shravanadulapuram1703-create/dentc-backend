"""Phone-number normalisation for SMS (SMS-1/2).

The frontend sends E.164 (``+12107936174``); legacy ``patients`` rows hold
whatever Denticon held — bare 10 digits, ``(210) 793-6174``, ``210-793-6174``.
Matching an inbound ``From`` against those columns cannot use a regex on the
DB side portably (SQLite in tests, Postgres live), so instead the E.164 form is
expanded into every storage spelling we have seen and matched with ``IN``,
which also keeps the lookups index-friendly.
"""

from __future__ import annotations

import re

_DIGITS = re.compile(r"\d+")


def digits_only(raw: str | None) -> str:
    return "".join(_DIGITS.findall(raw or ""))


def normalize_e164(raw: str | None, *, default_country: str = "1") -> str | None:
    """Best-effort E.164. US/CA 10-digit numbers get ``+1``; an explicit ``+``
    is trusted; anything else that is not plausibly a number returns None."""
    if not raw:
        return None
    text = raw.strip()
    digits = digits_only(text)
    if not digits:
        return None
    if text.startswith("+"):
        return f"+{digits}" if 8 <= len(digits) <= 15 else None
    if len(digits) == 10:
        return f"+{default_country}{digits}"
    if len(digits) == 11 and digits.startswith(default_country):
        return f"+{digits}"
    if 11 <= len(digits) <= 15 and digits.startswith("00"):
        return f"+{digits[2:]}"
    return None


def phone_variants(e164: str | None) -> list[str]:
    """Every way a number equal to ``e164`` might be stored on a patient row."""
    if not e164:
        return []
    digits = digits_only(e164)
    out: list[str] = [e164, digits]
    if len(digits) == 11 and digits.startswith("1"):
        n = digits[1:]
        a, b, c = n[:3], n[3:6], n[6:]
        out += [
            n,
            f"({a}) {b}-{c}",
            f"({a}){b}-{c}",
            f"{a}-{b}-{c}",
            f"{a}.{b}.{c}",
            f"{a} {b} {c}",
            f"1-{a}-{b}-{c}",
            f"+1 {a} {b} {c}",
            f"+1-{a}-{b}-{c}",
            f"+1 ({a}) {b}-{c}",
            f"1 ({a}) {b}-{c}",
        ]
    seen: set[str] = set()
    return [v for v in out if not (v in seen or seen.add(v))]


def same_number(a: str | None, b: str | None) -> bool:
    na, nb = normalize_e164(a), normalize_e164(b)
    return bool(na and nb and na == nb)
