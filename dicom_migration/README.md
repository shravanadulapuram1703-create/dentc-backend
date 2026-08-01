# DICOM Migration Toolkit

Self-contained scripts to move the legacy dental imaging archive
(~500 GB / ~450k `.dic` files / ~34k patients) into **Google Cloud Storage** and
index it in **Postgres**, per the approved migration plan.

Runs from the machine where the data lives. Designed for a **big, unattended
run**: retries transient failures, never aborts on a bad file, logs every skip
to CSV + JSON, resumes where it left off, and shows live progress in the
terminal.

---

## What it does

| Step | Script | What it does | Touches |
|------|--------|--------------|---------|
| 1 | `01_scan.py` | Reads each file's DICOM **header only** (a few KB) → `state/manifest.ndjson`. Non-DICOM/unreadable files → `state/skipped_scan.csv`. | local disk |
| 2 | `02_upload.py` | Hashes each file (SHA-256) and uploads it to GCS at a content-addressed key `dicom/aa/bb/<sha256>.dcm`. Retries, resumes, dedupes. | local disk → GCS |
| 3 | `03_load_staging.py` | Loads the manifest into Postgres staging tables (`mig_dicom_*`) and links each image's `PatientID` to `patients.legacy_id`. | Postgres |
| 4 | `04_reconcile.py` | Cross-checks manifest vs upload state vs the live GCS listing. Prints **GO / NO-GO**. | GCS (read-only) |
| 5 | `05_promote.py` | Promotes matched staging rows into the app's live `dicom_studies/series/instances` + `stored_objects` tables. Skips the unmatched quarantine. Idempotent. | Postgres |
| 6 | `06_derivatives.py` | Decodes each promoted image → browser-viewable **thumbnail + web JPEGs**, uploads to GCS (`derived/…`), flips the instance to `ready`. | local/GCS → GCS + Postgres |

> Steps 1–4 get bytes into GCS + metadata into staging. Steps **5 (promote)**
> and **6 (derivatives)** make the images appear and render in the app's imaging
> tab — run them after the backend `alembic upgrade head` has created the
> `dicom_*` tables. At **full scale (450k)**, step 6 runs as a sharded Cloud Run
> Job instead of locally; the decode/encode recipe is identical.

---

## One-time setup (admin, once)

Run `setup_gcp.sh` with a GCP account that has project-admin rights. It creates
the buckets + a least-privilege **upload-only** service account and writes a key
file (`sa-dicom-ingest.json`) to hand to whoever runs the upload:

```bash
bash setup_gcp.sh
```

(If you already created the bucket + service-account key by hand, skip this.)

---

## Setup on the machine with the data (the person running it)

1. **Install Python 3.10+**, then the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. **Copy the config template and fill it in:**
   ```bash
   copy .env.example .env      REM Windows
   # cp .env.example .env      # macOS/Linux
   ```
   Set at minimum: `SOURCE_DIR`, `GCS_BUCKET_ORIGINALS`,
   `GOOGLE_APPLICATION_CREDENTIALS` (path to the key file), and — for step 3 —
   the `DATABASE_URL` / `DB_*` values.
3. Put the `sa-dicom-ingest.json` key file where `.env` points.

---

## Running it

Run the steps in order. **Every step is safe to stop (Ctrl-C) and re-run** — it
resumes automatically.

```bash
# 0) SANITY CHECK — scan just the first 200 files and confirm it looks right
python 01_scan.py --limit 200

# 1) Full header scan  (15–90 min)
python 01_scan.py

# 2) Upload everything to GCS  (the long one — hours, depends on your upload speed)
python 02_upload.py
#    ...if the run stops for any reason, just run it again — it continues:
python 02_upload.py

# 3) Load metadata + link patients into Postgres
python 03_load_staging.py

# 4) Verify everything landed  (prints GO / NO-GO)
python 04_reconcile.py

# 5) Promote staging → the app's live dicom_* tables  (minutes; batched + idempotent)
python 05_promote.py            # add --dry-run first to preview counts, writes nothing

# 6) Generate thumbnail + web JPEGs  (the CPU-heavy one — see the note below)
python 06_derivatives.py --procs 8    # set --procs to your CPU core count
```

