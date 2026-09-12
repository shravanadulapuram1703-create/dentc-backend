"""Procedure-entry rules: the surface vocabulary, tooth numbering and the
``requires_*`` enforcement that must hold whoever is writing (PROC-INT-6/8).

Four screens post or plan a procedure (Transactions Entry, Account Ledger,
Restorative Chart, Treatment Plan). Until now the only thing stopping a D2150
("two surface amalgam") being saved with no tooth and no surface was the
**ADD PROCEDURE DETAILS** pop-up in one client — the API accepted anything. And
the surface itself was free text: the same restoration could be stored as
``"MOD"``, ``"mod"``, ``"M,O,D"`` or ``"DOM"``, so a report grouping by surface
could not, and the migrated data already shows it (``IDLF``, ``FMDL``, ``MOLB``
alongside the canonical spellings).

This module is the single home for both rules. It is used by every write path
into ``patient_procedures`` and ``treatment_plan_items`` (the generic CRUD
routes, the Post-to-Ledger endpoint) and by the two catalogue tables that
pre-fill the pop-up (``code_bundle_items``, ``explosion_code_items``), and it is
published at ``GET /metadata/procedure-entry-rules`` so the client renders the
same vocabulary it is validated against.

Surface vocabulary (PROC-INT-6)
-------------------------------
Seven base letters, stored concatenated in one canonical order::

    M  mesial
    O  occlusal   (posterior teeth)      I  incisal  (anterior teeth)
    D  distal
    B  buccal     (posterior teeth)      F  facial   (anterior teeth)
    L  lingual

Order is **M · O/I · D · B/F · L** — so ``"DOM"`` normalises to ``"MOD"`` and
``"FML"`` to ``"MFL"``. ``O``/``I`` and ``B``/``F`` are the same anatomical
surface on different arches, so when the tooth is known the letter is written
in the arch's own spelling (an ``O`` on tooth 8 becomes ``I``); when it is not,
the letter is kept as given. **Class V** (a gingival-third lesion on a facial or
lingual surface) is a *qualifier*, not an eighth surface: it is stored as a
``5`` suffix on the surface it qualifies (``B5``, ``F5``, ``L5``), counts as
**one** surface toward the code's count, and is only valid on B/F/L.

Tooth numbering
---------------
Universal: permanent ``1``–``32``, primary ``A``–``T``; supernumerary as
``tooth + 50`` (``51``–``82``) or ``letter + "S"`` (``AS``–``TS``). Anterior =
permanent 6–11 / 22–27 and primary C–H / M–R; everything else is posterior.
The migrated ledger also holds **quadrant codes in the tooth column** (``UR``
3,182 rows, ``LR``, ``LL``, ``UL``, ``LA``, ``UA``, ``FM``) because Denticon had
one "tooth/area" field — so a quadrant code is accepted in ``tooth`` and
satisfies ``requires_quadrant``, and a write that carries it in ``tooth`` with
an empty ``quadrant`` has it mirrored into ``quadrant``.

Enforcement (PROC-INT-8)
------------------------
Evaluated against the **merge of payload and stored row**, so a PATCH carrying
only the touched field still sees the rest. On an update the rules only run
when the payload touches ``procedure_code``/``tooth``/``surface``/``quadrant``:
1.37 M migrated charges predate the flags, and re-pricing one of them must not
fail because it never had a tooth. Every failure is a **422** whose ``details``
carry ``code`` and the offending ``field``:

======================  ==========  =======================================
``code``                ``field``   when
======================  ==========  =======================================
invalid_tooth           tooth       not Universal / supernumerary / quadrant
invalid_surface         surface     a character outside the vocabulary
invalid_quadrant        quadrant    not UR/UL/LL/LR/UA/LA/FM
tooth_required          tooth       ``requires_tooth`` and no tooth
tooth_not_allowed       tooth       outside ``valid_teeth`` / ``tooth_area``
surface_required        surface     ``requires_surface`` and no surface
surface_count           surface     count outside the code's min/max
surface_not_allowed     surface     a letter outside ``surface_rules.allowed``
quadrant_required       quadrant    ``requires_quadrant`` and no quadrant
quadrant_not_allowed    quadrant    outside ``anatomy_rules.allowed_quadrants``
======================  ==========  =======================================

``requires_lab`` is deliberately **advisory** (reported in the metadata, never a
422): ``chart_materials`` is tenant-scoped while ``procedure_codes`` is global,
264 codes carry the flag, and several posting paths (appointment check-out,
payment-plan instalment posting) have no material picker — a hard failure
there would block billing, not improve charting.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.crud.base import CRUDBase
from app.db.models import ProcedureCode

# ── vocabulary ───────────────────────────────────────────────────────────────
SURFACE_LETTERS: tuple[str, ...] = ("M", "O", "I", "D", "B", "F", "L")
SURFACE_LABELS: dict[str, str] = {
    "M": "Mesial", "O": "Occlusal", "I": "Incisal", "D": "Distal",
    "B": "Buccal", "F": "Facial", "L": "Lingual",
}
#: Canonical sort position. O/I and B/F share a slot: they are the same surface
#: spelled for a posterior/anterior tooth.
_SURFACE_ORDER: dict[str, int] = {"M": 0, "O": 1, "I": 1, "D": 2, "B": 3, "F": 3, "L": 4}
ANTERIOR_SURFACES: tuple[str, ...] = ("M", "I", "D", "F", "L")
POSTERIOR_SURFACES: tuple[str, ...] = ("M", "O", "D", "B", "L")
_TO_ANTERIOR = {"O": "I", "B": "F"}
_TO_POSTERIOR = {"I": "O", "F": "B"}
CLASS_V_SUFFIX = "5"
CLASS_V_SURFACES: tuple[str, ...] = ("B", "F", "L")

QUADRANTS: tuple[str, ...] = ("UR", "UL", "LL", "LR", "UA", "LA", "FM")
QUADRANT_LABELS: dict[str, str] = {
    "UR": "Upper Right", "UL": "Upper Left", "LL": "Lower Left", "LR": "Lower Right",
    "UA": "Upper Arch", "LA": "Lower Arch", "FM": "Full Mouth",
}
TRUE_QUADRANTS: tuple[str, ...] = ("UR", "UL", "LL", "LR")
#: ADA-BE-11: the ADA claim form's Item 25 "Area of Oral Cavity" two-digit code
#: for every quadrant token the API stores (plus the legacy numeric quadrant
#: ids the migration left in a handful of rows). Published on
#: /metadata/procedure-entry-rules and /metadata/ada-claim-form-rules so the
#: print and the validator can never disagree on the token set.
AREA_OF_ORAL_CAVITY: dict[str, str] = {
    "FM": "00", "UA": "01", "LA": "02", "UR": "10", "UL": "20", "LL": "30", "LR": "40",
    "1": "10", "2": "20", "3": "30", "4": "40",
}

PERMANENT_ANTERIOR: frozenset[int] = frozenset(range(6, 12)) | frozenset(range(22, 28))
PRIMARY_LETTERS = "ABCDEFGHIJKLMNOPQRST"
PRIMARY_ANTERIOR: frozenset[str] = frozenset("CDEFGH") | frozenset("MNOPQR")
SUPERNUMERARY_OFFSET = 50

_PERMANENT_RE = re.compile(r"^(\d{1,2})$")
_PRIMARY_RE = re.compile(r"^([A-T])(S?)$")

VALID_TOOTH_AREAS: tuple[str, ...] = ("anterior", "posterior")


def anterior_teeth() -> list[str]:
    """Every Universal tooth id that is anterior (permanent + primary)."""
    return [str(n) for n in sorted(PERMANENT_ANTERIOR)] + sorted(PRIMARY_ANTERIOR)


def posterior_teeth() -> list[str]:
    return [str(n) for n in range(1, 33) if n not in PERMANENT_ANTERIOR] + [
        c for c in PRIMARY_LETTERS if c not in PRIMARY_ANTERIOR
    ]


# ── tooth parsing ────────────────────────────────────────────────────────────
class Tooth:
    """A parsed tooth/area value. ``kind`` is ``permanent`` / ``primary`` /
    ``quadrant``; ``anterior`` is None for a quadrant."""

    __slots__ = ("raw", "kind", "base", "supernumerary", "anterior")

    def __init__(self, raw: str, kind: str, base: str, supernumerary: bool, anterior: bool | None):
        self.raw = raw
        self.kind = kind
        self.base = base  # the non-supernumerary tooth this maps to ("8", "K")
        self.supernumerary = supernumerary
        self.anterior = anterior

    @property
    def is_quadrant(self) -> bool:
        return self.kind == "quadrant"


def parse_tooth(value: Any) -> Tooth | None:  # noqa: ANN401
    """Parse a Universal tooth id (or a legacy quadrant-in-tooth code).

    Returns None for an empty value; raises :class:`ValidationError`
    (``invalid_tooth``) for anything unrecognised.
    """
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in QUADRANTS:
        return Tooth(text, "quadrant", text, False, None)
    m = _PERMANENT_RE.match(text)
    if m:
        number = int(m.group(1))
        super_ = False
        if SUPERNUMERARY_OFFSET + 1 <= number <= SUPERNUMERARY_OFFSET + 32:
            number -= SUPERNUMERARY_OFFSET
            super_ = True
        if 1 <= number <= 32:
            return Tooth(text, "permanent", str(number), super_, number in PERMANENT_ANTERIOR)
    m = _PRIMARY_RE.match(text)
    if m:
        letter = m.group(1)
        return Tooth(text, "primary", letter, bool(m.group(2)), letter in PRIMARY_ANTERIOR)
    raise ValidationError(
        f"'{value}' is not a valid tooth (Universal 1-32 / A-T, supernumerary 51-82 / AS-TS, "
        "or a quadrant code)",
        details={"code": "invalid_tooth", "field": "tooth", "value": value},
    )


def normalise_quadrant(value: Any) -> str | None:  # noqa: ANN401
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text not in QUADRANTS:
        raise ValidationError(
            f"'{value}' is not a valid quadrant ({', '.join(QUADRANTS)})",
            details={"code": "invalid_quadrant", "field": "quadrant", "value": value,
                     "allowed": list(QUADRANTS)},
        )
    return text


# ── surface normalisation ────────────────────────────────────────────────────
_SEPARATORS = re.compile(r"[\s,;/|+\-]+")


def surface_tokens(value: Any) -> list[str]:  # noqa: ANN401
    """``"d,o m"`` → ``["D", "O", "M"]``; ``"B5L"`` → ``["B5", "L"]``.

    Raises ``invalid_surface`` on any character outside the vocabulary or a
    Class V suffix on a surface that cannot carry one.
    """
    if value is None:
        return []
    text = _SEPARATORS.sub("", str(value)).upper()
    if not text:
        return []
    tokens: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch not in SURFACE_LETTERS:
            raise ValidationError(
                f"'{value}' is not a valid surface (letters {''.join(SURFACE_LETTERS)}, "
                f"Class V as B5/F5/L5)",
                details={"code": "invalid_surface", "field": "surface", "value": value,
                         "allowed": list(SURFACE_LETTERS)},
            )
        token = ch
        if i + 1 < len(text) and text[i + 1] == CLASS_V_SUFFIX:
            if ch not in CLASS_V_SURFACES:
                raise ValidationError(
                    f"Class V ('{ch}5') is only valid on a buccal/facial/lingual surface",
                    details={"code": "invalid_surface", "field": "surface", "value": value,
                             "class_v_surfaces": list(CLASS_V_SURFACES)},
                )
            token += CLASS_V_SUFFIX
            i += 1
        tokens.append(token)
        i += 1
    return tokens


def _spell_for_arch(letter: str, tooth: Tooth | None) -> str:
    if tooth is None or tooth.anterior is None:
        return letter
    if tooth.anterior:
        return _TO_ANTERIOR.get(letter, letter)
    return _TO_POSTERIOR.get(letter, letter)


def normalise_surface(value: Any, tooth: Tooth | None = None) -> str | None:  # noqa: ANN401
    """Canonical surface string: arch-correct letters, M·O/I·D·B/F·L order,
    duplicates collapsed (a Class-V-qualified letter wins over its plain twin).
    Returns None for an empty value."""
    tokens = surface_tokens(value)
    if not tokens:
        return None
    chosen: dict[str, str] = {}
    for token in tokens:
        letter = _spell_for_arch(token[0], tooth)
        qualified = letter + token[1:]
        current = chosen.get(letter)
        if current is None or (len(qualified) > len(current)):
            chosen[letter] = qualified
    ordered = sorted(
        chosen.values(), key=lambda t: (_SURFACE_ORDER[t[0]], SURFACE_LETTERS.index(t[0]), t)
    )
    return "".join(ordered)


def surface_count(value: Any) -> int:  # noqa: ANN401
    return len(surface_tokens(value))


# ── requirement rules from a procedure_codes row ─────────────────────────────
def _as_dict(value: Any) -> dict:  # noqa: ANN401
    return value if isinstance(value, dict) else {}


def _tooth_area(code_row: ProcedureCode) -> str | None:
    area = (code_row.tooth_area or "").strip().lower()
    return area if area in VALID_TOOTH_AREAS else None


def surface_bounds(code_row: ProcedureCode) -> tuple[int | None, int | None]:
    """(min, max) surfaces the code accepts. ``surface_rules`` wins over the flat
    ``min_surfaces``/``max_surfaces`` pair; a code that requires a surface with
    neither set accepts 1..5."""
    rules = _as_dict(code_row.surface_rules)
    lo = rules.get("min", code_row.min_surfaces)
    hi = rules.get("max", code_row.max_surfaces)
    if code_row.requires_surface:
        lo = 1 if lo is None else lo
        hi = 5 if hi is None else hi
    return (int(lo) if lo is not None else None, int(hi) if hi is not None else None)


def allowed_surfaces(code_row: ProcedureCode) -> list[str] | None:
    allowed = _as_dict(code_row.surface_rules).get("allowed")
    if isinstance(allowed, list) and allowed:
        return [str(a).upper() for a in allowed]
    return None


def allowed_quadrants(code_row: ProcedureCode) -> list[str] | None:
    allowed = _as_dict(code_row.anatomy_rules).get("allowed_quadrants")
    if isinstance(allowed, list) and allowed:
        return [str(a).upper() for a in allowed]
    return None


def rules_for(code_row: ProcedureCode) -> dict:
    """The enforcement contract for one code, in the shape the pop-up consumes."""
    lo, hi = surface_bounds(code_row)
    area = _tooth_area(code_row)
    return {
        "code": code_row.code,
        "requires_tooth": bool(code_row.requires_tooth or code_row.requires_surface),
        "requires_surface": bool(code_row.requires_surface),
        "requires_quadrant": bool(code_row.requires_quadrant),
        "requires_lab": bool(code_row.requires_lab),
        "min_surfaces": lo,
        "max_surfaces": hi,
        "allowed_surfaces": allowed_surfaces(code_row),
        "tooth_area": area,
        "valid_teeth": list(code_row.valid_teeth) if code_row.valid_teeth else None,
        "allowed_quadrants": allowed_quadrants(code_row),
        "default_material_id": code_row.default_material_id,
        # PROC-7: supporting-records flags, advisory on posting (see
        # supporting_records_service for what satisfies each).
        **{flag: bool(getattr(code_row, flag, False)) for flag in SUPPORTING_RECORD_FLAGS},
    }


def _fail(code: str, field: str, message: str, **extra: Any) -> ValidationError:  # noqa: ANN401
    return ValidationError(message, details={"code": code, "field": field, **extra})


CLINICAL_FIELDS: tuple[str, ...] = ("procedure_code", "tooth", "surface", "quadrant")

#: PROC-7: the five supporting-records flags on ``procedure_codes``. Kept here
#: (next to the tooth/surface/quadrant flags) so ``rules_for`` and the
#: published metadata read them from one list; the *meaning* of each — what
#: counts as "on file" — is ``supporting_records_service.RULES``.
SUPPORTING_RECORD_FLAGS: tuple[str, ...] = (
    "requires_attachment",
    "requires_perio_chart",
    "requires_photo",
    "requires_xray",
    "requires_missing_tooth_info",
)


def touches_clinical_fields(data: dict) -> bool:
    return any(f in data for f in CLINICAL_FIELDS)


def validate_entry(
    db: Session,
    merged: dict,
    *,
    code_row: ProcedureCode | None = None,
    enforce: bool = True,
) -> dict:
    """Normalise ``tooth``/``surface``/``quadrant`` and enforce the code's rules.

    ``merged`` is the payload overlaid on the stored row (or the payload alone
    on create). Returns the canonical values for the three fields — the caller
    writes back whichever ones its payload carried. Raises 422 on any breach.
    ``enforce=False`` normalises only (used for the catalogue tables, whose rows
    are templates that may legitimately leave the tooth to be chosen later).
    """
    tooth = parse_tooth(merged.get("tooth"))
    quadrant = normalise_quadrant(merged.get("quadrant"))
    if quadrant is None and tooth is not None and tooth.is_quadrant:
        quadrant = tooth.raw  # legacy quadrant-in-tooth, mirrored (see module doc)
    surface = normalise_surface(merged.get("surface"), None if tooth is None or tooth.is_quadrant else tooth)

    out = {
        "tooth": tooth.raw if tooth is not None else None,
        "surface": surface,
        "quadrant": quadrant,
    }
    if not enforce:
        return out

    code = merged.get("procedure_code")
    if code_row is None and code:
        code_row = db.get(ProcedureCode, code)
    if code_row is None:
        return out
    rules = rules_for(code_row)
    real_tooth = tooth if (tooth is not None and not tooth.is_quadrant) else None

    if rules["requires_tooth"] and real_tooth is None:
        raise _fail("tooth_required", "tooth", f"{code} requires a tooth number")

    if real_tooth is not None:
        valid = rules["valid_teeth"]
        if valid and real_tooth.base not in {str(v).upper() for v in valid} \
                and real_tooth.raw not in {str(v).upper() for v in valid}:
            raise _fail("tooth_not_allowed", "tooth",
                        f"Tooth {real_tooth.raw} is not valid for {code}",
                        valid_teeth=list(valid))
        area = rules["tooth_area"]
        if area == "anterior" and real_tooth.anterior is False:
            raise _fail("tooth_not_allowed", "tooth",
                        f"{code} is an anterior-only procedure; tooth {real_tooth.raw} is posterior",
                        tooth_area=area)
        if area == "posterior" and real_tooth.anterior is True:
            raise _fail("tooth_not_allowed", "tooth",
                        f"{code} is a posterior-only procedure; tooth {real_tooth.raw} is anterior",
                        tooth_area=area)

    if rules["requires_surface"]:
        if not surface:
            raise _fail("surface_required", "surface", f"{code} requires at least one surface")
        tokens = surface_tokens(surface)
        lo, hi = rules["min_surfaces"], rules["max_surfaces"]
        if (lo is not None and len(tokens) < lo) or (hi is not None and len(tokens) > hi):
            expect = f"exactly {lo}" if lo == hi else f"between {lo} and {hi}"
            raise _fail("surface_count", "surface",
                        f"{code} expects {expect} surface(s); {len(tokens)} given",
                        min_surfaces=lo, max_surfaces=hi, count=len(tokens))
        allowed = rules["allowed_surfaces"]
        if allowed:
            allowed_set = {a[0] for a in allowed}
            # O/I and B/F name the same surface; a rule written for one arch must
            # not reject the other arch's spelling of it.
            for a in list(allowed_set):
                allowed_set.add(_TO_ANTERIOR.get(a, a))
                allowed_set.add(_TO_POSTERIOR.get(a, a))
            bad = [t for t in tokens if t[0] not in allowed_set]
            if bad:
                raise _fail("surface_not_allowed", "surface",
                            f"Surface(s) {', '.join(bad)} are not valid for {code}",
                            allowed=list(allowed))
    elif surface and (lo_hi := surface_bounds(code_row))[1] is not None \
            and surface_count(surface) > lo_hi[1]:
        raise _fail("surface_count", "surface",
                    f"{code} accepts at most {lo_hi[1]} surface(s)",
                    min_surfaces=lo_hi[0], max_surfaces=lo_hi[1], count=surface_count(surface))

    if rules["requires_quadrant"]:
        if quadrant is None:
            raise _fail("quadrant_required", "quadrant", f"{code} requires a quadrant")
        allowed_q = rules["allowed_quadrants"]
        if allowed_q and quadrant not in allowed_q:
            raise _fail("quadrant_not_allowed", "quadrant",
                        f"Quadrant {quadrant} is not valid for {code}", allowed=allowed_q)

    return out


def apply_entry_rules(
    db: Session,
    data: dict,
    current: Any = None,  # noqa: ANN401
    *,
    enforce: bool = True,
) -> dict:
    """Run :func:`validate_entry` for a CRUD write and fold the canonical values
    back into ``data`` (a copy). ``current`` is the stored row on an update; when
    the payload touches none of the clinical fields the rules are skipped.
    """
    payload = dict(data)
    if current is not None and not touches_clinical_fields(payload):
        return payload
    merged = {
        f: (payload[f] if f in payload else getattr(current, f, None))
        for f in CLINICAL_FIELDS
    }
    canonical = validate_entry(db, merged, enforce=enforce)
    for field in ("tooth", "surface", "quadrant"):
        if field in payload:
            payload[field] = canonical[field]
    # A legacy quadrant-in-tooth write mirrors into `quadrant` even when the
    # payload did not name it, so the typed column stops being empty.
    if canonical["quadrant"] and "quadrant" not in payload and "tooth" in payload:
        payload["quadrant"] = canonical["quadrant"]
    return payload


# ── catalogue templates (PROC-INT-9) ─────────────────────────────────────────
class ProcedureTemplateCRUD(CRUDBase):
    """``code_bundle_items`` / ``explosion_code_items``: canonicalise tooth /
    surface / quadrant on write but do **not** enforce the code's requirements —
    a template row legitimately leaves the tooth to be chosen when the bundle is
    applied to a patient."""

    def create(self, db: Session, data: dict, *, tenant_id=None, created_by=None):  # noqa: ANN001, ANN201
        return super().create(
            db, apply_entry_rules(db, data, enforce=False), tenant_id=tenant_id, created_by=created_by
        )

    def update(self, db: Session, obj_id, data: dict, *, tenant_id=None, updated_by=None):  # noqa: ANN001, ANN201
        current = self.get(db, obj_id, tenant_id=tenant_id)
        return super().update(
            db, obj_id, apply_entry_rules(db, data, current, enforce=False),
            tenant_id=tenant_id, updated_by=updated_by,
        )


# ── published contract ───────────────────────────────────────────────────────
def _supporting_rules_catalog() -> list[dict]:
    # Lazy: supporting_records_service imports the flag list from this module.
    from app.services.supporting_records_service import rules_catalog
    return rules_catalog()


def _supporting_error_code(flag: str) -> str:
    """``requires_xray`` -> ``xray_required`` (the per-procedure error code)."""
    return f"{flag.removeprefix('requires_')}_required"


ERROR_CODES: dict[str, str] = {
    "invalid_tooth": "tooth is not a Universal tooth id, supernumerary id or quadrant code",
    "invalid_surface": "surface contains a character outside the vocabulary or a misplaced Class V",
    "invalid_quadrant": "quadrant is not one of the seven quadrant/arch codes",
    "tooth_required": "the code requires a tooth and none was given",
    "tooth_not_allowed": "the tooth is outside the code's valid_teeth / tooth_area",
    "surface_required": "the code requires a surface and none was given",
    "surface_count": "the surface count is outside the code's min/max",
    "surface_not_allowed": "a surface letter is outside the code's allowed set",
    "quadrant_required": "the code requires a quadrant and none was given",
    "quadrant_not_allowed": "the quadrant is outside the code's allowed_quadrants",
    # PROC-7b/c: raised only by claim submission (never by posting a charge);
    # ``details.missing`` lists each procedure with the records it still lacks.
    "supporting_records_missing": "a procedure on the claim requires a supporting record "
                                  "(attachment / perio chart / photo / x-ray / missing-tooth "
                                  "info) that is not on file; allow_missing_records overrides",
    "attachment_required": "requires_attachment and no document is linked to the procedure "
                           "or its claim",
    "perio_chart_required": "requires_perio_chart and no perio exam is on file on/before the "
                            "date of service (within the configured age)",
    "photo_required": "requires_photo and no patient photo is on file",
    "xray_required": "requires_xray and no radiograph is on file on/before the date of service",
    "missing_tooth_info_required": "requires_missing_tooth_info and no charted missing tooth "
                                   "with a date, or posted extraction, is on file",
}


def rules_metadata() -> dict:
    """The vocabulary + enforcement contract for ``GET /metadata/procedure-entry-rules``."""
    return {
        "surfaces": [
            {
                "code": s,
                "label": SURFACE_LABELS[s],
                "arch": "anterior" if s in ("I", "F") else "posterior" if s in ("O", "B") else "any",
                "equivalent": _TO_ANTERIOR.get(s) or _TO_POSTERIOR.get(s),
                "class_v_allowed": s in CLASS_V_SURFACES,
            }
            for s in SURFACE_LETTERS
        ],
        "surface_order": ["M", "O/I", "D", "B/F", "L"],
        "surface_storage": "concatenated letters in canonical order, e.g. MOD, MIFL, B5",
        "class_v": {
            "kind": "qualifier",
            "suffix": CLASS_V_SUFFIX,
            "on_surfaces": list(CLASS_V_SURFACES),
            "counts_as_surfaces": 1,
            "note": "Class V is a location on a facial/lingual surface, not an extra surface; "
                    "stored as B5/F5/L5 and counted once toward the code's surface count.",
        },
        "anterior_surfaces": list(ANTERIOR_SURFACES),
        "posterior_surfaces": list(POSTERIOR_SURFACES),
        "quadrants": [{"code": q, "label": QUADRANT_LABELS[q]} for q in QUADRANTS],
        "true_quadrants": list(TRUE_QUADRANTS),
        # ADA-BE-11: quadrant token -> ADA claim form Item 25 code.
        "area_of_oral_cavity": [{"token": k, "code": v} for k, v in AREA_OF_ORAL_CAVITY.items()],
        "teeth": {
            "system": "universal",
            "permanent": [str(n) for n in range(1, 33)],
            "primary": list(PRIMARY_LETTERS),
            "supernumerary": {
                "permanent": f"tooth + {SUPERNUMERARY_OFFSET} (51-82)",
                "primary": "letter + 'S' (AS-TS)",
            },
            "anterior": anterior_teeth(),
            "posterior": posterior_teeth(),
            "legacy_quadrant_in_tooth": True,
        },
        "enforced": {
            "requires_tooth": True,
            "requires_surface": True,
            "requires_quadrant": True,
            "valid_teeth": True,
            "tooth_area": True,
            "surface_count": True,
            "requires_lab": False,
        },
        "advisory": {
            "requires_lab": "material_id is recommended, never a 422 — chart_materials is "
                            "tenant-scoped and several posting paths have no material picker",
            # PROC-7b: advisory on posting, enforced at claim submission. The
            # record is usually captured after the chair (the x-ray is taken,
            # the narrative written, the photo uploaded), so a 422 on POST
            # patient_procedures would block the charge that the record is
            # about. GET /patients/{id}/procedure-readiness is the checklist.
            **{
                flag: f"checked by GET /patients/{{id}}/procedure-readiness and enforced at "
                      f"POST /insurance-claims/{{id}}/submit (422 supporting_records_missing, "
                      f"per-procedure code {_supporting_error_code(flag)}); never a 422 on "
                      f"posting a charge or a treatment-plan item"
                for flag in SUPPORTING_RECORD_FLAGS
            },
        },
        "supporting_records": {
            "flags": list(SUPPORTING_RECORD_FLAGS),
            "enforced_at": "claim_submit",
            "enforce_on_submit": bool(settings.SUPPORTING_RECORDS_ENFORCE_ON_SUBMIT),
            "override": "allow_missing_records on ClaimSubmitRequest",
            "readiness": [
                "GET /patients/{patient_id}/procedure-readiness?procedure_code=&tooth=&date_of_service=",
                "GET /patient-procedures/{procedure_id}/readiness",
                "GET /insurance-claims/{claim_id}/readiness",
            ],
            "perio_max_age_months": settings.SUPPORTING_RECORDS_PERIO_MAX_AGE_MONTHS,
            "rules": _supporting_rules_catalog(),
        },
        "update_semantics": "rules run on PATCH only when the payload touches "
                            "procedure_code/tooth/surface/quadrant, against the merge of payload "
                            "and stored row",
        "error_codes": ERROR_CODES,
        "applies_to": [
            "patient_procedures", "treatment_plan_items",
            "code_bundle_items (normalise only)", "explosion_code_items (normalise only)",
        ],
    }
