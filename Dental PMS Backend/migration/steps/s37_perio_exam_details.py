"""
STEP 37 — perio_exam_details
Source: PERIOCHARTDETAIL.txt
Returns: {}
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import parse_int, parse_bool, clean


def _pb(val: str) -> bool:
    return parse_bool(val)


def _pi(val: str):
    return parse_int(val)


def run(conn, maps: dict) -> dict:
    perio_exam_map = maps.get("perio_exam_map", {})

    src = cfg.src("PERIOCHARTDETAIL.txt")
    if not src.exists():
        print("  [s37] perio_exam_details: file not found, skipping")
        return {}

    cur = conn.cursor()
    inserted = skipped = 0

    for row in read_denticon_file(src):
        exam_leg = (row.get("PerioExamID") or row.get("PERIOEXAMID") or "").strip()
        exam_id  = perio_exam_map.get(exam_leg)
        tooth    = clean(row.get("TOOTHNO") or row.get("TOOTH"))

        if not exam_id or not tooth:
            skipped += 1
            continue

        cur.execute(
            """
            INSERT INTO perio_exam_details (
                exam_id, tooth_no,
                pd1,pd2,pd3,pd4,pd5,pd6,
                fgm1,fgm2,fgm3,fgm4,fgm5,fgm6,
                mgj1,mgj2,mgj3,mgj4,mgj5,mgj6,
                bleed1,bleed2,bleed3,bleed4,bleed5,bleed6,
                supp1,supp2,supp3,supp4,supp5,supp6,
                furc1,furc2,furc3,furc4,furc5,furc6,
                mobility_buccal, mobility_lingual
            ) VALUES (
                %s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,
                %s,%s
            )
            ON CONFLICT DO NOTHING
            """,
            (
                exam_id, tooth,
                _pi(row.get("PD1","")), _pi(row.get("PD2","")), _pi(row.get("PD3","")),
                _pi(row.get("PD4","")), _pi(row.get("PD5","")), _pi(row.get("PD6","")),
                _pi(row.get("FGM1","")), _pi(row.get("FGM2","")), _pi(row.get("FGM3","")),
                _pi(row.get("FGM4","")), _pi(row.get("FGM5","")), _pi(row.get("FGM6","")),
                _pi(row.get("MGJ1","")), _pi(row.get("MGJ2","")), _pi(row.get("MGJ3","")),
                _pi(row.get("MGJ4","")), _pi(row.get("MGJ5","")), _pi(row.get("MGJ6","")),
                _pb(row.get("Bleeding1","")), _pb(row.get("Bleeding2","")),
                _pb(row.get("Bleeding3","")), _pb(row.get("Bleeding4","")),
                _pb(row.get("Bleeding5","")), _pb(row.get("Bleeding6","")),
                _pb(row.get("Suppuration1","")), _pb(row.get("Suppuration2","")),
                _pb(row.get("Suppuration3","")), _pb(row.get("Suppuration4","")),
                _pb(row.get("Suppuration5","")), _pb(row.get("Suppuration6","")),
                _pi(row.get("Furcation1","")), _pi(row.get("Furcation2","")),
                _pi(row.get("Furcation3","")), _pi(row.get("Furcation4","")),
                _pi(row.get("Furcation5","")), _pi(row.get("Furcation6","")),
                _pi(row.get("Mobility2","")),   # buccal
                _pi(row.get("Mobility5","")),   # lingual
            ),
        )
        inserted += 1

        if inserted % 2000 == 0:
            conn.commit()

    conn.commit()
    print(f"  [s37] perio_exam_details: {inserted} inserted, {skipped} skipped")
    return {}
