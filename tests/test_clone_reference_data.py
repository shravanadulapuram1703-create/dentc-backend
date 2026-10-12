"""scripts/clone_reference_data — onboarding a client into a separate database."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401  (register every table)
from app.db.base import Base
from app.db.models import (
    ChartMaterial,
    FeeSchedule,
    FeeScheduleEntry,
    IcdCode,
    LetterTemplate,
    NoteMacro,
    Permission,
    PrescriptionLibrary,
    ProcedureCode,
    Tenant,
)
from scripts.clone_reference_data import clone


@pytest.fixture()
def dbs(tmp_path):
    src = create_engine(f"sqlite:///{tmp_path / 'src.db'}")
    dst = create_engine(f"sqlite:///{tmp_path / 'dst.db'}")
    Base.metadata.create_all(src)
    Base.metadata.create_all(dst)

    with Session(src) as s:
        s.add_all([Tenant(id=1, name="Source", code="src"), Tenant(id=2, name="Other", code="oth")])
        s.flush()
        s.add(ChartMaterial(id=50, tenant_id=1, name="Amalgam"))
        s.add_all([
            ProcedureCode(code="D0120", description="Periodic eval", category="Diagnostic", default_material_id=50),
            ProcedureCode(code="D1110", description="Prophy", category="Preventive"),
        ])
        s.add(Permission(code="patients_view", label="View"))
        s.add(IcdCode(code="K02.9", description="Caries"))
        # Child inserted before its parent, so the remap must take two passes.
        s.add(FeeSchedule(id=10, tenant_id=1, name="UCR 2026", parent_schedule_id=11, office_id=None))
        s.add(FeeSchedule(id=11, tenant_id=1, name="UCR 2025"))
        s.add(FeeSchedule(id=12, tenant_id=1, name="Retired", is_active=False))
        s.add(FeeSchedule(id=13, tenant_id=2, name="Other tenant"))
        s.flush()
        s.add_all([
            FeeScheduleEntry(tenant_id=1, fee_schedule_id=10, procedure_code="D0120", patient_fee=Decimal("60")),
            FeeScheduleEntry(tenant_id=1, fee_schedule_id=10, procedure_code="D1110", patient_fee=Decimal("95")),
            FeeScheduleEntry(tenant_id=1, fee_schedule_id=11, procedure_code="D1110", patient_fee=Decimal("90")),
            FeeScheduleEntry(tenant_id=2, fee_schedule_id=13, procedure_code="D1110", patient_fee=Decimal("1")),
        ])
        s.add(LetterTemplate(tenant_id=1, name="Welcome", body_html="<p>Hi</p>"))
        s.add(NoteMacro(tenant_id=1, legacy_id="7", name="Prophy note", content="..."))
        s.add(PrescriptionLibrary(tenant_id=1, legacy_id="3", drug_name="Amoxicillin"))
        s.commit()

    with Session(dst) as d:
        d.add(Tenant(id=1, name="New client", code="new"))
        d.add(ProcedureCode(code="D1110", description="Target's own wording", category="Preventive"))
        d.commit()
    return src, dst


def _run(src, dst, **kw):
    with src.connect() as s, dst.connect() as d, d.begin():
        return clone(s, d, 1, 1, **kw)


def test_clone_copies_reference_data(dbs):
    src, dst = dbs
    counts = _run(src, dst)

    assert counts["procedure_codes"] == 1  # D1110 already existed
    assert counts["fee_schedules"] == 3  # tenant 2's schedule stays behind
    assert counts["fee_schedule_entries"] == 3

    with Session(dst) as d:
        # Global rows: insert-missing only, tenant pointers NULLed.
        assert d.get(ProcedureCode, "D1110").description == "Target's own wording"
        assert d.get(ProcedureCode, "D0120").default_material_id is None
        assert d.scalar(select(func.count()).select_from(Permission)) == 1
        assert d.scalar(select(func.count()).select_from(IcdCode)) == 1

        by_name = {f.name: f for f in d.scalars(select(FeeSchedule))}
        assert by_name["UCR 2026"].parent_schedule_id == by_name["UCR 2025"].id
        assert all(f.tenant_id == 1 for f in by_name.values())

        fees = {
            (e.fee_schedule_id, e.procedure_code): e.patient_fee
            for e in d.scalars(select(FeeScheduleEntry))
        }
        assert fees[(by_name["UCR 2026"].id, "D1110")] == Decimal("95")
        assert fees[(by_name["UCR 2025"].id, "D1110")] == Decimal("90")

        assert d.scalar(select(LetterTemplate.name)) == "Welcome"
        assert d.scalar(select(NoteMacro.legacy_id)) == "7"
        assert d.scalar(select(PrescriptionLibrary.drug_name)) == "Amoxicillin"


def test_active_only_skips_inactive_schedules(dbs):
    src, dst = dbs
    assert _run(src, dst, active_only=True)["fee_schedules"] == 2


def test_rerun_refuses_then_skip_existing_copies_nothing(dbs):
    src, dst = dbs
    _run(src, dst)
    with pytest.raises(SystemExit, match="already has rows"):
        _run(src, dst)

    counts = _run(src, dst, skip_existing=True)
    assert counts["fee_schedules"] == 0
    assert counts["procedure_codes"] == 0
    with Session(dst) as d:
        assert d.scalar(select(func.count()).select_from(FeeSchedule)) == 3


def test_missing_target_tenant_is_refused(dbs):
    src, dst = dbs
    with src.connect() as s, dst.connect() as d, d.begin():
        with pytest.raises(SystemExit, match="does not exist"):
            clone(s, d, 1, 99)
