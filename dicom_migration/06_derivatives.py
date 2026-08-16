"""
Phase D — Derivative generation (thumbnail + web JPEG) for promoted instances.

Browsers can't render JPEG-2000 DICOM, so this decodes each promoted image and
produces two browser-friendly JPEGs, uploads them to GCS, and flips the instance
to ``derivative_status='ready'`` so the imaging API serves them.

  thumbnail : 320px longest edge, JPEG q80   -> derived/thumb/<sha>.jpg
  web       : min(native, 2600)px, JPEG q85  -> derived/web/<sha>.jpg

Source bytes come from the local export (``mig_dicom_manifest.source_path``) when
present, else are downloaded from the GCS original. Idempotent: skips instances
already ``ready`` unless ``--force``.

Performance
-----------
The per-image work (download original, decode pixels, window, encode two JPEGs,
upload two JPEGs) is embarrassingly parallel: it is dominated by network I/O
(3 GCS round-trips/image) and C-extension CPU (openjpeg/GDCM decode, numpy,
libjpeg) that **releases the GIL**. So this runs a ``ThreadPoolExecutor`` of
image workers that do only GCS + CPU (never the DB), while the main thread
applies the resulting DB writes in **batches** (one commit per batch, not one
per image). At full 450k scale the same recipe fans out across a sharded Cloud
Run Job; this local version just uses threads.

Run:
    python 06_derivatives.py --procs 8          # THE FAST PATH: N = your CPU cores
    python 06_derivatives.py                    # single process (slow: 1 core)
    python 06_derivatives.py --procs 8 --force  # regenerate everything
    # Across machines (manual): run disjoint shards of one shared total, e.g.
    #   box A:  python 06_derivatives.py --shards 32 --shard 0   (…through 15)
    #   box B:  python 06_derivatives.py --shards 32 --shard 16  (…through 31)
"""

from __future__ import annotations

import argparse
import io
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait

import common as c

THUMB_EDGE = 320
WEB_EDGE = 2600
DERIVED_PREFIX = "derived"
DEFAULT_DB_BATCH = 200

_STOP = threading.Event()


def _to_image(ds):  # noqa: ANN001, ANN202
    """DICOM dataset -> 8-bit PIL Image, with basic windowing for 16-bit."""
    import numpy as np
    from PIL import Image

    arr = ds.pixel_array
    photometric = str(getattr(ds, "PhotometricInterpretation", "") or "")
    applied_wc = applied_ww = None

    if arr.ndim == 3:  # RGB / colour photo
        return Image.fromarray(arr.astype("uint8"), "RGB"), None, None

    arr = arr.astype("float32")
    if photometric == "MONOCHROME1":  # min = white -> invert to a normal look
        arr = arr.max() - arr

    bits_stored = int(getattr(ds, "BitsStored", 8) or 8)
    if bits_stored > 8:
        wc = getattr(ds, "WindowCenter", None)
        ww = getattr(ds, "WindowWidth", None)
        if wc is not None and ww is not None:
            wc = float(wc[0] if isinstance(wc, (list, tuple)) or hasattr(wc, "__iter__")
                       and not isinstance(wc, str) else wc)
            ww = float(ww[0] if isinstance(ww, (list, tuple)) or hasattr(ww, "__iter__")
                       and not isinstance(ww, str) else ww)
        else:  # robust default: 1st–99th percentile stretch (not naive min/max)
            lo_p, hi_p = np.percentile(arr, [1, 99])
            wc, ww = (lo_p + hi_p) / 2.0, max(hi_p - lo_p, 1.0)
        applied_wc, applied_ww = wc, ww
        lo, hi = wc - ww / 2.0, wc + ww / 2.0
        arr = np.clip((arr - lo) / max(hi - lo, 1.0), 0, 1) * 255.0
    # else already 8-bit mono in 0..255

    return Image.fromarray(arr.astype("uint8"), "L"), applied_wc, applied_ww


def _encode(img, edge: int, quality: int) -> bytes:  # noqa: ANN001
    from PIL import Image

    w, h = img.size
    scale = min(1.0, edge / float(max(w, h)))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, progressive=(edge == WEB_EDGE), optimize=True)
    return buf.getvalue()


