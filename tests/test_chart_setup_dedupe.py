"""Charting Setup data-note fixes (Restorative Materials / Colors).

1. ``chart_materials.pattern`` was migrated as a GIF filename (``hash.gif``); the
   renderer keys on the bare name (``hash``). The backfill normalizes it.
2. Like code_bundles, chart_materials / chart_colors had no unique key, so importer
   re-runs produced duplicate rows. Dedupe collapses each (tenant_id, legacy_id) group
   to the lowest id (repointing chart_materials FKs first); the model now carries a
   unique constraint so it cannot recur. NULL legacy_id is exempt.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import ChartColor, ChartMaterial
from scripts.backfill_chart_material_patterns import backfill, normalize_pattern
from scripts.dedupe_chart_setup import dedupe_chart_colors, dedupe_chart_materials


# ── Pattern normalization (CHART-3e) ─────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("hash.gif", "hash"),
    ("ROUND.GIF", "round"),
    ("arestin.gif", "arestin"),
    ("crosshash.gif", "crosshash"),
    ("hash", "hash"),      # already bare → unchanged
    ("", ""),
    (None, None),          # NULL (e.g. "Unknown") left alone
])
def test_normalize_pattern(raw, expected):
    assert normalize_pattern(raw) == expected


# ── Dedupe (CHART-3f) ────────────────────────────────────────────────────────

@pytest.fixture
def legacy_db():
    """Isolated session whose chart tables predate the unique constraint, plus the
    chart_materials FK tables (minimal columns) so repointing can be exercised."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE chart_materials (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "tenant_id INTEGER, legacy_id VARCHAR, name VARCHAR, pattern VARCHAR, "
                       "color VARCHAR, created_at VARCHAR, updated_at VARCHAR, updated_by INTEGER)"))
        c.execute(text("CREATE TABLE chart_colors (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "tenant_id INTEGER, legacy_id VARCHAR)"))
        # chart_conditions now carries updated_at (TimestampMixin) — the material_id
        # repoint is an ORM update, so SQLAlchemy auto-sets the onupdate column.
        c.execute(text("CREATE TABLE chart_conditions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "material_id INTEGER, updated_at VARCHAR)"))
        # patient_procedures gained updated_at too (AL-13) — same reason as
        # chart_conditions above: the repoint is an ORM update, so the onupdate
        # column has to exist on the simulated legacy table.
        c.execute(text("CREATE TABLE patient_procedures (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "material_id INTEGER, updated_at VARCHAR)"))
        c.execute(text("CREATE TABLE appointment_procedures ("
                       "id INTEGER PRIMARY KEY AUTOINCREMENT, material_id INTEGER)"))
        c.execute(text("CREATE TABLE procedure_codes (code VARCHAR PRIMARY KEY, default_material_id INTEGER)"))
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()


def _seed(db, table, tenant_id, legacy_id, n) -> list[int]:
    ids = []
    for _ in range(n):
        r = db.execute(
            text(f"INSERT INTO {table} (tenant_id, legacy_id) VALUES (:t, :l)"),
            {"t": tenant_id, "l": legacy_id},
        )
        ids.append(int(r.lastrowid))
    db.commit()
    return ids


def test_materials_dedupe_repoints_fks_and_is_idempotent(legacy_db):
    ids = _seed(legacy_db, "chart_materials", 1, "1", 4)
    keep, dupe = min(ids), max(ids)
    # An FK row pointing at a duplicate (non-survivor) material.
    legacy_db.execute(text("INSERT INTO patient_procedures (material_id) VALUES (:m)"), {"m": dupe})
    legacy_db.execute(text("INSERT INTO procedure_codes (code, default_material_id) VALUES ('D0120', :m)"), {"m": dupe})
    legacy_db.commit()

    assert dedupe_chart_materials(legacy_db, 1) == 3
    remaining = legacy_db.execute(text("SELECT id FROM chart_materials")).scalars().all()
    assert remaining == [keep]
    # FK references were repointed to the survivor, not orphaned.
    assert legacy_db.execute(text("SELECT material_id FROM patient_procedures")).scalar_one() == keep
    assert legacy_db.execute(text("SELECT default_material_id FROM procedure_codes")).scalar_one() == keep
    # Idempotent.
    assert dedupe_chart_materials(legacy_db, 1) == 0


def test_colors_dedupe_and_dry_run(legacy_db):
    _seed(legacy_db, "chart_colors", 1, "1", 5)
    assert dedupe_chart_colors(legacy_db, 1, dry_run=True) == 4
    assert legacy_db.execute(text("SELECT COUNT(*) FROM chart_colors")).scalar_one() == 5
    assert dedupe_chart_colors(legacy_db, 1) == 4
    assert legacy_db.execute(text("SELECT COUNT(*) FROM chart_colors")).scalar_one() == 1


def test_backfill_normalizes_existing_patterns(legacy_db):
    legacy_db.execute(text("INSERT INTO chart_materials (tenant_id, legacy_id, pattern) "
                           "VALUES (1,'1','hash.gif'),(1,'2','round.gif'),(1,'3',NULL)"))
    legacy_db.commit()
    assert backfill(legacy_db, 1) == 2  # NULL untouched
    pats = legacy_db.execute(text("SELECT pattern FROM chart_materials ORDER BY legacy_id")).scalars().all()
    assert pats == ["hash", "round", None]


# ── Unique constraint (against the real, migrated schema) ─────────────────────

def test_unique_constraint_blocks_duplicate_legacy_id(db_session):
    db_session.add(ChartMaterial(tenant_id=db_session._tenant_id, legacy_id="9", name="First"))
    db_session.commit()
    db_session.add(ChartMaterial(tenant_id=db_session._tenant_id, legacy_id="9", name="Dup"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_null_legacy_id_is_exempt(db_session):
    db_session.add_all([
        ChartColor(tenant_id=db_session._tenant_id, legacy_id=None, name="API One"),
        ChartColor(tenant_id=db_session._tenant_id, legacy_id=None, name="API Two"),
    ])
    db_session.commit()
    assert db_session.query(ChartColor).filter(ChartColor.legacy_id.is_(None)).count() == 2