> ### ⚡ Step 6 speed: use `--procs = your CPU core count`
>
> Dental DICOM is **JPEG-2000**, and decoding it is CPU-bound work that holds
> Python's GIL — so **threads don't help** (`--workers` only overlaps the GCS
> uploads). Running a single process, or bumping `--workers`, tops out at **one
> core** (~5 img/s ⇒ ~19 h for 350k images).
>
> **The fast path is `--procs N`, which fans out into N separate processes (one
> per core) — the only thing that actually uses all your cores.** Check your
> count first:
> ```bash
> python -c "import os; print(os.cpu_count())"   # then use that as --procs
> ```
> Throughput scales ~linearly with cores (≈ cores × 5 img/s):
>
> | `--procs` (cores) | ~img/s | ETA for ~350k |
> |---|---|---|
> | 4 | ~20 | ~4.8 h |
> | 8 | ~40 | ~2.4 h |
> | 16 | ~80 | ~1.2 h |
> | 32 (big VM) | ~160 | ~36 min |
>
> It's idempotent and resumable (skips `ready` rows; Ctrl-C safe). Each process
> logs to `state/derivatives.shard{k}.log`. To go faster than one machine allows,
> split the **same total** across boxes: `--shards 32 --shard 0..15` on box A,
> `--shards 32 --shard 16..31` on box B. Don't set `--procs` above your physical
> core count — decode is CPU-bound, so extra processes just thrash.

### Before the big upload: measure your upload speed
Upload time is dominated by your **upload** bandwidth (not download). Rough
guide for 500 GB:

| Sustained upload | Approx. time |
|---|---|
| 35 Mbps (typical business cable) | ~42 h (a Fri-evening → Mon-morning window) |
| 100 Mbps | ~15 h |
| 200 Mbps | ~7 h |
| 1 Gbps | ~1.5 h |

To avoid saturating the clinic's internet during office hours, cap the speed in
`.env`, e.g. `MAX_BANDWIDTH_MBPS=20`, and raise it after hours.

---

## Progress, logs, and skipped files

Everything lives in the `state/` folder:

| File | What |
|---|---|
| `manifest.ndjson` | one JSON line per readable file (the inventory) |
| `state.db` | SQLite resume/progress store (per-file status) |
| `skipped_scan.csv` / `.jsonl` | files that weren't DICOM or wouldn't parse |
| `skipped_upload.csv` / `.jsonl` | files that failed to upload after all retries |
| `reconcile_report.json` | final counts + GO/NO-GO |
| `reconcile_discrepancies.csv` | any missing / orphan / size-mismatch objects |
| `*.log` | full run logs |

The terminal shows a live bar: files done / total, %, throughput (MB/s), ETA,
and running counts of `up` (uploaded) / `dup` (already in GCS) / `err` / `skip`.

**Nothing is ever silently dropped.** A file that can't be processed is recorded
in a skip log with the reason, and the run keeps going. Re-running retries any
`error` files automatically; permanently-bad files (`skipped`) stay logged for
review.

---

## How "resume" and "no duplicates" work

* Each file's status is tracked in `state/state.db`. Re-running any step only
  does what's still outstanding.
* Object keys are the file's **SHA-256**, so identical files collapse to one
  object automatically, and uploads use *create-only* (`if_generation_match=0`)
  — re-uploading an existing object is detected and counted as `dup`, never
  duplicated or overwritten.

---

## What's NOT in this toolkit (by design)

* **Derivative images** (thumbnails / web JPEGs) — generated server-side on
  Cloud Run after ingest.
* **Promotion into the app's live `dicom_study/series/instance` tables** — that
  happens from the backend once its schema migration is deployed; this toolkit
  populates the migration-owned `mig_dicom_*` staging tables, which the backend
  reads from. (Ask the backend team to run the promotion step after step 4 is
  GREEN.)

---

## Quick troubleshooting

| Symptom | Fix |
|---|---|
| `Could not create GCS client` | Check `GOOGLE_APPLICATION_CREDENTIALS` points to the key file and `GCS_BUCKET_ORIGINALS` is correct. |
| `No manifest … run 01_scan.py first` | Run step 1 before step 2. |
| Uploads slow / clinic internet choked | Set `MAX_BANDWIDTH_MBPS` in `.env`. |
| Postgres connection refused | Check `DATABASE_URL`/`DB_*`; the machine must reach Cloud SQL (public IP + authorized network, or the cloud-sql-proxy). |
| Lots of `unmatched` patients in step 3 | Expected for legacy id-scheme mismatches; review `mig_patient_link WHERE match_method='unmatched'` with the clinic before promotion. |
