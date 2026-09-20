"""Procedure codes, fee schedules, code bundles, and clinical reference data.

procedure_codes · fee_schedules · fee_schedule_entries · code_bundles ·
code_bundle_items · chart_materials · note_macros · prescription_library
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntPKMixin, TimestampMixin


class ProcedureCode(Base, CreatedAtMixin):
    __tablename__ = "procedure_codes"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    legacy_code: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(100), index=True)
    # FEE-1: the *insurance* coverage category this code bands into
    # ("01A", "03", "11B", …). ``category`` above is a display label; the
    # coverage percentages in ``insurance_coverage_rules`` are keyed on these
    # legacy category codes, so without this column no ADA code could ever match
    # a band and every estimate came back at 0 % coverage. Seeded from the CDT
    # family ranges by ``scripts/seed_coverage_categories.py``; a stored value
    # always beats the derived one, so a practice override survives a re-seed.
    coverage_category: Mapped[str | None] = mapped_column(String(20), index=True)
    default_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    default_duration_minutes: Mapped[int | None]
    requires_tooth: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_surface: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_quadrant: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_lab: Mapped[bool] = mapped_column(Boolean, default=False)
    # ── PROC-7: supporting-records requirements (Charting tab, "Supporting
    # Records Required"). Same shape and scope as requires_tooth — a tenant-wide
    # attribute of the code, default false, independent on/off flags. Unlike the
    # tooth/surface/quadrant flags these are *advisory* on posting (the record
    # can be captured after the chair) and enforced at claim submission; the
    # definition of "satisfied" lives in supporting_records_service.
    requires_attachment: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_perio_chart: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_xray: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_missing_tooth_info: Mapped[bool] = mapped_column(Boolean, default=False)
    is_ortho: Mapped[bool] = mapped_column(Boolean, default=False)
    billing_order: Mapped[str | None] = mapped_column(String(10))
    recall_interval: Mapped[int | None]
    recall_unit: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ── PROC-1: detailed charting config (legacy Charting tab) ───────────────
    chart_category: Mapped[str | None] = mapped_column(String(100))
    tooth_area: Mapped[str | None] = mapped_column(String(50))
    draw_as: Mapped[str | None] = mapped_column(String(50))
    min_surfaces: Mapped[int | None]
    max_surfaces: Mapped[int | None]
    default_material_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("chart_materials.id"))
    valid_teeth: Mapped[list | None] = mapped_column(JSON)  # e.g. ["1","2",…,"32"]
    # ── CHG-2: structured tooth/surface/material enforcement rules ─────────────
    # The ToothSurfaceEnforcement modal needs structured rules (allowed quadrants,
    # surface min/max + allowed surfaces, material options) per CDT code instead of
    # fabricating them client-side from the flat requires_* booleans. Each is a JSON
    # object, e.g. anatomy_rules={"mode":"tooth","allowed_quadrants":["UR","UL"]},
    # surface_rules={"min":1,"max":5,"allowed":["M","O","D","B","L"]},
    # material_rules={"options":[{"id":3,"name":"Composite"}]}.
    anatomy_rules: Mapped[dict | None] = mapped_column(JSON)
    surface_rules: Mapped[dict | None] = mapped_column(JSON)
    material_rules: Mapped[dict | None] = mapped_column(JSON)
    # ── PROC-4: legacy "Main" booleans/codes (Provider Settings) ─────────────
    taxable: Mapped[bool] = mapped_column(Boolean, default=False)
    sales_tax_code: Mapped[str | None] = mapped_column(String(50))
    visit_code: Mapped[str | None] = mapped_column(String(50))
    ledger_code: Mapped[str | None] = mapped_column(String(50))
    ar_code: Mapped[str | None] = mapped_column(String(50))
    is_post_op: Mapped[bool] = mapped_column(Boolean, default=False)
    exempt_from_dental_max: Mapped[bool] = mapped_column(Boolean, default=False)
    # ── REST-8: alternate-maximum-benefit ("A code") downgrade metadata ───────
    amb_code: Mapped[str | None] = mapped_column(String(20))  # the alternate-benefit downgrade code
    is_downgrade: Mapped[bool] = mapped_column(Boolean, default=False)  # true for AMB codes
    alternate_of: Mapped[str | None] = mapped_column(String(20))  # the code this one downgrades
    lock_default_provider: Mapped[bool] = mapped_column(Boolean, default=False)
    default_provider_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("providers.id"))
    default_notes_macro_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("note_macros.id"))
    show_ada_code_in_notes: Mapped[bool] = mapped_column(Boolean, default=False)
    nhs_treatment_category: Mapped[str | None] = mapped_column(String(100))
    nhs_clinical_data_set: Mapped[str | None] = mapped_column(String(100))


class FeeSchedule(Base, IntPKMixin, CreatedAtMixin):
    """One price list. ``fee_schedule_entries`` holds its per-code amounts.

    ``fee_type`` and ``pricing_model`` are the two orthogonal questions the legacy
    screen conflated into one free-text box (see
    :mod:`app.services.fee_vocab` for the vocabulary and the evidence):

    * ``fee_type`` — *how this list gets bound* (Denticon ``FeeScheH.FEETYPE``):
      an office's UCR list, a practice/patient list, or one assigned to a plan or
      a carrier. It is **advisory**: it drives picker filters and labels, not
      which pointer may reference the list. One list is legitimately both an
      office's UCR list and the list its patients are registered on.
    * ``pricing_model`` — *how the payer pays*: ``percentage`` (the plan's
      coverage % splits this allowed amount) or ``copay`` (the list states both
      dollar parts, so ``insurance_fee`` is the plan's share). Only a plan- or
      carrier-bound list may be ``copay``, because a copay list must be reached
      through a payer tier; the CHECK lives in Alembic ``d4f1a9c7b3e2`` and
      ``FeeScheduleCRUD`` carries the same rule (SQLite has no CHECK here).

    ``ins_plan_id`` / ``office_id`` are **deprecated** (Denticon leaves both empty
    on all 36 exported headers, and they were NULL on every row here): binding is
    expressed once, in ``fee_schedule_assignments`` plus the office and patient
    pointers. They are excluded from the write schemas and read by nothing; they
    are dropped one release after the backfill proves them unused.
    """

    __tablename__ = "fee_schedules"
    __table_args__ = (
        # ``legacy_id`` was globally unique, so two tenants migrating the same
        # Denticon FEEID collided at the database level. Scope it per tenant, like
        # chart_materials / note_macros / prescription_library.
        UniqueConstraint("tenant_id", "legacy_id", name="uq_fee_schedules_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(255))
    #: ``fee_vocab.FEE_TYPE_CODES``; normalised on every write.
    fee_type: Mapped[str | None] = mapped_column(String(50), default="standard")
    #: ``fee_vocab.PRICING_MODEL_CODES``.
    pricing_model: Mapped[str] = mapped_column(
        String(12), default="percentage", server_default="percentage", nullable=False
    )
    # Deprecated — see the class docstring. Never read by the resolver.
    ins_plan_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("insurance_plans.id"))
    office_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("offices.id"))
    # FEE-4: schedule-level effective date + versioning lineage ("New Effective
    # Date"). Display/lineage only: the fee in force is decided by the *entry*
    # date (Denticon has no header date and re-stamps per-entry EFFECTIVEDATE),
    # so a new effective date is a dated bulk upsert into the same list rather
    # than a clone whose pointers must all be moved.
    effective_date: Mapped[date | None]
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_schedule_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("fee_schedules.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class FeeScheduleEntry(Base, IntPKMixin, TimestampMixin):
    """What one code costs on one price list, from one date.

    ``patient_fee`` is the amount charged. ``insurance_fee`` ("Plan Pays") is the
    fixed dollar amount the *plan* pays and is valid **only** on a
    ``pricing_model='copay'`` list (Denticon ``FeeScheD.INSAMT``, non-zero on 356
    of 13,488 legacy rows, 354 of them on the two assign-to-plan Medicaid lists
    where ``PATAMT`` is blank). It is never a percentage and never a second
    patient price; ``FeeScheduleEntryCRUD`` refuses it elsewhere.

    ``is_no_charge`` is how a genuinely free procedure is expressed. It has to be
    explicit because ``0.00`` cannot mean it: the migration parsed 3,866 blank
    ``PATAMT`` cells as ``0.00`` (619 on CP-50, 225 on CP-40), and those zeros were
    winning the resolver walk and posting $0 charges. The resolver treats
    ``patient_fee <= 0`` as *not priced* and keeps walking unless this is set.
    """

    __tablename__ = "fee_schedule_entries"
    __table_args__ = (
        # Two people loading the same list produced duplicate rows that
        # ``ORDER BY id DESC`` silently resolved. One price per code per date.
        UniqueConstraint(
            "fee_schedule_id", "procedure_code", "effective_date",
            name="uq_fee_schedule_entries_schedule_code_date",
        ),
    )

    # The table had no tenant column, and ``CRUDBase`` only scopes models that
    # carry one — so ``/fee-schedule-entries/{id}`` was readable *and writable*
    # across tenants. Denormalised from the owning schedule and enforced by
    # ``FeeScheduleEntryCRUD`` on every write.
    tenant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    fee_schedule_id: Mapped[int] = mapped_column(Integer, ForeignKey("fee_schedules.id"), index=True)
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"), index=True)
    # FEE-2: legacy "AMB Code" — the alternate-benefit code the carrier actually
    # pays on (``D2391A`` -> ``D2140``: posterior composite downgraded to amalgam).
    amb_code: Mapped[str | None] = mapped_column(String(20))
    patient_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    insurance_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    #: An explicitly free procedure, as opposed to an unpriced one.
    is_no_charge: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    #: The date this price takes effect. The entry in force on a charge's date of
    #: service is the latest one on or before it. **NOT NULL**: it is half of the
    #: uniqueness key, and Postgres treats NULLs as distinct, so a nullable column
    #: would leave the duplicate rows the constraint exists to prevent. An omitted
    #: value means "effective now" (all 13,493 migrated rows already carry a date).
    effective_date: Mapped[date] = mapped_column(
        Date, server_default=func.current_date(), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    #: "Modified By" — stamped by ``CRUDBase.update`` (``updated_at`` via the mixin),
    #: so "who changed D0120 from 44 to 46, and when" is answerable.
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ChartMaterial(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "chart_materials"
    # Same defect as code_bundles: no unique key meant the importer's
    # ``ON CONFLICT DO NOTHING`` was a no-op and re-runs produced duplicate rows
    # (4x per legacy_id). NULL legacy_id (API-created) is exempt — NULLs are distinct.
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_chart_materials_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    pattern: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(50))
    # CHART-3a/3b: TimestampMixin adds updated_at ("Modified On"); updated_by is the
    # editing actor ("Modified By"), auto-set by CRUDBase.update on every PATCH.
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class NoteMacro(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "note_macros"
    # NM-7: same migration-rerun duplication as prescription_library /
    # chart_materials (every legacy macro imported 4x). NULL legacy_id
    # (API-created) is exempt.
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_note_macros_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(100))
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    # NM-4: TimestampMixin adds updated_at ("Modified On"); updated_by is the editing
    # actor ("Modified By"), auto-set by CRUDBase.update on every PATCH.
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class CodeBundle(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "code_bundles"
    # Explosion Codes (referral/proc dev-report data note): a migrated bundle is
    # unique per (tenant, legacy_id). Without this the importer's ON CONFLICT was a
    # no-op and re-runs produced duplicate bundles. NULL legacy_id (API-created
    # bundles) is exempt — Postgres treats NULLs as distinct.
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_code_bundles_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    display_code: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(255))
    same_tooth: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class CodeBundleItem(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "code_bundle_items"

    bundle_id: Mapped[int] = mapped_column(Integer, ForeignKey("code_bundles.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    procedure_code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    tooth: Mapped[str | None] = mapped_column(String(10))
    # PROC-INT-9: aligned with explosion_code_items so a bundle can pre-fill the
    # ADD PROCEDURE DETAILS pop-up fully (surface + quadrant, not just tooth).
    surface: Mapped[str | None] = mapped_column(String(20))
    quadrant: Mapped[str | None] = mapped_column(String(10))
    sort_order: Mapped[int] = mapped_column(Integer, default=1)


class PrescriptionLibrary(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "prescription_library"
    # RX-4: same migration-rerun duplication as chart_materials / code_bundles
    # (every legacy drug imported 5x). NULL legacy_id (API-created) is exempt.
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_prescription_library_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    drug_name: Mapped[str] = mapped_column(String(255))
    dispense: Mapped[str | None] = mapped_column(String(255))
    sig: Mapped[str | None] = mapped_column(String(500))
    refills: Mapped[int] = mapped_column(Integer, default=0)
    is_as_written: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # MA-5: allergy keys this drug conflicts with (``["penicillin", "aspirin"]``),
    # matched against the patient's active YES medical alerts and free-text
    # patient alerts when a prescription is written. Keys are stored as
    # ``to_code`` slugs so they compare against ``alert_code`` directly.
    allergy_keys: Mapped[list | None] = mapped_column(JSON)
    # RX-1: "Modified By". updated_at already comes from TimestampMixin ("Modified
    # On"); updated_by is auto-set by CRUDBase.update on every PATCH, created_by
    # by CRUDBase.create. Both resolve to ``*_by_name`` on the read model
    # (attach_actor_names). Migrated rows keep NULL — the Denticon export carries
    # no author for the library.
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class ChartColor(Base, IntPKMixin, TimestampMixin):
    __tablename__ = "chart_colors"
    # Same migration-rerun duplication as chart_materials (5x per legacy_id).
    # NULL legacy_id (API-created) is exempt — Postgres treats NULLs as distinct.
    __table_args__ = (
        UniqueConstraint("tenant_id", "legacy_id", name="uq_chart_colors_tenant_legacy"),
    )

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    legacy_id: Mapped[str | None] = mapped_column(String(20))
    category_type: Mapped[int | None]
    name: Mapped[str] = mapped_column(String(100))
    stroke_color: Mapped[str | None] = mapped_column(String(50))
    fill_type: Mapped[str | None] = mapped_column(String(20))
    fill_color: Mapped[str | None] = mapped_column(String(50))
    fill_color2: Mapped[str | None] = mapped_column(String(50))
    fill_pattern: Mapped[str | None] = mapped_column(Text)
    gradient_angle: Mapped[str | None] = mapped_column(String(20))
    gradient_method: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[str | None] = mapped_column(String(100))
    # CHART-2a: editing actor ("Modified By"), auto-set by CRUDBase.update on PATCH.
    # (created_at/updated_at already provided by TimestampMixin.)
    updated_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))


class CodesView(Base, IntPKMixin, CreatedAtMixin):
    __tablename__ = "codes_view"

    tenant_id: Mapped[int] = mapped_column(Integer, ForeignKey("tenants.id"), index=True)
    office_id: Mapped[int] = mapped_column(Integer, ForeignKey("offices.id"), index=True)
    code: Mapped[str] = mapped_column(String(20), ForeignKey("procedure_codes.code"))
    created_by: Mapped[str | None] = mapped_column(String(100))
