"""
Phase R2 (promotion) — staging → the app's live DICOM tables.

Turns the migration-owned ``mig_dicom_*`` staging rows into the application
tables the backend serves from:

  stored_objects   (one row per uploaded original)
  dicom_studies    (per matched patient)
  dicom_series
  dicom_instances  (derivative_status='pending' until 06_derivatives runs)

Only **matched** patients are promoted (``mig_patient_link.match_method`` !=
``unmatched``); unmatched studies stay in quarantine and are skipped. Idempotent:
re-running upserts on the DICOM UIDs, so it never duplicates.

Performance
-----------
This is a **set-based, batched** rewrite. Instead of firing ~2 SQL round-trips
per instance (which is fatal over a remote DB — hundreds of thousands of
serial round-trips), it:

  1. streams the matched staging rows once (server-side cursor), collapsing them
     in memory into the *distinct* studies / series / originals / instances,
  2. bulk-upserts each set with ``execute_values`` in pages, using
     ``RETURNING`` to build the ``uid -> id`` maps that link children to parents.

Same SQL semantics, same ``ON CONFLICT`` idempotency, same output — just a few
hundred round-trips instead of ~10⁶.

Run:
    python 05_promote.py
    python 05_promote.py --dry-run
    python 05_promote.py --batch 5000
"""

from __future__ import annotations

import argparse

import common as c

# How many value-tuples per INSERT round-trip. 2000 is a good default; bigger
# pages = fewer round-trips but more memory/parse time per statement.
DEFAULT_BATCH = 2000


STUDY_SQL = """
    INSERT INTO dicom_studies
      (tenant_id, patient_id, study_instance_uid, accession_number, study_id,
       study_date, study_time, description, modalities, source_patient_id_raw,
       identity_review_required, is_deleted)
    VALUES %s
    ON CONFLICT (study_instance_uid) DO UPDATE SET patient_id = EXCLUDED.patient_id
    RETURNING study_instance_uid, id
"""

SERIES_SQL = """
    INSERT INTO dicom_series
      (tenant_id, study_id, series_instance_uid, modality, series_number,
       body_part, description, is_deleted)
    VALUES %s
    ON CONFLICT (series_instance_uid) DO UPDATE SET modality = EXCLUDED.modality
    RETURNING series_instance_uid, id
"""

OBJECT_SQL = """
    INSERT INTO stored_objects
      (tenant_id, bucket, object_key, kind, content_type, size_bytes, sha256, ref_count)
    VALUES %s
    ON CONFLICT (bucket, object_key) DO UPDATE SET sha256 = EXCLUDED.sha256
    RETURNING object_key, id
"""

INSTANCE_SQL = """
    INSERT INTO dicom_instances
      (tenant_id, series_id, sop_instance_uid, sop_class_uid, instance_number,
       rows, columns, bits_allocated, photometric_interpretation,
       window_center, window_width, anatomic_codes, original_object_id,
       derivative_status, has_original_attributes, is_deleted)
    VALUES %s
    ON CONFLICT (sop_instance_uid) DO UPDATE SET original_object_id = EXCLUDED.original_object_id
"""


