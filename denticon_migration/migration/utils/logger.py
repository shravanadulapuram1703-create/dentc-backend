"""
migration/utils/logger.py
--------------------------
MigrationLogger — captures every run to a timestamped log file.

Creates two files per run inside  migration/logs/ :
  YYYY-MM-DD_HH-MM-SS_migration.log   — plain-text mirror of all console output
  YYYY-MM-DD_HH-MM-SS_migration.json  — structured JSON record for comparisons

Usage (in run_migration.py):
    logger = MigrationLogger()
    logger.start(db_name, data_source, steps_range)
    # ... run steps, calling logger.log_step() and logger.log_error() ...
    logger.finish(table_counts, errors)
"""

import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Log directory ─────────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


class _Tee:
    """
    Writes to both the original stdout and a log file simultaneously.
    Installed as sys.stdout so all print() calls are captured automatically.
    """
    def __init__(self, file_path: Path):
        self._stdout  = sys.stdout
        self._logfile = open(file_path, "w", encoding="utf-8")

    def write(self, text: str):
        self._stdout.write(text)
        self._logfile.write(text)

    def flush(self):
        self._stdout.flush()
        self._logfile.flush()

    def close(self):
        sys.stdout = self._stdout   # restore original stdout
        self._logfile.close()

    # Forward any other attribute access to the real stdout
    def __getattr__(self, name):
        return getattr(self._stdout, name)


class MigrationLogger:
    """
    Wraps a migration run with structured logging.

    Lifecycle:
        logger = MigrationLogger()
        logger.start(...)
        logger.log_step(...)     # called once per step
        logger.log_error(...)    # called if a step raises
        logger.finish(...)       # writes .log and .json files
    """

    def __init__(self):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        self.run_id    = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_path  = LOGS_DIR / f"{self.run_id}_migration.log"
        self.json_path = LOGS_DIR / f"{self.run_id}_migration.json"

        self._tee        = _Tee(self.log_path)
        self._started_at = datetime.now(timezone.utc)
        self._wall_start = time.time()

        # Structured record — gets serialised to JSON at the end
        self._record: dict = {
            "run_id":       self.run_id,
            "started_at":   self._started_at.isoformat(),
            "finished_at":  None,
            "duration_s":   None,
            "status":       "running",
            "database":     {},
            "data_source":  None,
            "steps_range":  None,
            "steps":        [],
            "table_counts": [],
            "total_rows":   0,
            "tables_with_data": 0,
            "errors":       [],
        }

        # Install the tee so all subsequent print() calls go to file too
        sys.stdout = self._tee

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, db_name: str, db_host: str, db_port: int,
              data_source: str, steps_range: str):
        self._record["database"]    = {"name": db_name, "host": db_host, "port": db_port}
        self._record["data_source"] = data_source
        self._record["steps_range"] = steps_range
        print(f"  Log file    : {self.log_path}")

    def log_step(self, step_num: int, name: str,
                 duration_s: float, status: str, error: Optional[str] = None):
        self._record["steps"].append({
            "step":       step_num,
            "name":       name,
            "duration_s": round(duration_s, 2),
            "status":     status,        # "ok" | "failed" | "skipped"
            "error":      error,
        })

    def log_error(self, step_num: int, message: str):
        self._record["errors"].append({
            "step":    step_num,
            "message": message,
        })

    def finish(self, table_counts: list[dict], errors: list[str]):
        """
        Finalise the record, write the JSON file, and restore stdout.

        table_counts: [{"table": str, "domain": str, "rows": int}, ...]
        errors:       list of error strings from the run
        """
        finished_at = datetime.now(timezone.utc)
        duration    = time.time() - self._wall_start

        self._record["finished_at"]       = finished_at.isoformat()
        self._record["duration_s"]        = round(duration, 1)
        self._record["table_counts"]      = table_counts
        self._record["total_rows"]        = sum(t["rows"] for t in table_counts)
        self._record["tables_with_data"]  = sum(1 for t in table_counts if t["rows"] > 0)
        self._record["errors"]            = [
            {"message": e} for e in errors
        ] if errors else []
        self._record["status"] = "failed" if errors else "success"

        # Write JSON
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self._record, f, indent=2, default=str)

        # Print footer in the log before closing the tee
        print(f"\n  Log saved   → {self.log_path.name}")
        print(f"  JSON saved  → {self.json_path.name}")

        # Restore original stdout (stops mirroring to file)
        self._tee.close()

    # ── Comparison helper ─────────────────────────────────────────────────────

    @staticmethod
    def list_runs() -> list[dict]:
        """
        Return a summary list of all past runs, newest first.
        Each entry: {run_id, started_at, duration_s, status, total_rows, tables_with_data, errors}
        """
        runs = []
        for f in sorted(LOGS_DIR.glob("*_migration.json"), reverse=True):
            try:
                with open(f, encoding="utf-8") as fp:
                    data = json.load(fp)
                runs.append({
                    "run_id":           data.get("run_id"),
                    "started_at":       data.get("started_at"),
                    "duration_s":       data.get("duration_s"),
                    "status":           data.get("status"),
                    "total_rows":       data.get("total_rows", 0),
                    "tables_with_data": data.get("tables_with_data", 0),
                    "error_count":      len(data.get("errors", [])),
                    "json_file":        f.name,
                    "log_file":         f.name.replace(".json", ".log"),
                })
            except Exception:
                pass
        return runs

    @staticmethod
    def diff_runs(run_id_a: str, run_id_b: str) -> dict:
        """
        Compare table row counts between two runs.
        Returns {"added": [...], "removed": [...], "changed": [...]}
        """
        def load(rid):
            path = LOGS_DIR / f"{rid}_migration.json"
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {t["table"]: t["rows"] for t in data.get("table_counts", [])}

        a, b = load(run_id_a), load(run_id_b)
        all_tables = set(a) | set(b)

        added   = {t: b[t] for t in all_tables if t not in a and t in b}
        removed = {t: a[t] for t in all_tables if t in a and t not in b}
        changed = {
            t: {"before": a[t], "after": b[t], "delta": b[t] - a[t]}
            for t in all_tables
            if t in a and t in b and a[t] != b[t]
        }
        return {"added": added, "removed": removed, "changed": changed}
