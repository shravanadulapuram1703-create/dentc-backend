"""
STEP 3b — seed_users
Source: Providers.txt
Creates one user account per provider so that:
  - The application has usable login accounts immediately after migration
  - USERID string lookups in s40 (time_clock_entries) and s45 (perio_chart_settings) work

ID strategy: users.legacy_id = Denticon SHORTID (the login username string Denticon uses
in USERID fields of TCLOCK.txt and CHARTPERIOSETUP.txt).

Passwords: all migrated users receive a temporary password "ChangeMe123!"
that must be changed on first login (must_change_password = TRUE).

Also seeds one super_admin account for the tenant owner.

Returns: { shortid_str: user_db_id, providerid_str: user_db_id }
         (two keys per provider so both SHORTID and PROVIDERID lookups work)
"""

import hashlib
from migration.config import cfg
from migration.utils.reader import read_denticon_file
from migration.utils.parsers import clean, map_provider_type

# Temporary password hash — SHA-256 placeholder.
# In production replace with bcrypt: bcrypt.hashpw(b"ChangeMe123!", bcrypt.gensalt())
TEMP_PASSWORD_HASH = "sha256:" + hashlib.sha256(b"ChangeMe123!").hexdigest()

PROVIDER_ROLE_MAP = {
    "dentist":    "provider",
    "hygienist":  "provider",
    "staff":      "staff",
}


def run(conn, maps: dict) -> dict:
    tenant_map  = maps["tenant_map"]
    default_tid = next(iter(tenant_map.values()))

    src = cfg.src("Providers.txt")
    cur = conn.cursor()
    user_map: dict[str, int] = {}
    inserted = skipped = 0

    # ── Seed one super_admin account (tenant owner) ──────────────────────────
    pgid = cfg.DENTICON_PGID
    tid  = tenant_map.get(pgid, default_tid)
    cur.execute(
        """
        INSERT INTO users (tenant_id, legacy_id, email, username, password_hash,
                           first_name, last_name, role, must_change_password)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (username) DO NOTHING
        RETURNING id
        """,
        (
            tid, "ADMIN",
            "admin@dental.local",
            "admin",
            TEMP_PASSWORD_HASH,
            "Admin", "User",
            "super_admin",
            True,
        ),
    )
    row = cur.fetchone()
    if row:
        user_map["ADMIN"] = row[0]

    # ── One user per provider ────────────────────────────────────────────────
    for row in read_denticon_file(src):
        prov_id  = (row.get("PROVIDERID") or "").strip()
        short_id = (row.get("SHORTID") or "").strip()
        denticon_uid = clean(row.get("DENTICONUSERID"))
        if not prov_id:
            skipped += 1
            continue

        pgid = (row.get("PGID") or "").strip()
        tid  = tenant_map.get(pgid, default_tid)

        fname = clean(row.get("FNAME") or row.get("FIRSTNAME") or "Provider")
        lname = clean(row.get("LNAME") or row.get("LASTNAME") or prov_id)

        # legacy_id / username: prefer Denticon login id (used in TCLOCK, CHARTPERIOSETUP)
        legacy_id = denticon_uid or short_id or prov_id
        username  = (denticon_uid or short_id or f"prv{prov_id}").lower()[:50]

        # Build a unique email
        email = f"{username}@dental.local"

        prov_type = map_provider_type(row.get("PROVIDERTYPE", ""))
        role      = PROVIDER_ROLE_MAP.get(prov_type, "staff")

        cur.execute(
            """
            INSERT INTO users (tenant_id, legacy_id, email, username, password_hash,
                               first_name, last_name, role, must_change_password)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                legacy_id  = EXCLUDED.legacy_id,
                first_name = EXCLUDED.first_name,
                last_name  = EXCLUDED.last_name
            RETURNING id
            """,
            (
                tid, legacy_id, email, username, TEMP_PASSWORD_HASH,
                fname, lname, role, True,
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            row_id = cur.fetchone()

        db_id = row_id[0]
        # Register under all keys used by downstream USERID / SHORTID lookups
        user_map[prov_id] = db_id
        if short_id:
            user_map[short_id] = db_id
            user_map[short_id.lower()] = db_id
        if denticon_uid:
            user_map[denticon_uid] = db_id
            user_map[denticon_uid.lower()] = db_id
        user_map[username] = db_id
        inserted += 1

    # ── Staff users referenced in TCLOCK / CHARTPERIOSETUP but not in Providers ─
    known = {k.lower() for k in user_map}
    staff_ids: set[str] = set()
    for fname in ("TCLOCK.txt", "CHARTPERIOSETUP.txt"):
        fpath = cfg.src(fname)
        if not fpath.exists():
            continue
        for srow in read_denticon_file(fpath):
            uid = (srow.get("USERID") or "").strip()
            if uid and uid.lower() not in known:
                staff_ids.add(uid)

    staff_inserted = 0
    for uid in sorted(staff_ids):
        username = uid.lower()[:50]
        email = f"{username}@dental.local"
        cur.execute(
            """
            INSERT INTO users (tenant_id, legacy_id, email, username, password_hash,
                               first_name, last_name, role, must_change_password)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET legacy_id = EXCLUDED.legacy_id
            RETURNING id
            """,
            (
                default_tid, uid, email, username, TEMP_PASSWORD_HASH,
                uid, "Staff", "staff", True,
            ),
        )
        row_id = cur.fetchone()
        if row_id is None:
            cur.execute("SELECT id FROM users WHERE username = %s", (username,))
            row_id = cur.fetchone()
        db_id = row_id[0]
        user_map[uid] = db_id
        user_map[uid.lower()] = db_id
        user_map[username] = db_id
        staff_inserted += 1

    conn.commit()
    print(f"  [s03b] users seeded: {inserted} provider accounts + {staff_inserted} staff + 1 admin → map size {len(user_map)}")
    print(f"         ⚠  Temporary password 'ChangeMe123!' — enforce change on first login")
    return user_map
