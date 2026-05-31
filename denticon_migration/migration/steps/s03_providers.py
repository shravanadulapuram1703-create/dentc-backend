"""
STEP 3 — providers
Source: Providers.txt
Returns: { providerid_str: provider_varchar_pk }
Note: providers.id is VARCHAR(50), set as "PRV-{PROVIDERID}" for determinism.
"""

from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, map_provider_type, lookup


def run(conn, maps: dict) -> dict:
    tenant_map = maps["tenant_map"]
    office_map = maps["office_map"]
    default_tid = next(iter(tenant_map.values()))
    default_oid = next(iter(office_map.values()))

    src = cfg.src("Providers.txt")
    cur = conn.cursor()
    provider_map: dict[str, str] = {}
    inserted = skipped = 0

    for row in read_denticon_file(src):
        pid = (row.get("PROVIDERID") or "").strip()
        if not pid:
            skipped += 1
            continue

        db_id = f"PRV-{pid}"
        pgid = (row.get("PGID") or "").strip()
        oid  = (row.get("OID") or "").strip()
        tenant_id = tenant_map.get(pgid, default_tid)
        office_id = office_map.get(oid, default_oid)

        fname = clean(row.get("FNAME") or row.get("FIRSTNAME") or "")
        lname = clean(row.get("LNAME") or row.get("LASTNAME") or "")
        name  = f"{fname or ''} {lname or ''}".strip() or f"Provider {pid}"

        cur.execute(
            """
            INSERT INTO providers (
                id, tenant_id, office_id, legacy_id, name, title,
                short_id, role, npi, license, tax_id, dea_id, specialty
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
                name      = EXCLUDED.name,
                is_active = TRUE
            """,
            (
                db_id, tenant_id, office_id, pid, name,
                clean(row.get("TITLE")),
                clean(row.get("SHORTID")),
                map_provider_type(row.get("PROVIDERTYPE", "")),
                clean(row.get("NPI")),
                clean(row.get("LICENSE")),
                clean(row.get("TAXID") or row.get("TAX_ID")),
                clean(row.get("DEAID") or row.get("DEA_ID")),
                clean(row.get("SPECIALTY")),
            ),
        )
        provider_map[pid] = db_id
        inserted += 1

    conn.commit()
    print(f"  [s03] providers: {inserted} upserted, {skipped} skipped → map size {len(provider_map)}")
    return provider_map
