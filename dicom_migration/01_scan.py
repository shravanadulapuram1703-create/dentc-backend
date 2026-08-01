"""
Phase A1 — Header-only inventory scan.

Walks SOURCE_DIR, reads only the DICOM header of each file (~a few KB, NOT the
whole 1 MB+ file), and writes one NDJSON line per readable file to
``state/manifest.ndjson``. Unreadable / non-DICOM files are logged to
``state/skipped_scan.csv`` (and .jsonl) — never crashes the run.

Resumable: re-running skips files already in the manifest.

Run:
    python 01_scan.py
    python 01_scan.py --limit 1000     # quick sample of the first N files
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import common as c


def count_files(root: Path, exts: tuple[str, ...], scan_all: bool) -> int:
    n = 0
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if scan_all or f.lower().endswith(exts):
                n += 1
    return n


def iter_candidate_files(root: Path, exts: tuple[str, ...], scan_all: bool):
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if scan_all or f.lower().endswith(exts):
                yield Path(dirpath) / f


def load_done_paths(manifest_path: Path) -> set[str]:
    done: set[str] = set()
    if not manifest_path.exists():
        return done
    with open(manifest_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["source_path"])
            except Exception:
                continue
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="Scan DICOM headers into a manifest")
    ap.add_argument("--limit", type=int, default=0, help="stop after N files (0 = all)")
    args = ap.parse_args()

    cfg = c.load_config()
    if not cfg.source_dir:
        print("ERROR: SOURCE_DIR is not set in .env")
        return 2
    root = Path(cfg.source_dir)
    if not root.is_dir():
        print(f"ERROR: SOURCE_DIR does not exist or is not a directory: {root}")
        return 2

    state = cfg.state_path
    log = c.get_logger("scan", state)
    skips = c.SkipLog(state, "scan")
    store = c.StateStore(state)

    log.info("Counting files under %s ...", root)
    total = count_files(root, cfg.file_extensions, cfg.scan_all_files)
    if args.limit:
        total = min(total, args.limit)
    log.info("Found %d candidate files.", total)

    done = load_done_paths(cfg.manifest_path)
    if done:
        log.info("Resuming: %d files already in manifest, will skip them.", len(done))

    manifest_f = open(cfg.manifest_path, "a", encoding="utf-8")
    bar = c.make_progress(total, unit="file", desc="scan")

    ok = notdicom = errors = resumed = 0
    seen = 0
    try:
        for path in iter_candidate_files(root, cfg.file_extensions, cfg.scan_all_files):
            if args.limit and seen >= args.limit:
                break
            seen += 1
            sp = str(path)
            bar.update(1)

            if sp in done:
                resumed += 1
                continue

            # Cheap DICOM detection first (magic number).
            if not c.is_dicom_file(path):
                if not sp.lower().endswith(cfg.file_extensions):
                    notdicom += 1
                    skips.add(sp, "not_dicom", "no DICM magic and non-DICOM extension")
                    continue
                # has a DICOM-ish extension but no magic → still try force-read below

            try:
                st = path.stat()
                header = c.parse_dicom_header(path)
                rec = {
                    "source_path": sp,
                    "source_size_bytes": st.st_size,
                    "source_mtime_utc": st.st_mtime,
                    "scan_ts": c.utcnow_iso(),
                    "status": "ok",
                    **header,
                }
                manifest_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                # keep the resume store seeded so 02_upload has its worklist
                store.add_pending(sp, st.st_size, st.st_mtime)
                ok += 1
                if ok % 2000 == 0:
                    manifest_f.flush()
            except Exception as exc:  # never abort the whole scan
                errors += 1
                skips.add(sp, "header_parse_error", repr(exc))
                log.debug("parse failed: %s: %r", sp, exc)

            bar.set_postfix_str(f"ok={ok} skip={notdicom+errors}")
    except KeyboardInterrupt:
        log.warning("Interrupted — manifest is safe, re-run to resume.")
    finally:
        manifest_f.flush()
        manifest_f.close()
        bar.close()
        skips.close()
        store.close()

    log.info(
        "Scan done. ok=%d resumed=%d not_dicom=%d parse_errors=%d  (skips -> %s)",
        ok, resumed, notdicom, errors, skips.csv_path,
    )
    log.info("Manifest: %s", cfg.manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