def _derive_one(r, *, bucket, orig_bucket, bucket_name, log):  # noqa: ANN001
    """CPU + GCS only — never touches the DB. Returns a result dict; never raises.

    ok:    {status:'ok', row, sha, thumb_key, thumb_len, web_key, web_len, awc, aww}
    error: {status:'error', row, error}
    """
    import pydicom

    sop = r["sop_instance_uid"]
    try:
        # source bytes: local export first, else download the GCS original
        if r["source_path"] and os.path.isfile(r["source_path"]):
            ds = pydicom.dcmread(r["source_path"])
        else:
            data = orig_bucket.blob(r["original_key"]).download_as_bytes()
            ds = pydicom.dcmread(io.BytesIO(data))

        # Some Secondary-Capture images omit tags pixel_array requires; default them.
        if "PixelRepresentation" not in ds:
            ds.PixelRepresentation = 0
        if "PlanarConfiguration" not in ds and int(getattr(ds, "SamplesPerPixel", 1) or 1) > 1:
            ds.PlanarConfiguration = 0

        img, awc, aww = _to_image(ds)
        sha = r["sha256"]
        thumb_key = f"{DERIVED_PREFIX}/thumb/{sha}.jpg"
        web_key = f"{DERIVED_PREFIX}/web/{sha}.jpg"
        thumb_bytes = _encode(img, THUMB_EDGE, 80)
        web_bytes = _encode(img, WEB_EDGE, 85)

        for key, payload in ((thumb_key, thumb_bytes), (web_key, web_bytes)):
            blob = bucket.blob(key)
            blob.content_type = "image/jpeg"
            blob.cache_control = "private, max-age=31536000, immutable"
            blob.upload_from_string(payload, content_type="image/jpeg")

        return {
            "status": "ok", "row": r, "sha": sha,
            "thumb_key": thumb_key, "thumb_len": len(thumb_bytes),
            "web_key": web_key, "web_len": len(web_bytes),
            "awc": str(awc) if awc is not None else None,
            "aww": str(aww) if aww is not None else None,
        }
    except Exception as exc:  # noqa: BLE001 - never abort the batch
        log.warning("derivative failed for %s: %r", sop, exc)
        return {"status": "error", "row": r, "error": repr(exc)[:500]}


OBJECT_SQL = """
    INSERT INTO stored_objects
      (tenant_id, bucket, object_key, kind, content_type, size_bytes, sha256, ref_count)
    VALUES %s
    ON CONFLICT (bucket, object_key) DO UPDATE SET size_bytes = EXCLUDED.size_bytes
    RETURNING object_key, id
"""

READY_SQL = """
    UPDATE dicom_instances di
    SET thumb_object_id       = v.thumb_id::bigint,
        web_object_id         = v.web_id::bigint,
        derivative_status     = 'ready',
        applied_window_center = v.awc::text,
        applied_window_width  = v.aww::text,
        derivative_error      = NULL
    FROM (VALUES %s) AS v(id, thumb_id, web_id, awc, aww)
    WHERE di.id = v.id::bigint
"""

FAILED_SQL = """
    UPDATE dicom_instances di
    SET derivative_status = 'failed', derivative_error = v.err::text
    FROM (VALUES %s) AS v(id, err)
    WHERE di.id = v.id::bigint
"""


def _connect(cfg):
    """Open a DB connection tuned for a long, bursty job.

    TCP keepalives stop the remote Postgres / network from silently dropping the
    connection during the minutes-long idle gaps between batch commits (that drop
    is what was crashing the shards mid-run), and statement_timeout is disabled.
    """
    import psycopg2

    conn = psycopg2.connect(
        cfg.dsn(),
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
        options="-c statement_timeout=0",
    )
    conn.autocommit = False
    return conn


def _flush(conn, results, bucket_name, cfg, log):
    """Apply a batch of worker results in one transaction.

    Returns ``(ok, failed, conn)`` — ``conn`` may be a freshly reconnected handle.
    A dropped connection is recovered (reconnect + retry once) instead of killing
    the shard; a genuine data error is logged and the batch skipped (the rows stay
    unmarked, so a re-run — which is idempotent — picks them up).
    """
    from psycopg2.extras import execute_values
    import psycopg2

    oks = [x for x in results if x["status"] == "ok"]
    errs = [x for x in results if x["status"] == "error"]

    def _apply(cur):
        if oks:
            # 1) upsert both derivative objects; dedupe by object_key so a shared
            #    sha (deduped original) can't hit the same row twice in a batch.
            obj_args = {}
            for x in oks:
                r = x["row"]
                obj_args[x["thumb_key"]] = (
                    r["tenant_id"], bucket_name, x["thumb_key"], "thumb",
                    "image/jpeg", x["thumb_len"], x["sha"], 1)
                obj_args[x["web_key"]] = (
                    r["tenant_id"], bucket_name, x["web_key"], "web",
                    "image/jpeg", x["web_len"], x["sha"], 1)
            key_to_id = {}
            for key, _id in execute_values(cur, OBJECT_SQL, list(obj_args.values()),
                                           page_size=len(obj_args), fetch=True):
                key_to_id[key] = _id

            # 2) flip instances to ready, wiring the derivative object ids
            ready_args = [
                (x["row"]["id"], key_to_id[x["thumb_key"]], key_to_id[x["web_key"]],
                 x["awc"], x["aww"])
                for x in oks
            ]
            execute_values(cur, READY_SQL, ready_args,
                           template="(%s,%s,%s,%s,%s)", page_size=len(ready_args))

        if errs:
            execute_values(cur, FAILED_SQL,
                           [(x["row"]["id"], x["error"]) for x in errs],
                           template="(%s,%s)", page_size=len(errs))

    for attempt in (1, 2):
        try:
            with conn.cursor() as cur:
                _apply(cur)
            conn.commit()
            return len(oks), len(errs), conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            # Connection dropped (idle reap / network blip). Reconnect and retry once.
            log.warning("DB connection lost (%r) — reconnecting (attempt %d/2) ...", exc, attempt)
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                conn = _connect(cfg)
            except Exception as exc2:  # noqa: BLE001
                log.error("Reconnect failed: %r — batch skipped (safe to re-run).", exc2)
                return 0, 0, conn
        except Exception as exc:  # noqa: BLE001 - a data error must never kill the shard
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001 - rollback on a dead conn would itself throw
                pass
            log.error("DB flush failed for a batch of %d (rolled back, skipped): %r",
                      len(results), exc)
            return 0, 0, conn

    log.error("Batch of %d skipped after reconnect; rows stay pending (re-run to finish).",
              len(results))
    return 0, 0, conn


