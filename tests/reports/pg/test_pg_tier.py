"""Smoke tests of the PostgreSQL tier itself (ENG-17 thin part)."""

from __future__ import annotations

import os

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from tests.reports.pg.conftest import REPO


def test_template_is_at_alembic_head(pg_engine):
    head = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini"))).get_current_head()
    with pg_engine.connect() as conn:
        current = conn.execute(text("select version_num from alembic_version")).scalar_one()
    assert current == head


def test_server_is_postgres_15_or_newer(pg_engine):
    with pg_engine.connect() as conn:
        num = int(conn.execute(text("show server_version_num")).scalar_one())
    assert num >= 150000


def test_tier_canary(pg_engine):
    # CI runs this once with RPT_PG_CANARY_FAIL=1 and requires a red result, proving
    # that a failing PostgreSQL test fails the job (ENG-17 acceptance).
    with pg_engine.connect() as conn:
        assert conn.execute(text("select 1")).scalar_one() == 1
    assert os.environ.get("RPT_PG_CANARY_FAIL") != "1", "canary: deliberate failure"
