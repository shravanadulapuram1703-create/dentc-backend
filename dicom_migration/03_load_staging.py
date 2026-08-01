"""
Phase A1b / R2(staging) — Load the manifest into Postgres and link patients.

Creates three migration-owned staging tables (prefixed ``mig_dicom_*`` — they
never touch the app's live tables) and populates them from the manifest +
upload state:

  * mig_dicom_manifest  — one row per source file (metadata + sha256 + gcs key)
  * mig_dicom_object    — one row per distinct sha256 (what physically lives in GCS)
  * mig_patient_link    — DICOM PatientID -> patients.legacy_id resolution

Patient linkage:
  1. exact:      manifest.patient_id  ==  patients.legacy_id
  2. fallback:   (last_name, first_name, birth_date) if those columns exist
  3. unmatched:  everything else  -> the quarantine worklist (never dropped)

Idempotent: safe to re-run (ON CONFLICT upserts). Uses raw psycopg2 with
statement_timeout disabled for the session, so the bulk COPY-style load is not
killed by the app's 30s timeout.

Run:
    python 03_load_staging.py                # load + link
    python 03_load_staging.py --dry-run      # connect + create tables only
    python 03_load_staging.py --link-only    # skip re-load, just recompute links
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import common as c

DDL = """
CREATE TABLE IF NOT EXISTS mig_dicom_manifest (
    id                       BIGSERIAL PRIMARY KEY,
    source_path              TEXT UNIQUE NOT NULL,
    source_size_bytes        BIGINT,
    content_sha256           CHAR(64),
    gcs_object_key           TEXT,
    upload_status            TEXT,
    sop_instance_uid         VARCHAR(64),
    sop_class_uid            VARCHAR(64),
    study_instance_uid       VARCHAR(64),
    series_instance_uid      VARCHAR(64),
    accession_number         VARCHAR(64),
    study_id                 VARCHAR(64),
    series_number            VARCHAR(32),
    instance_number          VARCHAR(32),
    transfer_syntax_uid      VARCHAR(64),
    patient_id               VARCHAR(64),
    patient_name_raw         TEXT,
    patient_birth_date       VARCHAR(16),
    patient_sex              VARCHAR(8),
    modality                 VARCHAR(16),
    study_date               VARCHAR(16),
    study_time               VARCHAR(24),
    content_date             VARCHAR(16),
    body_part_examined       VARCHAR(64),
    view_position            VARCHAR(32),
    image_comments           TEXT,
    anatomic_structure_codes JSONB,
    rows                     INTEGER,
    columns                  INTEGER,
    bits_allocated           INTEGER,
    photometric_interpretation VARCHAR(32),
    window_center            VARCHAR(64),
    window_width             VARCHAR(64),
    manufacturer             VARCHAR(128),
    manufacturer_model_name  VARCHAR(128),
    software_versions        VARCHAR(128),
    institution_name         VARCHAR(128),
    source_ae_title          VARCHAR(64),
    has_original_attributes  BOOLEAN DEFAULT FALSE,
    loaded_at                TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_mig_manifest_patient ON mig_dicom_manifest(patient_id);
CREATE INDEX IF NOT EXISTS ix_mig_manifest_study   ON mig_dicom_manifest(study_instance_uid);
CREATE INDEX IF NOT EXISTS ix_mig_manifest_sha     ON mig_dicom_manifest(content_sha256);

CREATE TABLE IF NOT EXISTS mig_dicom_object (
    content_sha256  CHAR(64) PRIMARY KEY,
    size_bytes      BIGINT,
    gcs_object_key  TEXT,
    source_copies   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS mig_patient_link (
    patient_id_raw  VARCHAR(64) PRIMARY KEY,
    patient_id      INTEGER,
    tenant_id       INTEGER,
    match_method    VARCHAR(32) NOT NULL,   -- legacy_id_exact | name_dob | unmatched
    confidence      REAL,
    image_count     INTEGER,
    resolved_at     TIMESTAMPTZ DEFAULT NOW()
);
"""

# columns inserted into mig_dicom_manifest, in order
COLS = [
    "source_path", "source_size_bytes", "content_sha256", "gcs_object_key", "upload_status",
    "sop_instance_uid", "sop_class_uid", "study_instance_uid", "series_instance_uid",
    "accession_number", "study_id", "series_number", "instance_number", "transfer_syntax_uid",
    "patient_id", "patient_name_raw", "patient_birth_date", "patient_sex", "modality",
    "study_date", "study_time", "content_date", "body_part_examined", "view_position",
    "image_comments", "anatomic_structure_codes", "rows", "columns", "bits_allocated",
    "photometric_interpretation", "window_center", "window_width", "manufacturer",
    "manufacturer_model_name", "software_versions", "institution_name", "source_ae_title",
    "has_original_attributes",
]


def _row_from_rec(rec: dict, state_by_path: dict[str, tuple]) -> list:
    sp = rec.get("source_path")
    sha = key = status = None
    if sp in state_by_path:
        sha, key, status = state_by_path[sp]
    codes = rec.get("anatomic_structure_codes") or []
    return [
        sp, rec.get("source_size_bytes"), sha, key, status,
        rec.get("sop_instance_uid"), rec.get("sop_class_uid"),
        rec.get("study_instance_uid"), rec.get("series_instance_uid"),
        rec.get("accession_number"), rec.get("study_id"), rec.get("series_number"),
        rec.get("instance_number"), rec.get("transfer_syntax_uid"),
        rec.get("patient_id"), rec.get("patient_name_raw"), rec.get("patient_birth_date"),
        rec.get("patient_sex"), rec.get("modality"), rec.get("study_date"),
        rec.get("study_time"), rec.get("content_date"), rec.get("body_part_examined"),
        rec.get("view_position"), rec.get("image_comments"),
        json.dumps(codes) if codes else None,
        rec.get("rows"), rec.get("columns"), rec.get("bits_allocated"),
        rec.get("photometric_interpretation"), rec.get("window_center"),
        rec.get("window_width"), rec.get("manufacturer"),
        rec.get("manufacturer_model_name"), rec.get("software_versions"),
        rec.get("institution_name"), rec.get("source_ae_title"),
        bool(rec.get("has_original_attributes_seq")),
    ]


def _load_state(store: c.StateStore) -> dict[str, tuple]:
    """{source_path: (sha256, object_key, status)} from the resume DB."""
    out: dict[str, tuple] = {}
    for row in store.iter_all():
        out[row["source_path"]] = (row["sha256"], row["object_key"], row["status"])
    return out


def _patients_columns(cur) -> set[str]:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'patients'
    """)
    return {r[0] for r in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Load manifest into Postgres staging + link patients")
    ap.add_argument("--dry-run", action="store_true", help="create tables only, load nothing")
    ap.add_argument("--link-only", action="store_true", help="skip manifest load, recompute links")
    ap.add_argument("--batch", type=int, default=5000)
    args = ap.parse_args()

    cfg = c.load_config()
    dsn = cfg.dsn()
    if "dbname=" not in dsn and "://" not in dsn:
        print("ERROR: no database configured. Set DATABASE_URL or DB_* in .env")
        return 2

    state_dir = cfg.state_path
    log = c.get_logger("load", state_dir)

    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except Exception:
        log.error("psycopg2 not installed. Run: pip install -r requirements.txt")
        return 2

    log.info("Connecting to Postgres …")
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 0")           # bulk load; no 30s cap
        cur.execute("SET idle_in_transaction_session_timeout = 0")
    conn.commit()

    log.info("Ensuring staging tables exist …")
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()

    if args.dry_run:
        log.info("--dry-run: tables ready, nothing loaded. ✔")
        conn.close()
        return 0

    # ── load manifest ────────────────────────────────────────────────────
    if not args.link_only:
        if not cfg.manifest_path.exists():
            log.error("No manifest at %s — run 01_scan.py first.", cfg.manifest_path)
            return 2
        store = c.StateStore(state_dir)
        log.info("Reading upload state …")
        state_by_path = _load_state(store)
        store.close()

        # count lines for the progress bar
        total = sum(1 for _ in open(cfg.manifest_path, "r", encoding="utf-8"))
        bar = c.make_progress(total, unit="row", desc="load")
        insert_sql = (
            f"INSERT INTO mig_dicom_manifest ({','.join(COLS)}) VALUES %s "
            f"ON CONFLICT (source_path) DO UPDATE SET "
            f"content_sha256=EXCLUDED.content_sha256, gcs_object_key=EXCLUDED.gcs_object_key, "
            f"upload_status=EXCLUDED.upload_status, loaded_at=NOW()"
        )
        batch: list[list] = []
        loaded = bad = 0
        with open(cfg.manifest_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    bar.update(1)
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("status") != "ok":
                        bar.update(1)
                        continue
                    batch.append(_row_from_rec(rec, state_by_path))
                except Exception:
                    bad += 1
                bar.update(1)
                if len(batch) >= args.batch:
                    loaded += _flush(conn, execute_values, insert_sql, batch, log)
                    batch = []
        if batch:
            loaded += _flush(conn, execute_values, insert_sql, batch, log)
        bar.close()
        log.info("Manifest loaded: %d rows (%d unparseable lines skipped).", loaded, bad)

    # ── derive distinct objects ──────────────────────────────────────────
    log.info("Rebuilding mig_dicom_object (distinct sha256) …")
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO mig_dicom_object (content_sha256, size_bytes, gcs_object_key, source_copies)
            SELECT content_sha256, MAX(source_size_bytes), MAX(gcs_object_key), COUNT(*)
            FROM mig_dicom_manifest
            WHERE content_sha256 IS NOT NULL
            GROUP BY content_sha256
            ON CONFLICT (content_sha256) DO UPDATE
              SET source_copies = EXCLUDED.source_copies,
                  gcs_object_key = EXCLUDED.gcs_object_key
        """)
    conn.commit()

    # ── patient linkage ──────────────────────────────────────────────────
    log.info("Resolving patient links …")
    with conn.cursor() as cur:
        pcols = _patients_columns(cur)
        cur.execute("DELETE FROM mig_patient_link")

        # 1) exact legacy_id match
        cur.execute("""
            INSERT INTO mig_patient_link
                (patient_id_raw, patient_id, tenant_id, match_method, confidence, image_count)
            SELECT m.patient_id, p.id, p.tenant_id, 'legacy_id_exact', 1.0, COUNT(*)
            FROM mig_dicom_manifest m
            JOIN patients p ON p.legacy_id = m.patient_id
            WHERE m.patient_id IS NOT NULL
            GROUP BY m.patient_id, p.id, p.tenant_id
            ON CONFLICT (patient_id_raw) DO NOTHING
        """)
        exact = cur.rowcount

        # 2) fallback (last_name, first_name, birth_date) — only if columns exist
        name_dob = 0
        birth_col = next((x for x in ("date_of_birth", "birth_date", "dob") if x in pcols), None)
        if {"first_name", "last_name"} <= pcols and birth_col:
            # patient_name_raw is "Last^First" in DICOM
            cur.execute(f"""
                INSERT INTO mig_patient_link
                    (patient_id_raw, patient_id, tenant_id, match_method, confidence, image_count)
                SELECT sub.patient_id_raw, sub.pid, sub.tenant_id, 'name_dob', 0.6, sub.cnt
                FROM (
                    SELECT m.patient_id AS patient_id_raw, p.id AS pid, p.tenant_id AS tenant_id,
                           COUNT(*) AS cnt,
                           ROW_NUMBER() OVER (PARTITION BY m.patient_id ORDER BY COUNT(*) DESC) AS rn
                    FROM mig_dicom_manifest m
                    JOIN patients p
                      ON lower(p.last_name)  = lower(split_part(m.patient_name_raw, '^', 1))
                     AND lower(p.first_name) = lower(split_part(m.patient_name_raw, '^', 2))
                     AND to_char(p.{birth_col}, 'YYYYMMDD') = m.patient_birth_date
                    WHERE m.patient_id IS NOT NULL
                      AND m.patient_name_raw IS NOT NULL
                      AND m.patient_birth_date IS NOT NULL
                      AND m.patient_id NOT IN (SELECT patient_id_raw FROM mig_patient_link)
                    GROUP BY m.patient_id, p.id, p.tenant_id
                ) sub
                WHERE sub.rn = 1
                ON CONFLICT (patient_id_raw) DO NOTHING
            """)
            name_dob = cur.rowcount
        else:
            log.info("Skipping name/DOB fallback (patients lacks expected columns).")

        # 3) everything still unresolved -> quarantine
        cur.execute("""
            INSERT INTO mig_patient_link
                (patient_id_raw, patient_id, tenant_id, match_method, confidence, image_count)
            SELECT m.patient_id, NULL, NULL, 'unmatched', 0.0, COUNT(*)
            FROM mig_dicom_manifest m
            WHERE m.patient_id IS NOT NULL
              AND m.patient_id NOT IN (SELECT patient_id_raw FROM mig_patient_link)
            GROUP BY m.patient_id
            ON CONFLICT (patient_id_raw) DO NOTHING
        """)
        unmatched = cur.rowcount
    conn.commit()

    # ── summary ──────────────────────────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM mig_dicom_manifest")
        n_files = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM mig_dicom_object")
        n_objs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT study_instance_uid) FROM mig_dicom_manifest")
        n_studies = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM mig_dicom_manifest WHERE has_original_attributes")
        n_corrected = cur.fetchone()[0]
        cur.execute("""SELECT study_instance_uid FROM mig_dicom_manifest
                       WHERE study_instance_uid IS NOT NULL
                       GROUP BY study_instance_uid HAVING COUNT(DISTINCT patient_id) > 1""")
        multi_patient_studies = cur.fetchall()

    log.info("──────── STAGING LOAD SUMMARY ────────")
    log.info("  manifest rows            : %d", n_files)
    log.info("  distinct objects (dedup) : %d", n_objs)
    log.info("  distinct studies         : %d", n_studies)
    log.info("  patient links exact      : %d", exact)
    log.info("  patient links name/dob   : %d", name_dob)
    log.info("  UNMATCHED (quarantine)   : %d  <-- resolve before promotion", unmatched)
    log.info("  re-identified (CORRECT)  : %d rows carry OriginalAttributes", n_corrected)
    log.info("  studies spanning >1 pt   : %d  <-- review", len(multi_patient_studies))
    log.info("──────────────────────────────────────")
    log.info("Query the quarantine with:")
    log.info("  SELECT * FROM mig_patient_link WHERE match_method='unmatched' ORDER BY image_count DESC;")
    conn.close()
    return 0


def _flush(conn, execute_values, sql, batch, log) -> int:
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, batch, page_size=1000)
        conn.commit()
        return len(batch)
    except Exception as exc:
        conn.rollback()
        log.error("batch insert failed (%d rows), continuing: %r", len(batch), exc)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
