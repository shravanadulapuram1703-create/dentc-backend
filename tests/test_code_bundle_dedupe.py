"""Explosion Codes (code_bundles) dedupe — data-note fix.

Duplicate bundles per (tenant_id, legacy_id) are collapsed to the lowest id; the
model now carries a unique constraint so it cannot recur. API-created bundles have
a NULL legacy_id and are exempt (multiple NULLs allowed).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import CodeBundle
from scripts.dedupe_code_bundles import dedupe


@pytest.fixture
def legacy_db():
    """An isolated session whose code_bundles table predates the unique constraint
    (so the importer-style duplicates can be seeded and then deduped)."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        c.execute(text(
            "CREATE TABLE code_bundles (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "tenant_id INTEGER, legacy_id VARCHAR)"
        ))
        c.execute(text(
            "CREATE TABLE code_bundle_items (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "bundle_id INTEGER)"
        ))
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def _seed_dupes(db, tenant_id, legacy_id, n) -> list[int]:
    ids = []
    for _ in range(n):
        r = db.execute(
            text("INSERT INTO code_bundles (tenant_id, legacy_id) VALUES (:t, :l)"),
            {"t": tenant_id, "l": legacy_id},
        )
        ids.append(int(r.lastrowid))
    for bid in ids:
        db.execute(text("INSERT INTO code_bundle_items (bundle_id) VALUES (:b)"), {"b": bid})
    db.commit()
    return ids


def test_dedupe_collapses_duplicates_and_is_idempotent(legacy_db):
    ids = _seed_dupes(legacy_db, 1, "100", 4)
    keep = min(ids)

    removed = dedupe(legacy_db, 1)
    assert removed == 3

    remaining = legacy_db.execute(
        text("SELECT id FROM code_bundles WHERE legacy_id = '100'")
    ).scalars().all()
    assert remaining == [keep]
    # Items of the duplicates were removed; the survivor keeps its own.
    item_bundles = legacy_db.execute(text("SELECT DISTINCT bundle_id FROM code_bundle_items")).scalars().all()
    assert item_bundles == [keep]

    # Idempotent: a second pass removes nothing.
    assert dedupe(legacy_db, 1) == 0


def test_dedupe_dry_run_does_not_delete(legacy_db):
    _seed_dupes(legacy_db, 1, "200", 3)
    assert dedupe(legacy_db, 1, dry_run=True) == 2
    assert legacy_db.execute(
        text("SELECT COUNT(*) FROM code_bundles WHERE legacy_id = '200'")
    ).scalar_one() == 3


def test_unique_constraint_blocks_duplicate_legacy_id(db_session):
    db_session.add(CodeBundle(tenant_id=db_session._tenant_id, legacy_id="300", name="First"))
    db_session.commit()
    db_session.add(CodeBundle(tenant_id=db_session._tenant_id, legacy_id="300", name="Dup"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_null_legacy_id_bundles_are_exempt(db_session):
    # API-created bundles (no legacy_id) must coexist freely.
    db_session.add_all([
        CodeBundle(tenant_id=db_session._tenant_id, legacy_id=None, name="API One"),
        CodeBundle(tenant_id=db_session._tenant_id, legacy_id=None, name="API Two"),
    ])
    db_session.commit()
    assert db_session.query(CodeBundle).filter(CodeBundle.legacy_id.is_(None)).count() == 2
