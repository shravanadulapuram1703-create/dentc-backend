"""ADA (CDT) code → insurance **coverage category** mapping (FEE-1).

Why this exists
---------------
``insurance_coverage_rules`` is where the coverage percentages live (876,732 rows
on the migrated tenant, one band per plan per category). Its ``start_code`` /
``end_code`` are **not** ADA codes on most plans — they are Denticon
*coverage-category* codes:

    ('01',  '01',  'Diagnostic',                  100.00)
    ('01A', '01A', 'Diagnostic:  X-Rays',         100.00)
    ('03',  '03',  'Restorative',                  80.00)
    ('03A', '03A', 'Restorative: Crowns',          50.00)

A minority of plans do band on real ADA ranges (``D0100``–, ``D1000``–, …), and
those already matched. For everything else a lookup keyed on ``D2393`` could
never hit a band whose range is ``01``–``01``, so the estimate engine returned
0 % coverage for every code on every migrated plan — the FEE-1 blocker.

The missing link is the ADA→category mapping. Denticon carries it as
``Codes.INSCATEGORYID``, which the migration mapped to a display label
(``category = "Restorative"``) and then **discarded**, so it cannot simply be
re-read. What is reconstructable — and auditable — is the category structure
itself: the categories are organised along the published **CDT family ranges**
(``D2xxx`` = restorative, ``D3xxx`` = endodontics, …), the same public taxonomy
``scripts/seed_procedure_code_rules.py`` derives the ``requires_*`` flags from.
No licensed CDT data file is used, and no ADA descriptor text is reproduced.

So the mapping is stated here as an explicit, reviewable range table, seeded onto
``procedure_codes.coverage_category`` by
``python -m scripts.seed_coverage_categories``, and published at
``GET /api/v1/metadata/coverage-categories`` so a practice can see exactly what
each band is being matched against and override any code it disagrees with (the
stored column always wins over the derived value).

Deliberate non-decisions
------------------------
* A code that matches no range gets **NULL**, not ``12`` ("Non-covered
  Services"). Silently classifying the 167 medical/CPT codes as non-covered
  would make the engine deny them with the same confidence it approves a
  prophy; NULL means "unknown", which is what it is.
* Sub-categories are listed **before** their parent so the first match wins:
  ``D0330`` is Panoramic (``01B``) before it is Diagnostic (``01``). A rule on
  the parent still applies to a sub-category code — see
  ``category_matches`` — so a plan that only bands ``01`` still covers it.
"""

from __future__ import annotations

import re
from typing import Iterable, NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProcedureCode

# ── the code-range table ────────────────────────────────────────────────────


class CoverageCategory(NamedTuple):
    code: str            # the Denticon coverage-category code, e.g. "01A"
    description: str     # the label the plan's bands carry
    ranges: tuple[tuple[str, str], ...]  # inclusive CDT ranges


#: Ordered **most specific first** — the first range that contains the code wins.
COVERAGE_CATEGORIES: tuple[CoverageCategory, ...] = (
    # ── 01 Diagnostic ───────────────────────────────────────────────────────
    CoverageCategory("01B", "Diagnostic: Panoramic X-Rays", (("D0330", "D0330"),)),
    CoverageCategory("01C", "Diagnostic: X-Rays - PAs", (("D0220", "D0230"),)),
    CoverageCategory("01D", "Diagnostic: X-Rays - Bitewings", (("D0270", "D0277"),)),
    CoverageCategory("01E", "Diagnostic: X-Rays - Cone Beam",
                     (("D0364", "D0368"), ("D0380", "D0391"))),
    CoverageCategory("01A", "Diagnostic: X-Rays", (("D0210", "D0363"),)),
    CoverageCategory("01", "Diagnostic", (("D0100", "D0999"),)),
    # ── 02 Preventive ───────────────────────────────────────────────────────
    CoverageCategory("02A", "Preventive: Sealants", (("D1351", "D1354"),)),
    CoverageCategory("02B", "Preventive: Space Maint", (("D1510", "D1575"),)),
    CoverageCategory("02", "Preventive", (("D1000", "D1999"),)),
    # ── 07 Inlays / onlays sit inside the D2xxx family but band with prosth ──
    CoverageCategory("07", "Prosthodontics (fix/rem), Inlays, Onlays",
                     (("D2510", "D2664"), ("D5000", "D5899"), ("D6200", "D6999"))),
    # ── 03 Restorative ──────────────────────────────────────────────────────
    CoverageCategory("03A", "Restorative: Crowns",
                     (("D2710", "D2799"), ("D2930", "D2934"))),
    CoverageCategory("03B", "Restorative: Build Up",
                     (("D2949", "D2950"), ("D2952", "D2957"))),
    CoverageCategory("03", "Restorative", (("D2000", "D2999"),)),
    # ── 04 Endodontics ──────────────────────────────────────────────────────
    CoverageCategory("04A", "Endodontics: Molar",
                     (("D3330", "D3330"), ("D3347", "D3347"), ("D3425", "D3425"))),
    CoverageCategory("04", "Endodontics", (("D3000", "D3999"),)),
    # ── 05 Periodontics ─────────────────────────────────────────────────────
    CoverageCategory("05A", "Periodontics: Osseous Surgery", (("D4260", "D4261"),)),
    CoverageCategory("05B", "Periodontics: Arestin", (("D4381", "D4381"),)),
    CoverageCategory("05", "Periodontics", (("D4000", "D4999"),)),
    # ── 08 Maxillofacial prosthetics ────────────────────────────────────────
    CoverageCategory("08", "Maxillofacial Prosthetics", (("D5900", "D5999"),)),
    # ── 09 Implants ─────────────────────────────────────────────────────────
    CoverageCategory("09A", "Implants: Crowns", (("D6058", "D6099"),)),
    CoverageCategory("09", "Implants", (("D6000", "D6199"),)),
    # ── 06 Oral surgery ─────────────────────────────────────────────────────
    CoverageCategory("06A", "Oral Surgery: Impactions", (("D7220", "D7241"),)),
    CoverageCategory("06", "Oral Surgery", (("D7000", "D7999"),)),
    # ── 10 Orthodontics ─────────────────────────────────────────────────────
    CoverageCategory("10", "Orthodontics", (("D8000", "D8999"),)),
    # ── 11 Adjunctive general services ──────────────────────────────────────
    CoverageCategory("11A", "Gen Adjunctive: Anesthesia", (("D9210", "D9248"),)),
    CoverageCategory("11B", "Gen Adjunctive: Biteguard/Nightguard",
                     (("D9940", "D9946"),)),
    CoverageCategory("11", "Gen Adjunctive", (("D9000", "D9999"),)),
)

