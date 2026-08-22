"""Seed the CDT tooth / surface / quadrant / lab requirement flags and default
chair time on ``procedure_codes`` (APPT-8, APPT-9).

Why this exists
---------------
``requires_tooth`` / ``requires_surface`` / ``requires_quadrant`` / ``requires_lab``
were **false across the whole catalog** — including codes that clinically cannot
be posted without a tooth (D2391 "Resin Composite One Surface Posterior" needs
both a tooth *and* a surface). With every flag false the appointment procedure
picker can never enforce anything, so it has to fall back to a manual "Edit".
``default_duration_minutes`` was likewise NULL everywhere, so **Calc Time** had
nothing to add up and every line defaulted to 30 minutes.

The rules below are derived from the **CDT code families** (the leading
``D<category><series>`` structure of the ADA code set), not from a licensed CDT
data file — the ADA's own descriptor text is copyrighted, but the range
structure (D2xxx = restorative, D3xxx = endodontics, …) is the published
taxonomy the codes are organised by. Each rule is stated as an explicit,
reviewable range so a practice can audit and override it.

Fees (APPT-9)
-------------
``default_fee`` is deliberately **not** invented here. Fee schedules are the
intended source of truth — the estimate engine and the picker both price through
``resolve_procedure_fee`` against the patient/office/provider schedule. The only
supported fee seeding is copying a real schedule the practice already maintains
into the catalog default, so codes with no schedule entry stop pricing at $0::

    python -m scripts.seed_procedure_code_rules --fee-schedule-id 12 --apply

Usage
-----
Dry-run by default — it prints what would change and writes nothing::

    python -m scripts.seed_procedure_code_rules                 # report only
    python -m scripts.seed_procedure_code_rules --apply         # write
    python -m scripts.seed_procedure_code_rules --apply --overwrite
    python -m scripts.seed_procedure_code_rules --csv rules.csv --apply

Without ``--overwrite`` a column that already holds a non-default value is left
alone: a practice that has hand-tuned D2740's chair time keeps it. ``--csv``
takes precedence over the built-in ranges for the codes it names; columns it
omits fall back to the derived value::

    code,requires_tooth,requires_surface,requires_quadrant,requires_lab,default_duration_minutes
    D2391,true,true,false,false,60
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FeeScheduleEntry, ProcedureCode
from app.db.session import SessionLocal

_FLAGS = ("requires_tooth", "requires_surface", "requires_quadrant", "requires_lab")

# ── CDT family rules ─────────────────────────────────────────────────────────
# (low, high, requires_tooth, requires_surface, requires_quadrant, requires_lab,
#  default_duration_minutes, note). Ranges are inclusive and scanned in order —
# the FIRST match wins, so narrow exceptions are listed before the wide family.
_RULES: tuple[tuple[int, int, bool, bool, bool, bool, int, str], ...] = (
    # ── D0xxx Diagnostic ─────────────────────────────────────────────────────
    (120, 120, False, False, False, False, 30, "periodic oral evaluation"),
    (140, 140, False, False, False, False, 30, "limited/problem-focused evaluation"),
    (150, 150, False, False, False, False, 60, "comprehensive evaluation"),
    (160, 180, False, False, False, False, 60, "detailed / comprehensive perio evaluation"),
    (210, 210, False, False, False, False, 30, "intraoral complete series"),
    (220, 230, True, False, False, False, 15, "intraoral periapical — tooth-specific"),
    (270, 277, False, False, False, False, 15, "bitewings"),
    (330, 340, False, False, False, False, 20, "panoramic / cephalometric"),
    (350, 395, False, False, False, False, 20, "photographic / 3-D imaging"),
    (460, 460, True, False, False, False, 15, "pulp vitality test — tooth-specific"),
    (1, 999, False, False, False, False, 30, "diagnostic (default)"),
    # ── D1xxx Preventive ─────────────────────────────────────────────────────
    (1110, 1110, False, False, False, False, 60, "prophylaxis — adult"),
    (1120, 1120, False, False, False, False, 30, "prophylaxis — child"),
    (1206, 1208, False, False, False, False, 15, "topical fluoride"),
    (1310, 1330, False, False, False, False, 15, "nutritional / OH instruction"),
    (1351, 1354, True, False, False, False, 20, "sealant / interim caries arresting — per tooth"),
    (1510, 1575, False, False, True, True, 30, "space maintainer — unilateral, lab-fabricated"),
    (1000, 1999, False, False, False, False, 30, "preventive (default)"),
    # ── D2xxx Restorative ────────────────────────────────────────────────────
    (2140, 2161, True, True, False, False, 45, "amalgam restoration"),
    (2330, 2394, True, True, False, False, 60, "resin composite restoration"),
    (2410, 2430, True, True, False, False, 60, "gold foil restoration"),
    (2510, 2664, True, True, False, True, 90, "inlay / onlay — lab-fabricated"),
    (2710, 2799, True, False, False, True, 90, "crown — lab-fabricated"),
    (2910, 2921, True, False, False, False, 30, "recement / repair"),
    (2929, 2934, True, False, False, True, 60, "prefabricated crown"),
    (2940, 2941, True, False, False, False, 30, "protective / interim restoration"),
    (2949, 2957, True, False, False, False, 60, "core buildup / post and core"),
    (2960, 2962, True, True, False, False, 90, "labial veneer"),
    (2000, 2999, True, False, False, False, 60, "restorative (default)"),
    # ── D3xxx Endodontics ────────────────────────────────────────────────────
    (3110, 3120, True, False, False, False, 30, "pulp cap"),
    (3220, 3230, True, False, False, False, 45, "pulpotomy"),
    (3310, 3348, True, False, False, False, 90, "root canal therapy"),
    (3351, 3357, True, False, False, False, 60, "apexification"),
    (3410, 3470, True, False, False, False, 90, "apicoectomy / surgical endodontics"),
    (3000, 3999, True, False, False, False, 60, "endodontics (default)"),
    # ── D4xxx Periodontics ───────────────────────────────────────────────────
    (4210, 4210, False, False, True, False, 60, "gingivectomy — four or more teeth per quadrant"),
    (4211, 4212, True, False, False, False, 45, "gingivectomy — one to three teeth"),
    (4240, 4241, False, False, True, False, 90, "gingival flap procedure"),
    (4245, 4249, False, False, True, False, 90, "apically positioned flap / crown lengthening"),
    (4260, 4261, False, False, True, False, 120, "osseous surgery"),
    (4263, 4278, True, False, False, False, 90, "bone / soft-tissue graft — per site"),
    (4341, 4342, False, False, True, False, 60, "scaling and root planing — per quadrant"),
    (4346, 4346, False, False, False, False, 60, "scaling in the presence of inflammation"),
    (4355, 4355, False, False, False, False, 60, "full-mouth debridement"),
    (4381, 4381, True, False, False, False, 15, "localized antimicrobial — per tooth"),
    (4910, 4910, False, False, False, False, 60, "periodontal maintenance"),
    (4000, 4999, False, False, False, False, 60, "periodontics (default)"),
    # ── D5xxx Removable prosthodontics / maxillofacial ───────────────────────
    (5110, 5140, False, False, False, True, 60, "complete denture — lab"),
    (5211, 5286, False, False, False, True, 60, "partial denture — lab"),
    (5410, 5422, False, False, False, False, 30, "denture adjustment — chairside"),
    (5511, 5520, True, False, False, True, 45, "denture repair / replace missing tooth"),
    (5610, 5671, True, False, False, True, 45, "partial repair / replace tooth or clasp"),
    (5710, 5761, False, False, False, True, 60, "reline / rebase — lab"),
    (5810, 5821, False, False, False, True, 60, "interim denture — lab"),
    (5850, 5851, False, False, False, False, 30, "tissue conditioning — chairside"),
    (5900, 5999, False, False, False, True, 60, "maxillofacial prosthetics — lab"),
    (5000, 5999, False, False, False, True, 60, "removable prosthodontics (default)"),
    # ── D6xxx Implants and fixed prosthodontics ──────────────────────────────
    (6010, 6013, True, False, False, False, 90, "implant body placement — per site"),
    (6040, 6055, True, False, False, True, 120, "implant abutment / superstructure — lab"),
    (6056, 6199, True, False, False, True, 90, "implant-supported crown / retainer — lab"),
    (6200, 6999, True, False, False, True, 90, "fixed partial denture (bridge) — lab"),
    (6000, 6999, True, False, False, True, 90, "implant / fixed prosthodontics (default)"),
    # ── D7xxx Oral and maxillofacial surgery ─────────────────────────────────
    (7111, 7140, True, False, False, False, 30, "extraction — erupted tooth or exposed root"),
    (7210, 7251, True, False, False, False, 45, "surgical extraction"),
    (7260, 7297, False, False, False, False, 60, "oroantral / tooth transplantation / exposure"),
    (7310, 7321, False, False, True, False, 45, "alveoloplasty — per quadrant"),
    (7471, 7490, False, False, False, False, 60, "excision of bone tissue / reconstruction"),
    (7510, 7560, False, False, False, False, 30, "incision and drainage"),
    (7950, 7999, True, False, False, False, 60, "ridge augmentation / preservation — per site"),
    (7000, 7999, False, False, False, False, 45, "oral surgery (default)"),
    # ── D8xxx Orthodontics ───────────────────────────────────────────────────
    (8210, 8220, False, False, False, True, 30, "removable appliance therapy — lab"),
    (8000, 8999, False, False, False, False, 30, "orthodontics (default)"),
    # ── D9xxx Adjunctive ─────────────────────────────────────────────────────
    (9110, 9110, False, False, False, False, 30, "palliative treatment"),
    (9210, 9248, False, False, False, False, 15, "anaesthesia / sedation"),
    (9910, 9911, True, False, False, False, 15, "desensitizing — per tooth"),
    (9930, 9930, True, False, False, False, 30, "treatment of complications — per tooth"),
    (9000, 9999, False, False, False, False, 30, "adjunctive (default)"),
)

_CDT_RE = re.compile(r"^D(\d{4})$", re.IGNORECASE)


def derive(code: str) -> dict | None:
    """The requirement flags + chair time implied by ``code``'s CDT family.

    Returns ``None`` for anything that is not a ``D####`` CDT code (CPT/HCPCS
    medical codes, custom practice codes) — those carry no ADA taxonomy to
    derive from and must be seeded by CSV.
    """
    match = _CDT_RE.match(code.strip())
    if match is None:
        return None
    numeric = int(match.group(1))
    for low, high, tooth, surface, quadrant, lab, minutes, note in _RULES:
        if low <= numeric <= high:
            return {
                "requires_tooth": tooth,
                "requires_surface": surface,
                "requires_quadrant": quadrant,
                "requires_lab": lab,
                "default_duration_minutes": minutes,
                "_note": note,
            }
    return None


# Surface counts for the families where the CDT descriptor *is* the surface count
# (D2140 one surface, D2150 two, D2160 three, D2161 four or more — and the same
# ladder for the composite families). Feeds CHG-2 ``surface_rules`` so the
# enforcement modal has a real min/max instead of fabricating one client-side.
_SURFACE_COUNTS: dict[int, tuple[int, int]] = {
    2140: (1, 1), 2150: (2, 2), 2160: (3, 3), 2161: (4, 5),
    2330: (1, 1), 2331: (2, 2), 2332: (3, 3), 2335: (4, 5),
    2391: (1, 1), 2392: (2, 2), 2393: (3, 3), 2394: (4, 5),
    2410: (1, 1), 2420: (2, 2), 2430: (3, 3),
}
_ALL_SURFACES = ["M", "O", "D", "B", "L", "I", "F"]


def _surface_rules(code: str) -> dict | None:
    match = _CDT_RE.match(code.strip())
    if match is None:
        return None
    bounds = _SURFACE_COUNTS.get(int(match.group(1)))
    if bounds is None:
        return None
    return {"min": bounds[0], "max": bounds[1], "allowed": _ALL_SURFACES}


def _bool(value: str | None) -> bool | None:
    if value is None or value.strip() == "":
        return None
    return value.strip().lower() in ("1", "true", "yes", "y", "t")


def _int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def load_overrides(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    out: dict[str, dict] = {}
    for row in rows:
        code = (row.get("code") or "").strip()
        if not code:
            continue
        values: dict = {}
        for flag in _FLAGS:
            parsed = _bool(row.get(flag))
            if parsed is not None:
                values[flag] = parsed
        minutes = _int(row.get("default_duration_minutes"))
        if minutes is not None:
            values["default_duration_minutes"] = minutes
        out[code.upper()] = values
    return out


def seed(
    db: Session,
    *,
    overrides: dict[str, dict] | None = None,
    fee_schedule_id: int | None = None,
    overwrite: bool = False,
    apply_changes: bool = False,
) -> dict[str, int]:
    overrides = overrides or {}
    fees: dict[str, object] = {}
    if fee_schedule_id is not None:
        fees = {
            entry.procedure_code: entry.patient_fee
            for entry in db.execute(
                select(FeeScheduleEntry).where(
                    FeeScheduleEntry.fee_schedule_id == fee_schedule_id
                )
            ).scalars()
            if entry.patient_fee is not None
        }

    counts = {
        "scanned": 0, "unmatched": 0, "flags_set": 0,
        "durations_set": 0, "surface_rules_set": 0, "fees_set": 0,
    }
    for code_row in db.execute(select(ProcedureCode)).scalars():
        counts["scanned"] += 1
        derived = derive(code_row.code)
        override = overrides.get(code_row.code.upper(), {})
        if derived is None and not override:
            counts["unmatched"] += 1
            continue

        values = {k: v for k, v in (derived or {}).items() if not k.startswith("_")}
        values.update(override)

        # Requirement flags: only lift false → true unless --overwrite. A practice
        # that deliberately turned an enforcement off keeps it off.
        touched_flags = False
        for flag in _FLAGS:
            if flag not in values:
                continue
            current = bool(getattr(code_row, flag))
            wanted = bool(values[flag])
            if current == wanted:
                continue
            if current and not overwrite:
                continue  # a hand-set true is never silently cleared
            if apply_changes:
                setattr(code_row, flag, wanted)
            touched_flags = True
        if touched_flags:
            counts["flags_set"] += 1

        minutes = values.get("default_duration_minutes")
        if minutes is not None and (code_row.default_duration_minutes is None or overwrite):
            if apply_changes:
                code_row.default_duration_minutes = int(minutes)
            counts["durations_set"] += 1

        rules = _surface_rules(code_row.code)
        if rules is not None and (code_row.surface_rules is None or overwrite):
            if apply_changes:
                code_row.surface_rules = rules
            counts["surface_rules_set"] += 1

        fee = fees.get(code_row.code)
        if fee is not None and (not code_row.default_fee or overwrite):
            if apply_changes:
                code_row.default_fee = fee
            counts["fees_set"] += 1

    if apply_changes:
        db.commit()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="Per-code overrides (see module docstring)")
    parser.add_argument(
        "--fee-schedule-id", type=int,
        help="Copy this fee schedule's patient_fee into procedure_codes.default_fee (APPT-9)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace values that are already set (default: only fill blanks / lift false→true)",
    )
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()

    overrides = load_overrides(args.csv) if args.csv else {}
    with SessionLocal() as db:
        counts = seed(
            db,
            overrides=overrides,
            fee_schedule_id=args.fee_schedule_id,
            overwrite=args.overwrite,
            apply_changes=args.apply,
        )
    verb = "updated" if args.apply else "would update"
    print(
        f"scanned {counts['scanned']} code(s); {counts['unmatched']} not CDT-derivable\n"
        f"{verb}: {counts['flags_set']} requirement flag set(s), "
        f"{counts['durations_set']} duration(s), "
        f"{counts['surface_rules_set']} surface rule(s), "
        f"{counts['fees_set']} default fee(s)"
    )
    if not args.apply:
        print("dry run — nothing written. Re-run with --apply.")


if __name__ == "__main__":
    main()
