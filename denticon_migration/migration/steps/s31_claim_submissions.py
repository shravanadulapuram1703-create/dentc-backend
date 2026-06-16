"""
STEP 31 — claim_submissions
Source: ClaimsDetail.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.bulk import BulkBuffer
from migration.utils.parsers import clean, parse_decimal, parse_int, parse_bool

COLS = [
    "claim_id", "legacy_id", "batch_id", "is_preauth",
    "total_charges", "num_lines", "submission_status", "claim_text",
]


def run(conn, maps: dict) -> dict:
    claim_map = maps.get("claim_map", {})

    src = cfg.src("ClaimsDetail.txt")
    if not src.exists():
        print("  [s31] claim_submissions: file not found, skipping")
        return {}

    skipped = 0
    buf = BulkBuffer(
        conn, "claim_submissions", COLS,
        conflict="ON CONFLICT DO NOTHING",
        flush_every=20000, page_size=2000, label="claim_submissions",
    )

    for row in read_denticon_file(src):
        claim_id = (row.get("CLAIMID") or "").strip()
        claim_pk = claim_map.get(claim_id)
        if not claim_pk:
            skipped += 1
            continue

        buf.add((
            claim_pk, claim_id,
            clean(row.get("CLAIMBATCHID")),
            parse_bool(row.get("ISPREAUTH", "False")),
            parse_decimal(row.get("TOTALCHARGES") or "0"),
            parse_int(row.get("NUMLINES")),
            clean(row.get("STATUS")),
            clean(row.get("CLAIMTEXT")),   # raw EDI X12 text — stored as-is
        ))

    buf.flush()
    print(f"  [s31] claim_submissions: {buf.inserted} inserted, {skipped} skipped")
    return {}
