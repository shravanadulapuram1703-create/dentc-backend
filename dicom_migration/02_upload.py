"""
Phase A2 — Hash + upload the DICOM bytes to GCS.

For every file in the manifest this:
  1. streams the file through SHA-256 (also warms the OS cache),
  2. derives a content-addressed object key
     ``dicom/<aa>/<bb>/<sha256>.dcm``,
  3. uploads it with ``if_generation_match=0`` (create-only) and server-side
     CRC32C verification.

Robustness (this is the long, unattended run):
  * Per-file try/except — one bad file NEVER aborts the run.
  * Exponential-backoff retry on transient GCS/network errors.
  * A 412 "already exists" is treated as SUCCESS (dedupe + cross-run resume).
  * Progress in the terminal: files done / total, %, throughput, ETA.
  * Every permanent failure is written to state/skipped_upload.csv (+ .jsonl).
  * Resumable: state.db records each file; re-running only does what's left.
  * Ctrl-C stops after in-flight uploads finish; just re-run to continue.

Run:
    python 02_upload.py
    python 02_upload.py --workers 16
    python 02_upload.py --retry-errors     # re-attempt previously failed files
"""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from pathlib import Path

import common as c

_STOP = threading.Event()


def _seed_state_from_manifest(cfg: c.Config, store: c.StateStore, log) -> None:
    """Ensure every 'ok' manifest row exists in the resume store."""
    mp = cfg.manifest_path
    if not mp.exists():
        log.error("No manifest at %s — run 01_scan.py first.", mp)
        raise SystemExit(2)
    added = 0
    with open(mp, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("status") != "ok":
                    continue
                store.add_pending(rec["source_path"],
                                  int(rec.get("source_size_bytes") or 0),
                                  float(rec.get("source_mtime_utc") or 0))
                added += 1
            except Exception:
                continue
    log.info("Seeded/confirmed %d files in the resume store.", added)


def _upload_one(path_str: str, size: int, *, cfg: c.Config, bucket, log,
                skips: c.SkipLog, store: c.StateStore, limiter: c.TokenBucket) -> str:
    """Returns one of: uploaded | exists | error | skipped. Never raises."""
    from google.api_core import exceptions as gexc

    try:
        path = Path(path_str)
        if not path.is_file():
            skips.add(path_str, "missing_at_upload", "file vanished before upload")
            store.mark(path_str, "skipped", error="missing at upload")
            return "skipped"

        # 1) hash (full read) — this is what makes the key content-addressed
        try:
            sha = c.sha256_file(path)
        except Exception as exc:
            skips.add(path_str, "hash_error", repr(exc))
            store.mark(path_str, "error", error=f"hash: {exc!r}", bump_attempt=True)
            return "error"

        key = c.object_key_for(sha, cfg.gcs_prefix)

        # 2) upload, create-only. 412 => already there => success.
        def _do_upload():
            blob = bucket.blob(key)
            blob.content_type = "application/dicom"
            with open(path, "rb") as fh:
                reader = c.ThrottledReader(fh, limiter) if limiter.rate > 0 else fh
                blob.upload_from_file(
                    reader,
                    size=size if size and size > 0 else None,
                    if_generation_match=0,      # create-only
                    checksum="crc32c",          # server verifies wire integrity
                    timeout=300,
                )

        try:
            c.with_retry(
                _do_upload,
                attempts=cfg.retry_max,
                base_delay=cfg.retry_base_delay,
                give_up_on=(gexc.PreconditionFailed,),   # 412 = exists
                retry_on=(gexc.GoogleAPIError, OSError, ConnectionError,
                          TimeoutError, Exception),
                on_retry=lambda i, e, d: log.debug("retry %d %s in %.1fs: %r", i, key, d, e),
            )
            store.mark(path_str, "uploaded", sha256=sha, object_key=key,
                       error="", bump_attempt=True)
            return "uploaded"
        except gexc.PreconditionFailed:
            store.mark(path_str, "exists", sha256=sha, object_key=key, error="")
            return "exists"
        except c.RetryError as exc:
            skips.add(path_str, "upload_error", repr(exc.last))
            store.mark(path_str, "error", sha256=sha, object_key=key,
                       error=repr(exc.last), bump_attempt=True)
            return "error"
    except Exception as exc:  # absolute defensive catch-all — never crash a worker
        try:
            skips.add(path_str, "worker_error", repr(exc))
            store.mark(path_str, "error", error=repr(exc), bump_attempt=True)
        except Exception:
            pass
        return "error"


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload DICOM files to GCS (content-addressed)")
    ap.add_argument("--workers", type=int, default=0, help="override WORKERS")
    ap.add_argument("--retry-errors", action="store_true",
                    help="also re-attempt files previously marked 'error'")
    args = ap.parse_args()

    cfg = c.load_config()
    if not cfg.gcs_bucket_originals:
        print("ERROR: GCS_BUCKET_ORIGINALS is not set in .env")
        return 2
    workers = args.workers or cfg.workers

    state = cfg.state_path
    log = c.get_logger("upload", state)
    skips = c.SkipLog(state, "upload")
    store = c.StateStore(state)

    _seed_state_from_manifest(cfg, store, log)

    try:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(cfg.gcs_bucket_originals)
    except Exception as exc:
        log.error("Could not create GCS client — check GOOGLE_APPLICATION_CREDENTIALS "
                  "and GCS_BUCKET_ORIGINALS. Detail: %r", exc)
        return 2

    limiter = c.TokenBucket(cfg.max_bandwidth_mbps * 1_000_000 / 8.0)

    todo = list(store.iter_todo())  # pending + error
    if not args.retry_errors:
        err = store.counts().get("error", 0)
        if err:
            log.info("%d file(s) are in 'error' state and WILL be retried this pass. "
                     "(They are retried every run until they succeed.)", err)

    total_all = store.total()
    counts0 = store.counts()
    done0 = counts0.get("uploaded", 0) + counts0.get("exists", 0)
    log.info("Worklist: %d file(s) to process; %d/%d already done.",
             len(todo), done0, total_all)

    if not todo:
        log.info("Nothing to do — all files already uploaded. ✔")
        _summary(store, skips, log)
        return 0

    def _sig(_signum, _frame):
        log.warning("Stopping after in-flight uploads finish … (re-run to resume)")
        _STOP.set()
    signal.signal(signal.SIGINT, _sig)

    bar = c.make_progress(total_all, unit="file", desc="upload")
    bar.update(done0)  # reflect prior progress

    tallies = {"uploaded": 0, "exists": 0, "error": 0, "skipped": 0}
    start = time.monotonic()
    bytes_start = store.bytes_done()

    it = iter(todo)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        inflight: set = set()

        def submit_next() -> bool:
            try:
                sp, size = next(it)
            except StopIteration:
                return False
            inflight.add(ex.submit(_upload_one, sp, size, cfg=cfg, bucket=bucket,
                                   log=log, skips=skips, store=store, limiter=limiter))
            return True

        for _ in range(workers * 3):     # bounded look-ahead queue
            if not submit_next():
                break

        while inflight:
            done_set, inflight = wait(inflight, return_when=FIRST_COMPLETED)
            for fut in done_set:
                result = fut.result()    # worker never raises
                tallies[result] = tallies.get(result, 0) + 1
                bar.update(1)
                if not _STOP.is_set():
                    submit_next()
            el = time.monotonic() - start
            mb = (store.bytes_done() - bytes_start) / 1_000_000
            rate = mb / el if el else 0
            bar.set_postfix_str(
                f"up={tallies['uploaded']} dup={tallies['exists']} "
                f"err={tallies['error']} skip={tallies['skipped']} {rate:5.1f}MB/s"
            )

    bar.close()
    _summary(store, skips, log)
    skips.close()
    store.close()
    if _STOP.is_set():
        rem = store.counts()
        log.warning("Run interrupted — %d file(s) still to do. Re-run 02_upload.py to resume.",
                    rem.get("pending", 0) + rem.get("error", 0))
    return 0


def _summary(store: c.StateStore, skips: c.SkipLog, log) -> None:
    counts = store.counts()
    total = store.total()
    done = counts.get("uploaded", 0) + counts.get("exists", 0)
    log.info("──────── UPLOAD SUMMARY ────────")
    log.info("  total files        : %d", total)
    log.info("  uploaded (new)     : %d", counts.get("uploaded", 0))
    log.info("  already in GCS     : %d", counts.get("exists", 0))
    log.info("  pending            : %d", counts.get("pending", 0))
    log.info("  errors (retryable) : %d", counts.get("error", 0))
    log.info("  skipped (permanent): %d", counts.get("skipped", 0))
    log.info("  bytes in GCS       : %s", c.human_bytes(store.bytes_done()))
    log.info("  done               : %d/%d (%.1f%%)", done, total,
             (100.0 * done / total) if total else 0)
    if skips.count:
        log.info("  ⚠ %d item(s) logged to %s", skips.count, skips.csv_path)
    log.info("────────────────────────────────")


if __name__ == "__main__":
    raise SystemExit(main())
