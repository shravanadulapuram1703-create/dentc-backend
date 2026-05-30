#!/usr/bin/env python3
"""
show_logs.py
------------
Lists all past migration runs and can diff two runs to show what changed.

Usage (from "Dental PMS Backend" directory):
    python migration/show_logs.py                        # List all runs
    python migration/show_logs.py --run YYYY-MM-DD_HH-MM-SS   # Full detail for one run
    python migration/show_logs.py --diff RUN_A RUN_B          # Compare row counts
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from migration.utils.logger import MigrationLogger, LOGS_DIR


def cmd_list():
    runs = MigrationLogger.list_runs()
    if not runs:
        print("  No migration runs found in migration/logs/")
        return

    print(f"\n  {'RUN ID':<25} {'STATUS':<10} {'ROWS':>8}  {'TABLES':>7}  {'ERRORS':>7}  {'DURATION':>9}")
    print("  " + "─" * 70)
    for r in runs:
        status  = r["status"].upper()
        dur     = f"{r['duration_s']}s" if r["duration_s"] else "?"
        errs    = str(r["error_count"]) if r["error_count"] else "—"
        print(
            f"  {r['run_id']:<25} {status:<10} {r['total_rows']:>8,}  "
            f"{r['tables_with_data']:>7}  {errs:>7}  {dur:>9}"
        )
    print(f"\n  {len(runs)} run(s) total  •  logs in: {LOGS_DIR}\n")


def cmd_run(run_id: str):
    path = LOGS_DIR / f"{run_id}_migration.json"
    if not path.exists():
        print(f"  Run '{run_id}' not found in {LOGS_DIR}")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n── Run: {run_id} ──────────────────────────────────────────────────")
    print(f"  Status     : {data['status'].upper()}")
    print(f"  Started    : {data['started_at']}")
    print(f"  Finished   : {data['finished_at']}")
    print(f"  Duration   : {data['duration_s']}s")
    print(f"  Database   : {data['database'].get('name')} @ {data['database'].get('host')}")
    print(f"  Steps run  : {len(data['steps'])}")
    print(f"  Total rows : {data['total_rows']:,}")
    print(f"  Tables w/data: {data['tables_with_data']}")

    if data["errors"]:
        print(f"\n  Errors ({len(data['errors'])}):")
        for e in data["errors"]:
            print(f"    ✗ {e['message']}")

    print(f"\n  Step timings:")
    print(f"  {'#':<4} {'STEP NAME':<40} {'STATUS':<8} {'TIME':>6}")
    print("  " + "─" * 62)
    for s in data["steps"]:
        status = "✓ ok" if s["status"] == "ok" else "✗ FAIL"
        print(f"  {s['step']:<4} {s['name']:<40} {status:<8} {s['duration_s']:>5.1f}s")

    print(f"\n  Table counts (non-zero only):")
    print(f"  {'TABLE':<42} {'DOMAIN':<12} {'ROWS':>8}")
    print("  " + "─" * 65)
    for t in data["table_counts"]:
        if t["rows"] > 0:
            print(f"  ✓ {t['table']:<40} {t['domain']:<12} {t['rows']:>8,}")
    print()


def cmd_diff(run_a: str, run_b: str):
    try:
        diff = MigrationLogger.diff_runs(run_a, run_b)
    except FileNotFoundError as e:
        print(f"  Could not load run: {e}")
        sys.exit(1)

    print(f"\n── Diff: {run_a}  →  {run_b} ────────────────────────────────────")

    if diff["changed"]:
        print(f"\n  Changed tables ({len(diff['changed'])}):")
        print(f"  {'TABLE':<42} {'BEFORE':>8}  {'AFTER':>8}  {'DELTA':>8}")
        print("  " + "─" * 70)
        for t, v in sorted(diff["changed"].items()):
            arrow = "▲" if v["delta"] > 0 else "▼"
            print(f"  {t:<42} {v['before']:>8,}  {v['after']:>8,}  "
                  f"{arrow}{abs(v['delta']):>7,}")
    else:
        print("  No changes in row counts between the two runs.")

    if diff["added"]:
        print(f"\n  Tables added in {run_b} ({len(diff['added'])}):")
        for t, rows in diff["added"].items():
            print(f"    + {t}: {rows:,} rows")

    if diff["removed"]:
        print(f"\n  Tables removed since {run_a} ({len(diff['removed'])}):")
        for t, rows in diff["removed"].items():
            print(f"    - {t}: was {rows:,} rows")

    print()


def main():
    parser = argparse.ArgumentParser(description="View migration run history")
    parser.add_argument("--run",  metavar="RUN_ID",
                        help="Show full detail for a specific run")
    parser.add_argument("--diff", nargs=2, metavar=("RUN_A", "RUN_B"),
                        help="Compare row counts between two runs")
    args = parser.parse_args()

    if args.run:
        cmd_run(args.run)
    elif args.diff:
        cmd_diff(args.diff[0], args.diff[1])
    else:
        cmd_list()


if __name__ == "__main__":
    main()