def _run_supervisor(args, cfg, log) -> int:
    """Fan out into ``args.procs`` sharded child processes — one per CPU core.

    JPEG-2000 decode is CPU-bound and GIL-bound, so threads inside one process
    can't use more than one core. Separate OS processes can. Each child runs
    ``--shards N --shard k`` (disjoint rows, no coordination needed) and logs to
    ``state/derivatives.shard{k}.log``. Progress is polled from the DB.
    """
    import subprocess
    import sys
    import time

    n = args.procs
    state = cfg.state_path
    # Each shard also spins up upload threads. With N shards that multiplies:
    # N shards x WORKERS threads all hit the uplink at once and stall it. Keep
    # per-shard threads small (just enough to overlap the 2 GCS uploads/image);
    # decode parallelism comes from the shards, not the threads.
    child_workers = args.workers or 3
    log.info("Fan-out: launching %d sharded workers x %d upload-threads each ...", n, child_workers)

    fhs, procs = [], []
    for k in range(n):
        fh = open(state / f"derivatives.shard{k}.log", "a", encoding="utf-8")
        fhs.append(fh)
        cmd = [sys.executable, os.path.abspath(__file__),
               "--shards", str(n), "--shard", str(k),
               "--batch", str(args.batch), "--workers", str(child_workers)]
        if args.force:
            cmd.append("--force")
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=fh)
        procs.append(p)
        log.info("  shard %d/%d -> pid %d  (state/derivatives.shard%d.log)", k, n, p.pid, k)

    # Aggregate progress by polling the DB while the children run.
    poll = None
    try:
        poll = _connect(cfg)
        poll.autocommit = True
    except Exception:  # noqa: BLE001 - progress polling is best-effort
        poll = None

    last_ready, last_t = None, time.monotonic()
    while any(p.poll() is None for p in procs):
        time.sleep(15)
        if not poll:
            continue
        try:
            with poll.cursor() as cur:
                cur.execute("""
                    SELECT count(*) FILTER (WHERE derivative_status = 'ready'), count(*)
                    FROM dicom_instances WHERE is_deleted = false
                """)
                ready, total = cur.fetchone()
            now = time.monotonic()
            rate = ((ready - last_ready) / (now - last_t)) if last_ready is not None and now > last_t else 0.0
            eta = f"{(total - ready) / rate / 3600:.1f}h" if rate > 0 else "—"
            log.info("  progress: %d/%d ready  (%.1f img/s, ETA %s)", ready, total, rate, eta)
            last_ready, last_t = ready, now
        except Exception:  # noqa: BLE001 - reconnect so progress keeps updating
            try:
                poll = _connect(cfg)
                poll.autocommit = True
            except Exception:  # noqa: BLE001
                poll = None

    rc = 0
    for k, p in enumerate(procs):
        r = p.wait()
        rc = r or rc
        log.info("  shard %d exited rc=%d", k, r)
    for fh in fhs:
        fh.close()
    if poll:
        poll.close()
    log.info("Fan-out complete (rc=%d). Per-shard detail in state/derivatives.shard*.log", rc)
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate thumbnail/web JPEG derivatives")
    ap.add_argument("--force", action="store_true", help="regenerate even if already ready")
    ap.add_argument("--workers", type=int, default=0, help="threads for GCS-upload overlap (NOT decode)")
    ap.add_argument("--batch", type=int, default=DEFAULT_DB_BATCH, help="results per DB commit")
    ap.add_argument("--procs", type=int, default=1,
                    help="THE FAST PATH: fan out into N sharded processes (set to your CPU core count)")
    ap.add_argument("--shards", type=int, default=1,
                    help="(advanced/manual) total shards across all processes/machines")
    ap.add_argument("--shard", type=int, default=0,
                    help="(advanced/manual) which shard THIS process handles, 0..shards-1")
    args = ap.parse_args()
    if args.shards < 1 or not (0 <= args.shard < args.shards):
        print(f"ERROR: need 0 <= --shard < --shards (got shard={args.shard}, shards={args.shards})")
        return 2

    cfg = c.load_config()

    # Supervisor mode: spin up N sharded children and aggregate. This is what
    # actually uses every core; a single process (threads) can't beat the GIL.
    if args.procs > 1 and args.shards == 1:
        return _run_supervisor(args, cfg, c.get_logger("derivatives", cfg.state_path))

    log_name = "derivatives" if args.shards == 1 else f"derivatives.shard{args.shard}"
    log = c.get_logger(log_name, cfg.state_path)
    workers = args.workers or cfg.workers
    db_batch = max(1, args.batch)
    bucket_name = cfg.gcs_bucket_derived or cfg.gcs_bucket_originals
    if not bucket_name:
        log.error("Set GCS_BUCKET_DERIVED or GCS_BUCKET_ORIGINALS in .env")
        return 2

    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        import pydicom  # noqa: F401  (ensures the DICOM stack is importable)
        from google.cloud import storage
    except Exception as exc:
        log.error("Missing dependency: %r. pip install -r requirements.txt", exc)
        return 2

    conn = _connect(cfg)
    gcs = storage.Client()
    bucket = gcs.bucket(bucket_name)
    orig_bucket = gcs.bucket(cfg.gcs_bucket_originals) if cfg.gcs_bucket_originals else None

    where = "" if args.force else "AND di.derivative_status <> 'ready'"
    # Shard by id so N independently-launched processes split the work with no
    # overlap (each row's id % shards picks exactly one process). Ints only —
    # safe to inline. Lets you use every CPU core (threads can't: JPEG-2000
    # decode holds the GIL), and even split across machines.
    shard = f"AND (di.id % {args.shards}) = {args.shard}" if args.shards > 1 else ""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"""
            SELECT di.id, di.sop_instance_uid, di.tenant_id,
                   so.object_key AS original_key, so.sha256,
                   mm.source_path
            FROM dicom_instances di
            JOIN stored_objects so ON so.id = di.original_object_id
            LEFT JOIN mig_dicom_manifest mm ON mm.sop_instance_uid = di.sop_instance_uid
            WHERE di.is_deleted = false {where} {shard}
            ORDER BY di.id
        """)
        rows = cur.fetchall()
    log.info("Instances needing derivatives: %d  (shard=%d/%d, workers=%d, db_batch=%d)",
             len(rows), args.shard, args.shards, workers, db_batch)
    if not rows:
        log.info("Nothing to do. ✔")
        conn.close()
        return 0

    def _sig(_signum, _frame):
        log.warning("Stopping after in-flight images finish ... (re-run to resume)")
        _STOP.set()
    signal.signal(signal.SIGINT, _sig)

    bar = c.make_progress(len(rows), unit="img", desc="derive")
    ok = failed = 0
    pending: list = []   # completed worker results awaiting a DB flush

    it = iter(rows)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        inflight: set = set()

        def submit_next() -> bool:
            try:
                r = next(it)
            except StopIteration:
                return False
            inflight.add(ex.submit(_derive_one, r, bucket=bucket, orig_bucket=orig_bucket,
                                   bucket_name=bucket_name, log=log))
            return True

        for _ in range(workers * 3):     # bounded look-ahead queue
            if not submit_next():
                break

        while inflight:
            done_set, inflight = wait(inflight, return_when=FIRST_COMPLETED)
            for fut in done_set:
                pending.append(fut.result())   # worker never raises
                bar.update(1)
                if not _STOP.is_set():
                    submit_next()
            if len(pending) >= db_batch:
                o, f, conn = _flush(conn, pending, bucket_name, cfg, log)
                ok += o
                failed += f
                pending = []

    if pending:                                # final partial batch
        o, f, conn = _flush(conn, pending, bucket_name, cfg, log)
        ok += o
        failed += f
    bar.close()

    log.info("──────── DERIVATIVES SUMMARY ────────")
    log.info("  ready  : %d", ok)
    log.info("  failed : %d", failed)
    if _STOP.is_set():
        log.warning("  interrupted — re-run 06_derivatives.py to finish the rest.")
    log.info("─────────────────────────────────────")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
