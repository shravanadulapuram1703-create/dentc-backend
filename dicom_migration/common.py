"""
Shared helpers for the DICOM → GCS + Postgres migration toolkit.

Everything the numbered scripts (01_scan, 02_upload, 03_load_staging,
04_reconcile) rely on lives here: config loading, logging, a robust retry
helper, DICOM header parsing, streaming SHA-256, an optional upload-bandwidth
limiter, and a small SQLite "resume" store so a killed run picks up where it
left off.

Design rules for this toolkit (they match the emphasis of the migration plan):
  * NEVER let one bad file kill the run. Every per-file operation is wrapped;
    failures are recorded and the run continues.
  * Everything is resumable. Re-running any step skips work already done.
  * Every skip/failure is written to a CSV *and* a JSON so nothing is silent.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import random
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence

# ── third-party (installed via requirements.txt) ──────────────────────────────
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is optional at runtime
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

# ──────────────────────────────────────────────────────────────────────────────
# Paths / constants
# ──────────────────────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent
DEFAULT_STATE_DIR = HERE / "state"
DICOM_MAGIC_OFFSET = 128
DICOM_MAGIC = b"DICM"
HASH_CHUNK = 4 * 1024 * 1024  # 4 MiB read blocks for hashing / uploading


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    # source
    source_dir: str = ""
    file_extensions: tuple[str, ...] = (".dic", ".dcm")
    scan_all_files: bool = True  # also detect DICOM by magic number, not just ext

    # GCS
    gcs_bucket_originals: str = ""
    gcs_bucket_derived: str = ""      # thumbnails/web JPEGs; falls back to originals bucket
    gcs_prefix: str = "dicom"
    gcs_ops_bucket: str = ""          # optional: where journals/reports get copied
    google_credentials: str = ""      # path to service-account JSON key

    # run tuning
    workers: int = 8
    max_bandwidth_mbps: float = 0.0   # 0 = unlimited (megabits/sec, upload only)
    retry_max: int = 6
    retry_base_delay: float = 1.5     # seconds; exponential backoff base

    # state / output
    state_dir: str = str(DEFAULT_STATE_DIR)

    # Postgres (only used by 03_load_staging / 04_reconcile)
    database_url: str = ""
    db_host: str = ""
    db_port: str = "5432"
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""

    @property
    def state_path(self) -> Path:
        p = Path(self.state_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def manifest_path(self) -> Path:
        return self.state_path / "manifest.ndjson"

    def dsn(self) -> str:
        """Assemble a libpq DSN. DATABASE_URL wins if set."""
        if self.database_url:
            return self.database_url
        parts = [
            f"host={self.db_host}",
            f"port={self.db_port}",
            f"dbname={self.db_name}",
            f"user={self.db_user}",
        ]
        if self.db_password:
            parts.append(f"password={self.db_password}")
        return " ".join(parts)


def _get_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_config() -> Config:
    """Load config from a .env file next to this script (and real env vars)."""
    load_dotenv(HERE / ".env")
    cfg = Config(
        source_dir=os.getenv("SOURCE_DIR", "").strip(),
        gcs_bucket_originals=os.getenv("GCS_BUCKET_ORIGINALS", "").strip(),
        gcs_bucket_derived=os.getenv("GCS_BUCKET_DERIVED", "").strip(),
        gcs_prefix=os.getenv("GCS_PREFIX", "dicom").strip(),
        gcs_ops_bucket=os.getenv("GCS_OPS_BUCKET", "").strip(),
        google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip(),
        workers=int(os.getenv("WORKERS", "8") or "8"),
        max_bandwidth_mbps=float(os.getenv("MAX_BANDWIDTH_MBPS", "0") or "0"),
        retry_max=int(os.getenv("RETRY_MAX", "6") or "6"),
        retry_base_delay=float(os.getenv("RETRY_BASE_DELAY", "1.5") or "1.5"),
        state_dir=os.getenv("STATE_DIR", str(DEFAULT_STATE_DIR)).strip() or str(DEFAULT_STATE_DIR),
        database_url=os.getenv("DATABASE_URL", "").strip(),
        db_host=os.getenv("DB_HOST", "").strip(),
        db_port=os.getenv("DB_PORT", "5432").strip() or "5432",
        db_name=os.getenv("DB_NAME", "").strip(),
        db_user=os.getenv("DB_USER", "").strip(),
        db_password=os.getenv("DB_PASSWORD", "").strip(),
    )
    cfg.scan_all_files = _get_bool("SCAN_ALL_FILES", True)
    exts = os.getenv("FILE_EXTENSIONS", "").strip()
    if exts:
        cfg.file_extensions = tuple(
            e if e.startswith(".") else f".{e}"
            for e in (x.strip().lower() for x in exts.split(",")) if e
        )
    # Make the credentials visible to the google client library.
    if cfg.google_credentials:
        os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", cfg.google_credentials)
    return cfg


# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────

def get_logger(name: str, state_dir: Path) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")

    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(fmt)
    log.addHandler(ch)

    logfile = state_dir / f"{name}.log"
    fh = RotatingFileHandler(logfile, maxBytes=20 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    log.addHandler(fh)
    return log


# ──────────────────────────────────────────────────────────────────────────────
# Retry
# ──────────────────────────────────────────────────────────────────────────────

class RetryError(Exception):
    def __init__(self, attempts: int, last: BaseException):
        super().__init__(f"failed after {attempts} attempts: {last!r}")
        self.attempts = attempts
        self.last = last


def with_retry(
    fn: Callable[[], Any],
    *,
    attempts: int,
    base_delay: float,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    give_up_on: tuple[type[BaseException], ...] = (),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> Any:
    """Call ``fn`` with exponential backoff + jitter.

    ``give_up_on`` exceptions are re-raised immediately (e.g. a 412
    "already exists" precondition, which the caller wants to treat specially).
    """
    last: BaseException | None = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except give_up_on:
            raise
        except retry_on as exc:  # noqa: PERF203
            last = exc
            if i >= attempts:
                break
            delay = base_delay * (2 ** (i - 1))
            delay = min(delay, 60.0) + random.uniform(0, base_delay)
            if on_retry:
                on_retry(i, exc, delay)
            time.sleep(delay)
    assert last is not None
    raise RetryError(attempts, last)


# ──────────────────────────────────────────────────────────────────────────────
# DICOM helpers
# ──────────────────────────────────────────────────────────────────────────────

def is_dicom_file(path: Path) -> bool:
    """Cheap check: DICOM Part-10 preamble (128 bytes) followed by 'DICM'."""
    try:
        with open(path, "rb") as fh:
            fh.seek(DICOM_MAGIC_OFFSET)
            return fh.read(4) == DICOM_MAGIC
    except Exception:
        return False


def _s(v: Any) -> str | None:
    if v is None:
        return None
    try:
        s = str(v).strip()
        return s or None
    except Exception:
        return None


def _i(v: Any) -> int | None:
    try:
        return int(v)
    except Exception:
        return None


def parse_dicom_header(path: Path) -> dict[str, Any]:
    """Header-only parse (stops before pixel data -> reads ~a few KB, not the
    whole file). Returns a manifest dict. Raises on unreadable files so the
    caller can log a skip."""
    import pydicom  # imported lazily so 'scan' is the only step that needs it

    with open(path, "rb") as fh:
        ds = pydicom.dcmread(fh, stop_before_pixels=True, force=True)

    # tooth / anatomy codes from (0008,2228) Primary Anatomic Structure Sequence
    tooth_codes: list[str] = []
    try:
        seq = ds.get((0x0008, 0x2228))
        if seq and seq.value:
            for item in seq.value:
                code = item.get((0x0008, 0x0100))
                if code and code.value:
                    tooth_codes.append(str(code.value).strip())
    except Exception:
        pass

    file_meta = getattr(ds, "file_meta", None)
    transfer_syntax = None
    source_ae = None
    impl_version = None
    if file_meta is not None:
        transfer_syntax = _s(getattr(file_meta, "TransferSyntaxUID", None))
        source_ae = _s(getattr(file_meta, "SourceApplicationEntityTitle", None))
        impl_version = _s(getattr(file_meta, "ImplementationVersionName", None))

    return {
        "sop_instance_uid": _s(ds.get("SOPInstanceUID")),
        "sop_class_uid": _s(ds.get("SOPClassUID")),
        "study_instance_uid": _s(ds.get("StudyInstanceUID")),
        "series_instance_uid": _s(ds.get("SeriesInstanceUID")),
        "accession_number": _s(ds.get("AccessionNumber")),
        "study_id": _s(ds.get("StudyID")),
        "series_number": _s(ds.get("SeriesNumber")),
        "instance_number": _s(ds.get("InstanceNumber")),
        "transfer_syntax_uid": transfer_syntax,
        # patient identity (PHI)
        "patient_id": _s(ds.get("PatientID")),
        "patient_name_raw": _s(ds.get("PatientName")),
        "patient_birth_date": _s(ds.get("PatientBirthDate")),
        "patient_sex": _s(ds.get("PatientSex")),
        # clinical
        "modality": _s(ds.get("Modality")),
        "study_date": _s(ds.get("StudyDate")),
        "study_time": _s(ds.get("StudyTime")),
        "content_date": _s(ds.get("ContentDate")),
        "content_time": _s(ds.get("ContentTime")),
        "acquisition_date": _s(ds.get("AcquisitionDate")),
        "body_part_examined": _s(ds.get("BodyPartExamined")),
        "view_position": _s(ds.get("ViewPosition")),
        "image_comments": _s(ds.get("ImageComments")),
        "anatomic_structure_codes": tooth_codes,
        # pixel geometry (drives server-side derivative generation later)
        "rows": _i(ds.get("Rows")),
        "columns": _i(ds.get("Columns")),
        "bits_allocated": _i(ds.get("BitsAllocated")),
        "bits_stored": _i(ds.get("BitsStored")),
        "samples_per_pixel": _i(ds.get("SamplesPerPixel")),
        "photometric_interpretation": _s(ds.get("PhotometricInterpretation")),
        "window_center": _s(ds.get("WindowCenter")),
        "window_width": _s(ds.get("WindowWidth")),
        # provenance / the "CORRECT" (re-identification) detector
        "manufacturer": _s(ds.get("Manufacturer")),
        "manufacturer_model_name": _s(ds.get("ManufacturerModelName")),
        "software_versions": _s(ds.get("SoftwareVersions")),
        "institution_name": _s(ds.get("InstitutionName")),
        "station_name": _s(ds.get("StationName")),
        "operator": _s(ds.get("OperatorsName")),
        "source_ae_title": source_ae,
        "implementation_version": impl_version,
        "has_original_attributes_seq": ds.get((0x0400, 0x0561)) is not None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Hashing
# ──────────────────────────────────────────────────────────────────────────────

def sha256_file(path: Path, *, chunk: int = HASH_CHUNK) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def object_key_for(sha256_hex: str, prefix: str) -> str:
    return f"{prefix}/{sha256_hex[0:2]}/{sha256_hex[2:4]}/{sha256_hex}.dcm"


# ──────────────────────────────────────────────────────────────────────────────
# Bandwidth limiter (upload only)
# ──────────────────────────────────────────────────────────────────────────────

class TokenBucket:
    """Thread-safe byte token bucket. ``rate`` is bytes/sec; 0 = unlimited."""

    def __init__(self, rate_bytes_per_sec: float):
        self.rate = rate_bytes_per_sec
        self.capacity = max(rate_bytes_per_sec, HASH_CHUNK)
        self.tokens = self.capacity
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, n: int) -> None:
        if self.rate <= 0:
            return
        with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= n:
                    self.tokens -= n
                    return
                deficit = n - self.tokens
                time.sleep(deficit / self.rate)


class ThrottledReader:
    """Wraps a binary file object and rate-limits reads through a TokenBucket.
    Passed to blob.upload_from_file so we throttle the *upload*, not disk I/O."""

    def __init__(self, fileobj, bucket: TokenBucket):
        self._f = fileobj
        self._b = bucket

    def read(self, size: int = -1) -> bytes:
        data = self._f.read(size)
        if data:
            self._b.consume(len(data))
        return data

    def __getattr__(self, item):
        return getattr(self._f, item)


# ──────────────────────────────────────────────────────────────────────────────
# Skip / failure logging (CSV + JSON, side by side)
# ──────────────────────────────────────────────────────────────────────────────

class SkipLog:
    """Append-only, thread-safe log of skipped/failed items -> CSV and NDJSON."""

    FIELDS = ("timestamp", "phase", "source_path", "reason", "detail")

    def __init__(self, state_dir: Path, phase: str):
        self.lock = threading.Lock()
        self.csv_path = state_dir / f"skipped_{phase}.csv"
        self.json_path = state_dir / f"skipped_{phase}.jsonl"
        self.phase = phase
        new = not self.csv_path.exists()
        self._csv_f = open(self.csv_path, "a", newline="", encoding="utf-8")
        self._csv = csv.writer(self._csv_f)
        if new:
            self._csv.writerow(self.FIELDS)
            self._csv_f.flush()
        self._json_f = open(self.json_path, "a", encoding="utf-8")
        self.count = 0

    def add(self, source_path: str, reason: str, detail: str = "") -> None:
        row = {
            "timestamp": utcnow_iso(),
            "phase": self.phase,
            "source_path": source_path,
            "reason": reason,
            "detail": (detail or "")[:2000],
        }
        with self.lock:
            self.count += 1
            self._csv.writerow([row[k] for k in self.FIELDS])
            self._csv_f.flush()
            self._json_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._json_f.flush()

    def close(self) -> None:
        with self.lock:
            try:
                self._csv_f.close()
            finally:
                self._json_f.close()


# ──────────────────────────────────────────────────────────────────────────────
# SQLite resume store (shared by scan + upload)
# ──────────────────────────────────────────────────────────────────────────────

class StateStore:
    """Tracks every source file's progress so any step can resume.

    status values:
      pending   - discovered, not yet uploaded
      uploaded  - bytes written to GCS this run
      exists    - already in GCS (dedupe / previous run) — success
      skipped   - permanently skipped (not DICOM / unreadable)
      error     - transient failure; will be retried on next run
    """

    _DONE = ("uploaded", "exists")

    def __init__(self, state_dir: Path):
        self.path = state_dir / "state.db"
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=60)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                source_path TEXT PRIMARY KEY,
                size        INTEGER,
                mtime       REAL,
                status      TEXT NOT NULL DEFAULT 'pending',
                sha256      TEXT,
                object_key  TEXT,
                attempts    INTEGER NOT NULL DEFAULT 0,
                error       TEXT,
                updated_at  TEXT
            )
            """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_files_status ON files(status)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS ix_files_sha ON files(sha256)")
        self.conn.commit()

    # --- writes -----------------------------------------------------------
    def add_pending(self, source_path: str, size: int, mtime: float) -> None:
        with self.lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO files(source_path,size,mtime,status,updated_at) "
                "VALUES (?,?,?, 'pending', ?)",
                (source_path, size, mtime, utcnow_iso()),
            )
            self.conn.commit()

    def mark(self, source_path: str, status: str, *, sha256: str | None = None,
             object_key: str | None = None, error: str | None = None,
             bump_attempt: bool = False) -> None:
        with self.lock:
            self.conn.execute(
                f"""
                UPDATE files SET status=?, sha256=COALESCE(?,sha256),
                    object_key=COALESCE(?,object_key), error=?,
                    attempts=attempts+{1 if bump_attempt else 0}, updated_at=?
                WHERE source_path=?
                """,
                (status, sha256, object_key, (error or "")[:1000], utcnow_iso(), source_path),
            )
            self.conn.commit()

    # --- reads ------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        cur = self.conn.execute("SELECT status, COUNT(*) FROM files GROUP BY status")
        return {row[0]: row[1] for row in cur.fetchall()}

    def total(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]

    def bytes_done(self) -> int:
        cur = self.conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM files WHERE status IN ('uploaded','exists')"
        )
        return cur.fetchone()[0]

    def iter_todo(self) -> Iterator[tuple[str, int]]:
        """Files still needing upload (pending or previously errored)."""
        cur = self.conn.execute(
            "SELECT source_path, size FROM files WHERE status IN ('pending','error')"
        )
        for row in cur:
            yield row[0], row[1]

    def iter_all(self) -> Iterator[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.execute("SELECT * FROM files")
        for row in cur:
            yield row
        self.conn.row_factory = None

    def close(self) -> None:
        with self.lock:
            self.conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# Progress bar (tqdm if available, else a plain fallback)
# ──────────────────────────────────────────────────────────────────────────────

def make_progress(total: int, unit: str = "file", desc: str = "progress"):
    try:
        from tqdm import tqdm

        return tqdm(total=total, unit=unit, desc=desc, dynamic_ncols=True,
                    smoothing=0.05, miniters=1)
    except Exception:
        return _PlainProgress(total, desc)


class _PlainProgress:
    """Minimal stderr progress printer used when tqdm isn't installed."""

    def __init__(self, total: int, desc: str):
        self.total = total
        self.n = 0
        self.desc = desc
        self.start = time.monotonic()
        self.postfix = ""

    def update(self, k: int = 1):
        self.n += k
        if self.n % 200 == 0 or self.n == self.total:
            self._draw()

    def set_postfix_str(self, s: str):
        self.postfix = s

    def _draw(self):
        el = time.monotonic() - self.start
        rate = self.n / el if el else 0
        pct = (100.0 * self.n / self.total) if self.total else 0
        eta = (self.total - self.n) / rate if rate else 0
        sys.stderr.write(
            f"\r{self.desc}: {self.n}/{self.total} ({pct:5.1f}%) "
            f"{rate:6.1f}/s ETA {eta/60:6.1f}m  {self.postfix}   "
        )
        sys.stderr.flush()

    def close(self):
        self._draw()
        sys.stderr.write("\n")


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"