#: Categories that appear on migrated plans but are not derivable from a CDT
#: range — published so the metadata endpoint lists the full vocabulary.
UNMAPPED_CATEGORIES: tuple[CoverageCategory, ...] = (
    CoverageCategory("12", "Non-covered Services", ()),
)

_BY_CODE = {c.code: c for c in (*COVERAGE_CATEGORIES, *UNMAPPED_CATEGORIES)}

# An ADA/CDT-shaped code: one letter + digits (``D2393``, ``D0120``).
_ADA_RE = re.compile(r"^([A-Za-z])0*(\d+)([A-Za-z]?)$")


def _split(code: str | None) -> tuple[str, int, str] | None:
    """``"D2393"`` → ``("D", 2393, "")``; ``None`` when it is not CDT-shaped."""
    if not code:
        return None
    m = _ADA_RE.match(code.strip())
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2)), m.group(3).upper()


def is_ada_code(code: str | None) -> bool:
    """True for a CDT/ADA-shaped code (so a band on it is a real code range)."""
    return _split(code) is not None


def in_range(code: str, start: str, end: str) -> bool:
    """Inclusive CDT range test, compared numerically inside the letter family."""
    c, s, e = _split(code), _split(start), _split(end or start)
    if c is None or s is None:
        return False
    if e is None:
        e = s
    if c[0] != s[0] or c[0] != e[0]:
        return False
    return s[1] <= c[1] <= e[1]


def derive_category(code: str) -> str | None:
    """The coverage category a CDT code falls in, or ``None`` when unmapped."""
    for cat in COVERAGE_CATEGORIES:
        for start, end in cat.ranges:
            if in_range(code, start, end):
                return cat.code
    return None


def describe(category_code: str | None) -> str | None:
    cat = _BY_CODE.get((category_code or "").strip())
    return cat.description if cat else None


def parent_of(category_code: str | None) -> str | None:
    """``"03A"`` → ``"03"``; ``None`` for a code that is already a parent."""
    code = (category_code or "").strip()
    if len(code) > 2 and code[-1].isalpha():
        return code[:-1]
    return None


def category_matches(rule_code: str | None, proc_category: str | None) -> int | None:
    """How well a rule's category band matches a procedure's category.

    Returns a **specificity score** (higher wins) or ``None`` for no match:

    * ``2`` — exact (``03A`` band, ``03A`` procedure)
    * ``1`` — the band is the parent of the procedure's sub-category
      (``03`` band covers a ``03A`` crown, which is how a plan that only
      itemises the top level still pays for one)

    A band on a *sub*-category never matches a procedure classified at the
    parent level: a "Restorative: Crowns" percentage must not price an amalgam.
    """
    rule = (rule_code or "").strip()
    proc = (proc_category or "").strip()
    if not rule or not proc:
        return None
    if rule == proc:
        return 2
    if parent_of(proc) == rule:
        return 1
    return None


# ── DB-facing helpers ───────────────────────────────────────────────────────


def category_for(db: Session, code: str) -> str | None:
    """The stored ``procedure_codes.coverage_category``, else the derived one.

    The stored column always wins so a practice override survives a re-seed.
    """
    stored = db.execute(
        select(ProcedureCode.coverage_category).where(ProcedureCode.code == code)
    ).scalar_one_or_none()
    if stored:
        return stored
    return derive_category(code)


def categories_for(db: Session, codes: Iterable[str]) -> dict[str, str | None]:
    """Batch form of :func:`category_for` (one query, no N+1)."""
    wanted = [c for c in dict.fromkeys(codes) if c]
    if not wanted:
        return {}
    stored = dict(
        db.execute(
            select(ProcedureCode.code, ProcedureCode.coverage_category).where(
                ProcedureCode.code.in_(wanted)
            )
        ).all()
    )
    return {c: (stored.get(c) or derive_category(c)) for c in wanted}


def catalog(db: Session | None = None) -> list[dict]:
    """The published mapping table (``GET /metadata/coverage-categories``)."""
    counts: dict[str, int] = {}
    if db is not None:
        rows = db.execute(
            select(ProcedureCode.coverage_category, ProcedureCode.code)
        ).all()
        for stored, code in rows:
            cat = stored or derive_category(code)
            if cat:
                counts[cat] = counts.get(cat, 0) + 1

    out: list[dict] = []
    for cat in (*COVERAGE_CATEGORIES, *UNMAPPED_CATEGORIES):
        out.append({
            "code": cat.code,
            "description": cat.description,
            "parent_code": parent_of(cat.code),
            "cdt_ranges": [{"start_code": s, "end_code": e} for s, e in cat.ranges],
            "procedure_code_count": counts.get(cat.code, 0),
        })
    out.sort(key=lambda r: r["code"])
    return out
