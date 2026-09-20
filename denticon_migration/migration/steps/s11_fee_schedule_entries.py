"""
STEP 11 — fee_schedule_entries
Source: FeeScheD.txt
Depends on: fee_schedules, procedure_codes
Returns: {}

Pricing hierarchy R1 (Alembic ``d4f1a9c7b3e2``) changed two things here:

* the uniqueness key became ``(fee_schedule_id, procedure_code, effective_date)``,
  because the old ``(fee_schedule_id, procedure_code)`` made a *dated* price list
  impossible — a second, later-dated fee for the same code was refused by the
  database, which is why Setup had to overwrite prices in place. The upsert target
  moves with it, or a re-run raises "no unique or exclusion constraint matching
  the ON CONFLICT specification".
* ``AMBCODE`` and ``tenant_id`` are now carried. ``FeeScheD.AMBCODE`` is the
  alternate-benefit code the carrier actually pays on (``D2391A`` -> ``D2140``:
  posterior composite downgraded to amalgam) and is set on 39 source rows, 36 of
  them that pattern across the PPO carrier schedules; the column existed but this
  step never mapped it, so it was NULL on all 13,493 rows. ``tenant_id`` closes a
  cross-tenant hole: the table had no tenant column, and ``CRUDBase`` only scopes
  models that carry one.

``PATAMT`` is blank on 2,884 source rows and ``parse_decimal`` turns a blank into
``0``, which the resolver used to accept as a real price and post as a $0 charge.
Blanks are now loaded as NULL so "no price on this list" stays distinct from "free",
which is what ``is_no_charge`` is for.
"""

from datetime import date

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import parse_decimal, parse_date, clean

COLS = [
    "tenant_id", "fee_schedule_id", "procedure_code", "patient_fee", "insurance_fee",
    "amb_code", "effective_date",
]

#: Junk in the source AMBCODE column (a stray backtick, a stray amount).
_AMB_JUNK = {"`", "78.00"}


def _amb_code(raw: str | None) -> str | None:
    """An alternate-benefit code, or None for the junk values in the export."""
    value = clean(raw)
    if not value or value in _AMB_JUNK:
        return None
    return value[:20]


def _money(raw: str | None):
    """A blank amount is *no price*, not 0.00 — see the module docstring."""
    if raw is None or str(raw).strip() == "":
        return None
    return parse_decimal(raw)


def run(conn, maps: dict) -> dict:
    fee_sched_map = maps["fee_sched_map"]
    proc_code_set = maps.get("proc_code_set", set())
    tenant_map = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("FeeScheD.txt")
    skipped = 0
    buf = BulkBuffer(
        conn, "fee_schedule_entries", COLS,
        conflict=(
            "ON CONFLICT (fee_schedule_id, procedure_code, effective_date) DO UPDATE SET "
            "patient_fee = EXCLUDED.patient_fee, "
            "insurance_fee = EXCLUDED.insurance_fee, "
            "amb_code = EXCLUDED.amb_code, "
            "tenant_id = EXCLUDED.tenant_id"
        ),
        dedup_index=(
            COLS.index("fee_schedule_id"), COLS.index("procedure_code"), COLS.index("effective_date"),
        ),
        flush_every=20000, page_size=2000, label="fee_schedule_entries",
    )

    for row in read_denticon_file(src):
        feeid = (row.get("FEEID") or "").strip()
        code  = (row.get("CODE") or row.get("ADACODE") or "").strip()
        fs_id = fee_sched_map.get(feeid)

        if not fs_id or not code or code not in proc_code_set:
            skipped += 1
            continue

        # A row with no effective date is open-ended: date it in the far past so
        # it prices every date of service rather than none (it is also half of the
        # uniqueness key, which cannot be NULL).
        effective = parse_date(row.get("EFFECTIVEDATE") or "") or date(1900, 1, 1)
        buf.add((
            tenant_map.get((row.get("PGID") or "").strip(), default_tid),
            fs_id, code,
            _money(row.get("PATAMT") or row.get("UCRAMOUNT")),
            _money(row.get("INSAMT")),
            _amb_code(row.get("AMBCODE")),
            effective,
        ))

    buf.flush()
    print(f"  [s11] fee_schedule_entries: {buf.inserted} inserted, {skipped} skipped")
    return {}
