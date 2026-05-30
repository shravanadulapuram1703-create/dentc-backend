"""
migration/utils/reader.py
--------------------------
Reads Denticon export files (.txt).

Exports may be tab- or comma-delimited (Recon Dental dumps use comma-separated
CSV with quoted fields). All files are:
  - Double-quote escaped strings
  - Windows-1252 (cp1252) encoded
  - First row is the header
  - May have an empty trailing row (skip rows where first field is blank)
"""

import csv
import glob
import os
from pathlib import Path
from typing import Generator, Dict

from migration.config import cfg


def _detect_delimiter(first_line: str) -> str:
    """Pick tab vs comma based on the header row."""
    tab_count = first_line.count("\t")
    comma_count = first_line.count(",")
    if tab_count > comma_count:
        return "\t"
    return ","


def read_denticon_file(
    path: str | Path,
    *,
    apply_limit: bool = True,
) -> Generator[Dict[str, str], None, None]:
    """
    Yield each data row from a Denticon .txt export file as a dict keyed by
    column header. Skips the header row and any trailing empty rows.

    When cfg.MIGRATION_MAX_ROWS is set, stops after that many rows per migration
    step (shared budget across read_denticon_file / read_folder in the same step).
    Pass apply_limit=False for lookup-only scans that should not consume the budget.

    Usage:
        for row in read_denticon_file("RespParty.txt"):
            print(row["RPID"], row["FNAME"])
    """
    path = str(path)
    with open(path, "r", encoding="cp1252", errors="replace", newline="") as f:
        first_line = f.readline()
        if not first_line:
            return
        delimiter = _detect_delimiter(first_line)

        def _lines():
            yield first_line
            yield from f

        reader = csv.reader(_lines(), delimiter=delimiter, quotechar='"')
        try:
            headers = [h.strip().lstrip("\ufeff") for h in next(reader)]
        except StopIteration:
            return  # empty file
        for row in reader:
            if apply_limit and cfg.row_budget_exhausted():
                return
            if not row:
                continue
            # Skip trailing blank rows (first field is empty)
            if not row[0].strip():
                continue
            # Pad short rows to avoid KeyError on missing trailing columns
            while len(row) < len(headers):
                row.append("")
            if apply_limit:
                cfg.consume_row_budget()
            yield dict(zip(headers, row))


def read_folder(
    folder_path: str | Path,
    *,
    apply_limit: bool = True,
) -> Generator[Dict[str, str], None, None]:
    """
    Yield rows from ALL .txt files in a folder in alphabetical order.
    Used for split-file folders: LEDGER (36 files), INSCOVERAGE (11), etc.

    Usage:
        for row in read_folder(cfg.src("LEDGER")):
            ...
    """
    folder_path = str(folder_path)
    for fpath in sorted(glob.glob(os.path.join(folder_path, "*.txt"))):
        yield from read_denticon_file(fpath, apply_limit=apply_limit)


def file_has_data(path: str | Path) -> bool:
    """
    Return True if the file has at least one non-empty data row
    (i.e. is not a header-only empty export).
    """
    for _ in read_denticon_file(path):
        return True
    return False
