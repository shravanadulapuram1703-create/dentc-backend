"""PostgreSQL test tier of the report engine (ENG-17, 02 §15.1).

How the schema is built (the same way every client database is built, see
docs/onboarding/NEW_CLIENT_DATABASE.md §1.3-1.4):

1. ``tests/pg/baseline_schema.sql`` - a structure-only ``pg_dump --schema-only
   --no-owner --no-privileges`` of the migrated source database - is restored into
   a template database;
2. the template is stamped with ``tests/pg/baseline_revision.txt`` (the
   ``alembic_version`` of the dumped database) and brought to head with
   ``alembic upgrade head``;
3. each test session clones the template (``CREATE DATABASE ... TEMPLATE``).

``Base.metadata.create_all`` is never used here: the reporting views are created
by Alembic revisions, and those must be tested exactly as they deploy.

Configuration: ``TEST_DATABASE_URL`` (SQLAlchemy URL) names a PostgreSQL 15
server and a database this tier may CONNECT to in order to create and drop its
own databases. The tier only ever creates, migrates and drops databases whose
names start with ``rpt_test_``; it never runs anything inside the database named
in the URL besides ``CREATE DATABASE`` / ``DROP DATABASE``. The role needs the
CREATEDB privilege. Without ``TEST_DATABASE_URL`` (or without the baseline files)
every test of this package is skipped - the SQLite suite is unaffected.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url

REPO = Path(__file__).resolve().parents[3]
BASELINE_SQL = REPO / "tests" / "pg" / "baseline_schema.sql"
BASELINE_REV = REPO / "tests" / "pg" / "baseline_revision.txt"
PREFIX = "rpt_test_"
TEMPLATE_DB = PREFIX + "template"


def _skip_reason() -> str | None:
    if not os.environ.get("TEST_DATABASE_URL"):
        return "TEST_DATABASE_URL not set (PostgreSQL tier)"
    if not BASELINE_SQL.exists() or not BASELINE_REV.exists():
        return "tests/pg/baseline_schema.sql or baseline_revision.txt missing"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    reason = _skip_reason()
    if reason is None:
        return
    here = Path(__file__).parent
    for item in items:
        if here in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.skip(reason=reason))


def _guard(name: str) -> str:
    # The only databases this tier may create, migrate or drop.
    if not name.startswith(PREFIX):
        raise RuntimeError(f"refusing to touch database {name!r}: not a {PREFIX}* test database")
    return name


def _server_url() -> URL:
    return make_url(os.environ["TEST_DATABASE_URL"])


def _admin_engine() -> Engine:
    return create_engine(_server_url(), isolation_level="AUTOCOMMIT", pool_pre_ping=True)


def _db_url(name: str) -> URL:
    return _server_url().set(database=_guard(name))


def _drop(admin: Engine, name: str) -> None:
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_guard(name)}" WITH (FORCE)'))


def _restore_baseline(url: URL) -> None:
    """Execute the pg_dump file without psql: drop psql meta-commands (``\\restrict``)
    and the ``transaction_timeout`` setting a newer pg_dump writes for PG 15."""
    lines = []
    for line in BASELINE_SQL.read_text(encoding="utf-8").splitlines():
        if line.startswith("\\") or "transaction_timeout" in line:
            continue
        lines.append(line)
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        raw = engine.raw_connection()
        try:
            with raw.cursor() as cur:
                cur.execute("\n".join(lines))
        finally:
            raw.close()
    finally:
        engine.dispose()


def _alembic(url: URL, *args: str) -> None:
    env = dict(os.environ, DATABASE_URL=url.render_as_string(hide_password=False))
    subprocess.run(  # noqa: S603 - fixed argv: this interpreter running alembic
        [sys.executable, "-c", f"from alembic.config import main; main({list(args)!r})"],
        cwd=REPO, env=env, check=True,
    )


def build_template(admin: Engine) -> None:
    _drop(admin, TEMPLATE_DB)
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{TEMPLATE_DB}"'))
    url = _db_url(TEMPLATE_DB)
    _restore_baseline(url)
    _alembic(url, "stamp", BASELINE_REV.read_text(encoding="utf-8").strip())
    _alembic(url, "upgrade", "head")


@pytest.fixture(scope="session")
def pg_template() -> Iterator[str]:
    admin = _admin_engine()
    try:
        build_template(admin)
        yield TEMPLATE_DB
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def pg_url(pg_template: str) -> Iterator[URL]:
    """A fresh clone of the migrated template for this test session."""
    name = f"{PREFIX}{uuid.uuid4().hex[:12]}"
    admin = _admin_engine()
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{_guard(name)}" TEMPLATE "{_guard(pg_template)}"'))
    try:
        yield _db_url(name)
    finally:
        _drop(admin, name)
        admin.dispose()


@pytest.fixture(scope="session")
def pg_engine(pg_url: URL) -> Iterator[Engine]:
    engine = create_engine(pg_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
