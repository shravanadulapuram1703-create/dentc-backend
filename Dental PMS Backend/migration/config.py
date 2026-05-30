"""
migration/config.py
-------------------
Central configuration loader. Reads from .env (or environment variables).
Import `cfg` anywhere in the migration module to get typed settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the migration/ directory, then from the project root as fallback
_HERE = Path(__file__).parent
load_dotenv(_HERE / ".env", override=False)
load_dotenv(_HERE.parent / ".env", override=False)


class Config:
    # ── Database ──────────────────────────────────────────────────────────────
    DB_HOST: str     = os.environ.get("DB_HOST", "localhost")
    DB_PORT: int     = int(os.environ.get("DB_PORT", 5432))
    DB_NAME: str     = os.environ.get("DB_NAME", "dental_pms")
    DB_USER: str     = os.environ.get("DB_USER", "postgres")
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")

    # ── Source data ──────────────────────────────────────────────────────────
    # Root folder that contains all Denticon .txt exports + LEDGER/, INSCOVERAGE/,
    # CLAIMH/, APPTH_ARCHIVE/ subfolders
    DATA_SOURCE_PATH: Path = Path(
        os.environ.get(
            "DATA_SOURCE_PATH",
            r"F:\Recon Dental Data\Data Migration\Data Migration",
        )
    )

    # ── Denticon tenant seed values ───────────────────────────────────────────
    DENTICON_PGID: str        = os.environ.get("DENTICON_PGID", "2829")
    DENTICON_TENANT_NAME: str = os.environ.get("DENTICON_TENANT_NAME", "Excel Dental")

    # ── Migration behaviour ───────────────────────────────────────────────────
    # How many rows to INSERT per executemany() batch
    BATCH_SIZE: int = int(os.environ.get("MIGRATION_BATCH_SIZE", 500))

    # Max source rows to process per migration step (per target table).
    # None = no limit (full migration). Set via MIGRATION_MAX_ROWS env or --max-rows CLI.
    MIGRATION_MAX_ROWS: int | None = (
        int(os.environ["MIGRATION_MAX_ROWS"])
        if os.environ.get("MIGRATION_MAX_ROWS", "").strip()
        else None
    )

    def __init__(self):
        self._step_rows_yielded = 0

    def begin_step(self) -> None:
        """Reset per-step row counter (call at the start of each migration step)."""
        self._step_rows_yielded = 0

    def step_rows_read(self) -> int:
        return self._step_rows_yielded

    def row_budget_exhausted(self) -> bool:
        if self.MIGRATION_MAX_ROWS is None:
            return False
        return self._step_rows_yielded >= self.MIGRATION_MAX_ROWS

    def consume_row_budget(self) -> None:
        if self.MIGRATION_MAX_ROWS is not None:
            self._step_rows_yielded += 1

    def row_limit_label(self) -> str:
        if self.MIGRATION_MAX_ROWS is None:
            return "all rows"
        return f"max {self.MIGRATION_MAX_ROWS:,} rows/step"

    @property
    def dsn(self) -> str:
        return (
            f"host={self.DB_HOST} port={self.DB_PORT} "
            f"dbname={self.DB_NAME} user={self.DB_USER} "
            f"password={self.DB_PASSWORD}"
        )

    def src(self, *parts: str) -> Path:
        """Return an absolute path under DATA_SOURCE_PATH."""
        return self.DATA_SOURCE_PATH.joinpath(*parts)


cfg = Config()