def _date(s):  # 'YYYYMMDD' -> 'YYYY-MM-DD' or None
    if not s or not str(s).isdigit() or len(str(s)) != 8:
        return None
    s = str(s)
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _bulk_upsert_map(cur, sql, arglist, batch, Json=None):
    """Run an upsert with RETURNING (key, id) and return {key: id}.

    ``execute_values(..., fetch=True)`` pages the statement internally and
    concatenates the RETURNING rows across all pages.
    """
    from psycopg2.extras import execute_values

    out = {}
    if not arglist:
        return out
    rows = execute_values(cur, sql, arglist, page_size=batch, fetch=True)
    for key, _id in rows:
        out[key] = _id
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Promote staging DICOM rows into the app tables")
    ap.add_argument("--dry-run", action="store_true", help="report what would promote, write nothing")
    ap.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="rows per INSERT round-trip")
    args = ap.parse_args()
    batch = max(1, args.batch)

    cfg = c.load_config()
    log = c.get_logger("promote", cfg.state_path)
    bucket = cfg.gcs_bucket_originals
    if not bucket:
        log.error("GCS_BUCKET_ORIGINALS not set — needed for stored_objects.bucket")
        return 2

    try:
        import psycopg2
        from psycopg2.extras import Json, RealDictCursor, execute_values  # noqa: F401
    except Exception:
        log.error("psycopg2 not installed. pip install -r requirements.txt")
        return 2

    conn = psycopg2.connect(cfg.dsn())
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute("SET statement_timeout = 0")
        # Idempotent, re-runnable migration — trade the last-commit crash guarantee
        # for materially faster WAL flushing on this bulk load.
        cur.execute("SET synchronous_commit = off")
    conn.commit()

    # matched patient links: raw legacy id -> (patient_id, tenant_id)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT patient_id_raw, patient_id, tenant_id
            FROM mig_patient_link
            WHERE match_method <> 'unmatched' AND patient_id IS NOT NULL
        """)
        links = {r["patient_id_raw"]: (r["patient_id"], r["tenant_id"]) for r in cur.fetchall()}
    log.info("Matched patients to promote: %d", len(links))
    if not links:
        log.warning("Nothing matched — run 03_load_staging first, or resolve the quarantine.")
        conn.close()
        return 0

    # ── Pass 1: stream the matched instances once, collapse into distinct sets ──
    # Server-side (named) cursor streams rather than materialising 445k dict rows
    # at once; we keep only the compact per-entity structures below.
    studies: dict[str, dict] = {}   # study_uid  -> attrs (+ accumulated modality set)
    series: dict[str, tuple] = {}   # series_uid -> row for the series insert
    objects: dict[str, tuple] = {}  # object_key -> row for the stored_object insert
    instances: dict[str, tuple] = {}  # sop_uid   -> row for the instance insert

    scanned = 0
    with conn.cursor(name="promote_stream", cursor_factory=RealDictCursor) as scur:
        scur.itersize = 5000
        scur.execute("""
            SELECT *
            FROM mig_dicom_manifest
            WHERE upload_status IN ('uploaded', 'exists')
              AND gcs_object_key IS NOT NULL
              AND content_sha256 IS NOT NULL
              AND patient_id = ANY(%s)
            ORDER BY study_instance_uid, series_instance_uid, instance_number
        """, (list(links.keys()),))

        for r in scur:
            scanned += 1
            if scanned % 50000 == 0:
                log.info("  scanned %d instances ...", scanned)

            raw_pid = r["patient_id"]
            patient_id, tenant_id = links[raw_pid]
            su = r["study_instance_uid"]
            seu = r["series_instance_uid"] or su   # some SC images omit a series UID
            okey = r["gcs_object_key"]
            sop = r["sop_instance_uid"]
            mod = r["modality"]

            # distinct study (first row wins for attrs; modality set accumulates)
            st = studies.get(su)
            if st is None:
                st = {
                    "tenant_id": tenant_id,
                    "patient_id": patient_id,
                    "accession_number": r["accession_number"],
                    "study_id": r["study_id"],
                    "study_date": _date(r["study_date"]),
                    "study_time": r["study_time"],
                    "description": r["image_comments"],
                    "source_patient_id_raw": raw_pid,
                    "mods": set(),
                }
                studies[su] = st
            if mod:
                st["mods"].add(mod)

            # distinct series
            if seu not in series:
                series[seu] = (
                    tenant_id, su, seu, mod, r["series_number"],
                    r["body_part_examined"], r["image_comments"], False,
                )

            # distinct original object (content-addressed key)
            if okey not in objects:
                objects[okey] = (
                    tenant_id, bucket, okey, "original", "application/dicom",
                    r["source_size_bytes"], r["content_sha256"], 1,
                )

            # distinct instance — series linked by `seu`, object by `okey`,
            # both resolved to ids after the parent upserts below.
            if sop not in instances:
                anatomic = r["anatomic_structure_codes"]
                instances[sop] = (
                    tenant_id, seu, sop, r["sop_class_uid"], r["instance_number"],
                    r["rows"], r["columns"], r["bits_allocated"],
                    r["photometric_interpretation"], r["window_center"], r["window_width"],
                    Json(anatomic) if anatomic is not None else None,
                    okey, bool(r["has_original_attributes"]),
                )

    log.info("Scanned %d instances → distinct: %d studies, %d series, %d originals, %d instances.",
             scanned, len(studies), len(series), len(objects), len(instances))

    if args.dry_run:
        log.info("--dry-run: would promote %d instances across %d studies for %d patients.",
                 len(instances), len(studies), len(links))
        conn.close()
        return 0

    if not instances:
        log.info("Nothing to promote. ✔")
        conn.close()
        return 0

    # ── Pass 2: bulk upsert parents → children, building uid->id maps ──
    try:
        with conn.cursor() as cur:
            # studies
            study_args = [
                (st["tenant_id"], st["patient_id"], su, st["accession_number"], st["study_id"],
                 st["study_date"], st["study_time"], st["description"],
                 Json(sorted(st["mods"])), st["source_patient_id_raw"], False, False)
                for su, st in studies.items()
            ]
            study_ids = _bulk_upsert_map(cur, STUDY_SQL, study_args, batch)
            log.info("  upserted %d studies", len(study_ids))

            # series (resolve study_id from the map)
            series_args = [
                (tenant_id, study_ids[su], seu, mod, series_number, body_part, desc, is_del)
                for (tenant_id, su, seu, mod, series_number, body_part, desc, is_del) in series.values()
            ]
            series_ids = _bulk_upsert_map(cur, SERIES_SQL, series_args, batch)
            log.info("  upserted %d series", len(series_ids))

            # stored_objects (originals)
            object_ids = _bulk_upsert_map(cur, OBJECT_SQL, list(objects.values()), batch)
            log.info("  upserted %d originals", len(object_ids))

            # instances (resolve series_id + original_object_id from the maps)
            inst_args = []
            skipped_link = 0
            for v in instances.values():
                (tenant_id, seu, sop, sop_class, inst_no, rows_, cols_, bits_,
                 photo_, wc_, ww_, anatomic_, okey, has_orig) = v
                series_id = series_ids.get(seu)
                original_object_id = object_ids.get(okey)
                if series_id is None or original_object_id is None:
                    skipped_link += 1
                    continue
                inst_args.append((
                    tenant_id, series_id, sop, sop_class, inst_no,
                    rows_, cols_, bits_, photo_, wc_, ww_, anatomic_,
                    original_object_id, "pending", has_orig, False,
                ))

            bar = c.make_progress(len(inst_args), unit="img", desc="promote")
            for i in range(0, len(inst_args), batch):
                chunk = inst_args[i:i + batch]
                execute_values(cur, INSTANCE_SQL, chunk, page_size=batch)
                bar.update(len(chunk))
            bar.close()

        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.error("Promotion failed, rolled back: %r", exc)
        raise

    log.info("──────── PROMOTION SUMMARY ────────")
    log.info("  studies    : %d", len(study_ids))
    log.info("  series     : %d", len(series_ids))
    log.info("  instances  : %d", len(inst_args))
    log.info("  objects    : %d (distinct originals)", len(object_ids))
    if skipped_link:
        log.warning("  skipped    : %d instance(s) missing a resolved series/object", skipped_link)
    log.info("  derivatives: pending — run 06_derivatives.py to generate thumbnails/web images")
    log.info("───────────────────────────────────")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
