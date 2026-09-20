"""Server-side office scoping (OFF-SCOPE-1/2/3/4/8).

The design the frontend implements (``docs/office-scope/office_scope_backend_devreport.md``):

    Office = the user's working context, not a fence. **Tenant is the security
    boundary.** The selected office is the default read filter for operational
    day-data, the write stamp for point-of-service records, and the selector for
    office-owned setup. Patients, the chart, the ledger, catalogs, users and
    Setup stay organisation-wide.

Everything the switcher does client-side (grouping, defaults, "This / My / All
offices") is workflow convenience. What is a *server* concern is anything a
client could bypass by editing a query string — the two things this module
enforces:

* **OFF-SCOPE-1** — a caller may not target an office they are not assigned to.
  An explicit ``?office_id=``/``?home_office_id=``, an ``office_ids[]``, an
  ``X-Office-ID`` header, or an ``/offices/{id}/*`` path is **403
  ``office_not_assigned``** unless the office is in the caller's ``user_offices``
  or the caller holds the master office right ``office_scope_view_all_offices``
  (or the legacy coverage alias ``appointments_add_appointment_in_other_office``).
* **OFF-SCOPE-2** — an operational day-data list with no office target narrows to
  the caller's assigned offices; ``all_offices=true`` is tenant-wide and needs
  ``office_scope_view_all_offices``.

Two deliberate escape hatches keep this from locking anyone out on deploy day,
mirroring ``permission_service``'s "a user in no group is ungated" rule:

* a caller holding a view-all right is never narrowed and never blocked;
* a caller with **zero** ``user_offices`` rows is *ungated* — treated as
  tenant-wide — because a migrated tenant whose assignments have not been seeded
  yet must not lose access to its own data (the report's data-hygiene note is
  that every real user should have ``user_offices`` rows; until then, ungated).

A patient-scoped list (one carrying a ``patient_id`` filter) is **never**
office-narrowed: the chart and the ledger are organisation-wide by the decision
above, so a front-desk user opening a chart sees every office's procedures on
it. An explicit office filter the caller *asked* for is still honoured (and
validated) on such a list.

The whole thing is gated by ``settings.OFFICE_SCOPE_ENFORCED`` (default True) so
operations keep a kill switch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, TenantId
from app.core import audit_context
from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.core.logging import office_id_ctx, user_id_ctx
from app.crud.base import CRUDBase
from app.db.models import Office, User, UserOffice
from app.services import permission_service


class OfficeCRUD(CRUDBase[Office]):
    """OFF-SCOPE-8: ``GET /offices?assigned_to_me=true`` narrows the office list
    to the caller's ``user_offices``. Opt-in only — the default list stays
    tenant-wide because it is the label table the badges resolve against. The
    caller is read from the office scope the list route injects (``list_scope_only``
    keeps the generic office narrowing off — offices are never fenced off)."""

    custom_filter_fields = ("assigned_to_me",)

    def _extra_list_clauses(self, filters: dict) -> list:
        value = filters.get("assigned_to_me")
        if not value or str(value).strip().lower() in ("false", "0", "no"):
            return []
        scope = filters.get("__office_scope")
        uid = scope.user.id if scope is not None else None
        if uid is None:
            raw = user_id_ctx.get()
            uid = int(raw) if raw and raw != "-" else None
        if uid is None:
            return []
        sub = select(UserOffice.office_id).where(UserOffice.user_id == uid)
        return [Office.id.in_(sub)]


def assigned_office_ids(db: Session, user_id: int, tenant_id: int) -> set[int]:
    """The office ids the user is assigned to (``user_offices``), narrowed to the
    active tenant so a cross-tenant target header can never widen the set."""
    rows = db.execute(
        select(UserOffice.office_id)
        .join(Office, Office.id == UserOffice.office_id)
        .where(UserOffice.user_id == user_id, Office.tenant_id == tenant_id)
    ).scalars().all()
    return {int(o) for o in rows}


def office_group_office_ids(db: Session, tenant_id: int, group_id: int) -> set[int]:
    """The offices belonging to an office group (OFF-SCOPE-8 regional mode)."""
    rows = db.execute(
        select(Office.id).where(
            Office.tenant_id == tenant_id, Office.office_group_id == group_id
        )
    ).scalars().all()
    return {int(o) for o in rows}


@dataclass
class OfficeScope:
    """Resolved office context for one request."""

    user: User
    tenant_id: int
    #: Validated working office from ``X-Office-ID`` (already checked against
    #: assignments); ``None`` when the header is absent.
    x_office_id: int | None = None
    #: List query params (only meaningful on a list route).
    all_offices: bool = False
    office_ids_param: list[int] | None = None
    office_group_id: int | None = None
    include_global_param: bool | None = None
    _db: Session | None = None
    _assigned: set[int] | None = None
    _rights: set[str] | None = None

    @property
    def rights(self) -> set[str]:
        # Lazy: the group-rights lookup is skipped entirely on a write that
        # carries no office context and no office-scoped resource.
        if self._rights is None:
            self._rights = permission_service.office_rights(self._db, self.user)
        return self._rights

    def can_view_all(self) -> bool:
        return (
            permission_service.OFFICES_VIEW_ALL in self.rights
            or permission_service.OFFICES_SWITCH_ANY in self.rights
        )

    @property
    def assigned_ids(self) -> set[int]:
        if self._assigned is None:
            self._assigned = assigned_office_ids(self._db, self.user.id, self.tenant_id)
        return self._assigned

    def is_ungated(self) -> bool:
        """No ``user_offices`` at all → tenant-wide (migration safety valve)."""
        return not self.assigned_ids

    def unrestricted(self) -> bool:
        """This caller is never narrowed and never office-blocked."""
        return (
            not settings.OFFICE_SCOPE_ENFORCED
            or self.can_view_all()
            or self.is_ungated()
        )


@dataclass(frozen=True)
class OfficeScopeSpec:
    """Declares that a CRUD resource participates in office scoping (registry).

    ``field`` is the office column on the model. ``kind`` decides the
    ``include_global`` default (catalogs include office_id IS NULL rows, day-data
    does not). ``require_on_create`` is OFF-SCOPE-11 (a point-of-service create
    must carry an office). ``patient_filter`` names the list filter that marks a
    read as patient-scoped — a chart/ledger read, which is organisation-wide and
    therefore never office-narrowed.
    """

    field: str = "office_id"
    kind: str = "day_data"  # "day_data" | "catalog"
    require_on_create: bool = False
    patient_filter: str = "patient_id"
    #: OFF-SCOPE-11: an extra column stamped with the *posting* office (the
    #: caller's working office), distinct from ``field`` (the operational office).
    #: ``patient_payments.created_office_id`` is the one case.
    created_office_field: str | None = None
    #: When False the default (no explicit target) case is NOT narrowed to the
    #: caller's assigned offices — the resource stays organisation-wide unless the
    #: caller opts into an office/group/all filter. Patients set this (the chart
    #: is org-wide; patient search defaults to All offices), while still getting
    #: OFF-SCOPE-1 validation of an explicit ``home_office_id`` and the
    #: office_ids/all_offices controls.
    default_narrow: bool = True
    #: OFF-SCOPE-6: enforce per-record visibility on GET (a caller without
    #: ``patients:view_cross_office`` may open a chart only if its home office is
    #: one of theirs, or the patient was seen at one of theirs). Patients only.
    enforce_patient_visibility: bool = False
    #: When True the list route resolves the office scope (validates X-Office-ID,
    #: injects ``__office_scope`` for the crud_class) but applies **no** generic
    #: office narrowing. The offices label table uses this — it is never fenced
    #: off, but ``OfficeCRUD`` still needs the caller for ``assigned_to_me``.
    list_scope_only: bool = False


@dataclass
class OfficeListFilter:
    """The office restriction the CRUD list applies. ``office_ids=None`` means
    'no restriction' (tenant-wide)."""

    column: str
    office_ids: list[int] | None
    include_null: bool = False


def _office_not_assigned(office_id: int, field: str, assigned: set[int]) -> ForbiddenError:
    return ForbiddenError(
        f"Office '{office_id}' is not assigned to you",
        code="office_not_assigned",
        details={
            "office_id": office_id,
            "field": field,
            "assigned_office_ids": sorted(assigned),
        },
    )


def validate_target_office(
    scope: OfficeScope, office_id: int | None, *, field: str = "office_id"
) -> None:
    """OFF-SCOPE-1: 403 ``office_not_assigned`` when the caller targets an office
    outside their assignments (unless privileged / ungated / enforcement off)."""
    if office_id is None or scope.unrestricted():
        return
    if int(office_id) in scope.assigned_ids:
        return
    raise _office_not_assigned(int(office_id), field, scope.assigned_ids)


def assert_office_path_access(db: Session, user: User, tenant_id: int, office_id: int) -> None:
    """OFF-SCOPE-1 for ``/offices/{office_id}/*`` routes: 403 ``office_not_assigned``
    when the caller targets an office they are not assigned to (privileged /
    ungated callers pass; enforcement off is a no-op)."""
    scope = OfficeScope(user=user, tenant_id=tenant_id, _db=db)
    validate_target_office(scope, office_id, field="office_id")


def require_all_offices(scope: OfficeScope, *, reports: bool = False) -> None:
    """OFF-SCOPE-2/8: ``all_offices=true`` needs ``offices:view_all`` (or, on the
    report routes, ``reports:all_offices``). Ungated callers are allowed."""
    if not settings.OFFICE_SCOPE_ENFORCED or scope.is_ungated():
        return
    if scope.can_view_all():
        return
    if reports and permission_service.REPORTS_ALL_OFFICES in scope.rights:
        return
    raise ForbiddenError(
        "You do not have permission to read across all offices",
        code="office_not_assigned",
        # The catalog collapses view-all / all-office-reports into one master
        # code, so the list is de-duplicated (dict.fromkeys preserves order).
        details={
            "required_any_of": list(dict.fromkeys(
                [permission_service.OFFICES_VIEW_ALL, permission_service.REPORTS_ALL_OFFICES]
                if reports
                else [permission_service.OFFICES_VIEW_ALL]
            ))
        },
    )


def resolve_list_office_filter(
    scope: OfficeScope,
    *,
    column: str,
    kind: str,
    explicit_value: int | None,
    patient_scoped: bool = False,
    reports: bool = False,
    default_narrow: bool = True,
) -> OfficeListFilter:
    """Compute the office restriction for a list request (OFF-SCOPE-2/4/8).

    Precedence: an explicit single-office filter → ``office_ids[]`` →
    ``office_group_id`` → ``all_offices`` → the default (assigned offices, unless
    the list is patient-scoped or the caller is unrestricted).
    """
    include_null = (
        scope.include_global_param
        if scope.include_global_param is not None
        else (kind == "catalog")
    )

    # 1) An explicit single-office filter the caller asked for (always validated).
    if explicit_value is not None:
        validate_target_office(scope, explicit_value, field=column)
        return OfficeListFilter(column, [int(explicit_value)], include_null)

    # 2) office_ids[] — validate each.
    if scope.office_ids_param:
        for oid in scope.office_ids_param:
            validate_target_office(scope, oid, field="office_ids")
        return OfficeListFilter(column, [int(o) for o in scope.office_ids_param], include_null)

    # 3) office_group_id — resolve to its offices; a non-privileged caller is
    #    restricted to the intersection with their assignments.
    if scope.office_group_id is not None:
        ids = office_group_office_ids(scope._db, scope.tenant_id, scope.office_group_id)
        if not scope.unrestricted():
            ids = ids & scope.assigned_ids
        return OfficeListFilter(column, sorted(ids), include_null)

    # 4) all_offices=true — tenant-wide, but permission-gated.
    if scope.all_offices:
        require_all_offices(scope, reports=reports)
        return OfficeListFilter(column, None, include_null)

    # 5) default. Chart/ledger reads (patient-scoped), org-wide resources
    #    (``default_narrow=False``, e.g. patients) and unrestricted callers are
    #    never narrowed; everyone else defaults to their assigned offices.
    if patient_scoped or not default_narrow or scope.unrestricted():
        return OfficeListFilter(column, None, include_null)
    return OfficeListFilter(column, sorted(scope.assigned_ids), include_null)


def patient_is_visible(scope: OfficeScope, patient) -> bool:  # noqa: ANN001
    """OFF-SCOPE-6: True when the caller may open this chart.

    A caller holding ``patients:view_cross_office`` (or unrestricted / with
    enforcement off) sees every chart. Otherwise the chart is visible when its
    home office is one of the caller's, or the patient was seen (an appointment
    or a posted procedure) at one of the caller's offices.
    """
    if (
        not settings.OFFICE_SCOPE_ENFORCED
        or scope.is_ungated()
        or permission_service.PATIENTS_VIEW_CROSS_OFFICE in scope.rights
        or scope.can_view_all()
    ):
        return True
    assigned = scope.assigned_ids
    if getattr(patient, "home_office_id", None) in assigned:
        return True
    # Seen at an assigned office? (a lightweight EXISTS across appointments +
    # procedures; only reached for a non-privileged caller opening a chart whose
    # home office is not theirs.)
    from app.db.models import Appointment, PatientProcedure

    db = scope._db
    seen = db.execute(
        select(Appointment.id)
        .where(Appointment.patient_id == patient.id, Appointment.office_id.in_(assigned))
        .limit(1)
    ).first()
    if seen is not None:
        return True
    seen = db.execute(
        select(PatientProcedure.id)
        .where(PatientProcedure.patient_id == patient.id, PatientProcedure.office_id.in_(assigned))
        .limit(1)
    ).first()
    return seen is not None


def assert_patient_visible(scope: OfficeScope, patient) -> None:  # noqa: ANN001
    if not patient_is_visible(scope, patient):
        raise ForbiddenError(
            "You do not have access to this patient's chart from your offices",
            code="patient_not_in_office",
            details={
                "patient_id": getattr(patient, "id", None),
                "home_office_id": getattr(patient, "home_office_id", None),
                "required_any_of": [permission_service.PATIENTS_VIEW_CROSS_OFFICE],
            },
        )


def apply_write_office(
    scope: OfficeScope, data: dict, spec: OfficeScopeSpec
) -> int | None:
    """OFF-SCOPE-1/3/11 write path, mutating ``data`` in place:

    * a body-supplied office is validated against the caller's assignments;
    * when the body omits it, the caller's validated ``X-Office-ID`` working
      office is stamped as the default (never overriding an explicit value);
    * a ``created_office_field`` (the posting office) is stamped from the working
      office regardless of the operational office in the body.

    Returns the resolved operational office (for the require-on-create check).
    """
    field = spec.field
    value = data.get(field)
    if value is not None:
        validate_target_office(scope, value, field=field)
    elif scope.x_office_id is not None:
        data[field] = scope.x_office_id
        value = scope.x_office_id
    if spec.created_office_field and scope.x_office_id is not None:
        data.setdefault(spec.created_office_field, scope.x_office_id)
    return value


# ── dependencies ─────────────────────────────────────────────────────────────
def get_office_context(
    db: DbSession,
    current: CurrentUser,
    tenant_id: TenantId,
    x_office_id: Annotated[
        int | None,
        Header(alias="X-Office-ID", description="OFF-SCOPE-3: the caller's working office"),
    ] = None,
) -> OfficeScope:
    """Resolve the caller's office rights + validated working office. Used by
    every write route (create/update) and any handler that needs the context."""
    scope = OfficeScope(user=current, tenant_id=tenant_id, _db=db)
    if x_office_id is not None:
        validate_target_office(scope, x_office_id, field="X-Office-ID")
        scope.x_office_id = int(x_office_id)
        # Record the working office for the audit trail (OFF-SCOPE-17) and logs.
        office_id_ctx.set(int(x_office_id))
        audit_context.record(office_id=int(x_office_id))
    return scope


OfficeContext = Annotated[OfficeScope, Depends(get_office_context)]


def get_office_scope(
    scope: OfficeContext,
    all_offices: Annotated[
        bool,
        Query(description="OFF-SCOPE-2: read across all offices (needs office_scope_view_all_offices)"),
    ] = False,
    office_ids: Annotated[
        list[int] | None,
        Query(description="OFF-SCOPE-8: restrict to these offices (repeatable)"),
    ] = None,
    office_group_id: Annotated[
        int | None, Query(description="OFF-SCOPE-8: restrict to an office group")
    ] = None,
    include_global: Annotated[
        bool | None,
        Query(
            description="OFF-SCOPE-4: include office_id IS NULL (global) rows "
            "(default: true for catalogs, false for day-data)"
        ),
    ] = None,
) -> OfficeScope:
    """The full list-route office scope: :func:`get_office_context` plus the
    OFF-SCOPE-2/4/8 list query parameters."""
    scope.all_offices = all_offices
    scope.office_ids_param = office_ids
    scope.office_group_id = office_group_id
    scope.include_global_param = include_global
    return scope


OfficeScopeDep = Annotated[OfficeScope, Depends(get_office_scope)]
