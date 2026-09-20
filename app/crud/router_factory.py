"""Turn a model + schemas into a standard 5-route CRUD ``APIRouter``.

This is the OpenAPI/Orval-facing half of the CRUD engine. Each route gets an
explicit ``operation_id`` so the generated TypeScript hook names are clean and
stable (``listPatients``, ``createPatient``, …) and a single domain ``tag`` so
Orval's ``tags-split`` mode produces one file per domain.

NOTE: this module deliberately does NOT use ``from __future__ import annotations``.
The dynamic ``body: cfg.create_schema`` parameter annotation must evaluate to the
real Pydantic class at definition time so FastAPI can build the request model.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy import inspect as sa_inspect

from app.api.deps import DbSession, PageParams, TenantId, get_current_user, require_permission
from app.core import concurrency
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.crud.base import CRUDBase
from app.schemas.common import ErrorResponse, PaginatedResponse
from app.services.office_scope_service import (
    OfficeScopeDep,
    OfficeScopeSpec,
    apply_write_office,
    assert_patient_visible,
    get_office_context,
    resolve_list_office_filter,
    validate_target_office,
)


@dataclass(slots=True)
class CrudConfig:
    model: type
    create_schema: type
    update_schema: type
    read_schema: type
    prefix: str  # URL segment + default tag, e.g. "patients"
    tag: str
    singular: str  # snake, for operation ids, e.g. "patient"
    plural: str | None = None  # snake, defaults to prefix
    pk_type: type = int
    pk_name: str = "id"
    search_fields: tuple[str, ...] = ()
    sortable_fields: tuple[str, ...] = ()
    # INS-9: (fk_attr, related_model, related_search_fields) — extend search to a related name.
    search_relations: tuple[tuple[str, type, tuple[str, ...]], ...] = ()
    filter_fields: tuple[str, ...] = ()
    range_fields: tuple[str, ...] = ()  # emit {f}_from / {f}_to typed query params
    # INS-PT-7/14: declared query params that are NOT plain columns — a partial
    # match (``group_number_contains``), or a filter that has to reach a related
    # table (``carrier_name``). Each entry is ``(param_name, python_type)``; the
    # value is passed through to ``crud.list(filters=...)`` and resolved by the
    # crud_class in ``_extra_list_clauses``. Declaring it here is what makes it
    # visible in OpenAPI, so Orval generates a typed argument for it.
    extra_filters: tuple[tuple[str, type], ...] = ()
    # INS-PT-9/18: expose ``?ids=1,2,3`` on the list route. A plan grid resolves
    # up to 40 carrier/employer names per page; without this each one is its own
    # GET (plus a CORS preflight).
    id_in_param: bool = False
    default_sort: str = "created_at"
    soft_delete_field: str | None = "is_active"
    soft_delete_value: bool = False
    # PP-1: exclude soft-deleted rows from the default listing (an explicit
    # ``?{soft_delete_field}=`` filter still wins). Opt-in per resource.
    hide_soft_deleted: bool = False
    # Optional post-read hook ``(db, items, tenant_id) -> None`` that mutates the
    # returned ORM rows in place (e.g. attach resolved actor names). Applied to
    # list/get/create/update responses. Batch-resolve inside to avoid N+1.
    read_enrich: Optional[Callable[[Any, list, int], None]] = None
    # Optional CRUDBase subclass with overridden create/update/delete for entities
    # that need real business rules (e.g. progress-note lock + strike-off). Defaults
    # to the generic CRUDBase. Must accept the same constructor kwargs.
    crud_class: type[CRUDBase] = CRUDBase
    # EDIT-PLAN-5: permission codes (any of) a caller must hold to POST / PATCH /
    # DELETE this resource. Empty = role-only (the historical behaviour). Reads
    # are never gated here — a view-only user still lists the plans.
    write_permissions: tuple[str, ...] = ()
    # ACCESS-RIGHTS C1: permission codes (any of) required *specifically for
    # DELETE*, in addition to ``write_permissions``. Many resources gate deletion
    # on its own high-risk right (e.g. ``patient_delete_patient_information``)
    # while leaving create/update on the coarser role check. Empty = DELETE is
    # gated only by ``write_permissions`` (if any).
    delete_permissions: tuple[str, ...] = ()
    # RBAC-6: the same, per-verb, for POST and PATCH — a resource whose *creation*
    # (e.g. ``transactions_add_post_patient_payments``) or *edit* carries its own
    # right, layered on top of ``write_permissions``. Empty = that verb is gated
    # only by ``write_permissions`` (if any).
    create_permissions: tuple[str, ...] = ()
    update_permissions: tuple[str, ...] = ()
    # OFF-SCOPE-1/2/4/11: when set, this resource participates in office scoping —
    # list reads narrow to the caller's assigned offices (or an explicit target,
    # validated), and create/update validate + default-stamp the office. None =
    # no office scoping (the historical behaviour).
    office_scope: Optional[OfficeScopeSpec] = None


def _col_pytype(columns, name: str) -> type | None:  # noqa: ANN001
    col = columns.get(name)
    if col is None:
        return None
    try:
        return col.type.python_type
    except Exception:  # noqa: BLE001
        return str


def _parse_ids(raw, pk_type: type):  # noqa: ANN001
    """``"3,7, 9"`` -> ``[3, 7, 9]``. Unparseable entries are dropped rather than
    422'd: the batch lookup is a convenience over a name-resolution fan-out, and
    one bad id should not blank a whole grid page."""
    if raw is None:
        return None
    out = []
    for chunk in str(raw).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.append(pk_type(chunk))
        except (TypeError, ValueError):
            continue
    return out


def _make_list_endpoint(cfg: "CrudConfig", crud: CRUDBase, plural: str):
    """Build a list handler whose signature declares one typed, OpenAPI-visible
    ``Query`` param per filter field (+ ``{f}_from``/``{f}_to`` per range field),
    so Orval generates typed filter arguments. Values are FastAPI-coerced."""
    columns = sa_inspect(cfg.model).columns
    eq_fields = [f for f in cfg.filter_fields if f in columns]
    rng_fields = [f for f in cfg.range_fields if f in columns]
    extra_fields = [f for f, _ in cfg.extra_filters]
    scope_spec = cfg.office_scope
    # The office column is queryable as a single-office ``?{field}=`` filter even
    # when the registry did not list it among ``filter_fields`` (so OFF-SCOPE-7
    # resources honour it without adding it to the generic equality pass).
    office_param = (
        scope_spec.field
        if scope_spec and scope_spec.field in columns and scope_spec.field not in eq_fields
        else None
    )

    def list_items(db, tenant_id, page, _office=None, **kwargs):  # noqa: ANN001
        filters = {f: kwargs.get(f) for f in eq_fields}
        # Non-column filters ride in the same dict; CRUDBase's equality pass skips
        # anything the model has no attribute for, so only the crud_class sees them.
        filters.update({f: kwargs.get(f) for f in extra_fields})
        id_in = _parse_ids(kwargs.get("ids"), cfg.pk_type) if cfg.id_in_param else None
        range_filters: dict[str, dict[str, Any]] = {}
        for f in rng_fields:
            lo, hi = kwargs.get(f"{f}_from"), kwargs.get(f"{f}_to")
            if lo is not None or hi is not None:
                range_filters[f] = {}
                if lo is not None:
                    range_filters[f]["ge"] = lo
                if hi is not None:
                    range_filters[f]["le"] = hi
        # OFF-SCOPE-1/2/4/8: resolve the office restriction from the caller's
        # scope + the explicit office filter (validated). The office field is
        # taken out of the plain equality pass so it is applied once, with
        # include-global semantics, by the resolved filter.
        office_column = office_ids = None
        office_include_null = False
        if scope_spec is not None and _office is not None:
            # OFF-SCOPE-5/8: a custom crud_class resolves resource-specific office
            # semantics (PatientCRUD's search_scope/seen_at, OfficeCRUD's
            # assigned_to_me) that need the caller. It rides in the filters dict
            # under a reserved key the generic equality pass ignores (no such
            # column). Injected before the generic narrowing so ``list_scope_only``
            # resources (offices) still get it.
            filters["__office_scope"] = _office
            if not scope_spec.list_scope_only:
                explicit = filters.pop(scope_spec.field, None)
                if explicit is None and office_param is not None:
                    explicit = kwargs.get(office_param)
                patient_scoped = bool(filters.get(scope_spec.patient_filter))
                resolved = resolve_list_office_filter(
                    _office,
                    column=scope_spec.field,
                    kind=scope_spec.kind,
                    explicit_value=explicit,
                    patient_scoped=patient_scoped,
                    default_narrow=scope_spec.default_narrow,
                )
                office_column = resolved.column
                office_ids = resolved.office_ids
                office_include_null = resolved.include_null
        items, total = crud.list(
            db,
            tenant_id=tenant_id,
            page=page.page,
            size=page.size,
            sort=page.sort,
            order=page.order,
            search=page.search,
            filters=filters,
            range_filters=range_filters,
            id_in=id_in,
            office_column=office_column,
            office_ids=office_ids,
            office_include_null=office_include_null,
        )
        if cfg.read_enrich is not None and items:
            cfg.read_enrich(db, items, tenant_id)
        return PaginatedResponse.build(items, total, page.page, page.size)

    params = [
        inspect.Parameter("db", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=DbSession),
        inspect.Parameter("tenant_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=TenantId),
        inspect.Parameter("page", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=PageParams),
    ]
    if scope_spec is not None:
        params.append(
            inspect.Parameter(
                "_office", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=OfficeScopeDep
            )
        )
    if office_param is not None:
        params.append(
            inspect.Parameter(
                office_param,
                inspect.Parameter.KEYWORD_ONLY,
                default=Query(None, description=f"Filter by {office_param}"),
                annotation=Optional[int],
            )
        )
    for f in eq_fields:
        pytype = _col_pytype(columns, f) or str
        params.append(
            inspect.Parameter(
                f,
                inspect.Parameter.KEYWORD_ONLY,
                default=Query(None, description=f"Filter by {f}"),
                annotation=Optional[pytype],
            )
        )
    for f, pytype in cfg.extra_filters:
        params.append(
            inspect.Parameter(
                f,
                inspect.Parameter.KEYWORD_ONLY,
                default=Query(None, description=f"Filter by {f}"),
                annotation=Optional[pytype],
            )
        )
    if cfg.id_in_param:
        params.append(
            inspect.Parameter(
                "ids",
                inspect.Parameter.KEYWORD_ONLY,
                default=Query(
                    None,
                    description="Comma-separated list of ids to return (batch lookup)",
                ),
                annotation=Optional[str],
            )
        )
    for f in rng_fields:
        pytype = _col_pytype(columns, f) or str
        params.append(
            inspect.Parameter(
                f"{f}_from",
                inspect.Parameter.KEYWORD_ONLY,
                default=Query(None, description=f"{f} >= (inclusive lower bound)"),
                annotation=Optional[pytype],
            )
        )
        params.append(
            inspect.Parameter(
                f"{f}_to",
                inspect.Parameter.KEYWORD_ONLY,
                default=Query(None, description=f"{f} <= (inclusive upper bound)"),
                annotation=Optional[pytype],
            )
        )
    list_items.__signature__ = inspect.Signature(params)
    return list_items


_ERRORS = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def register_crud(cfg: CrudConfig) -> APIRouter:
    plural = cfg.plural or cfg.prefix
    crud: CRUDBase = cfg.crud_class(
        cfg.model,
        pk_attr=cfg.pk_name,
        soft_delete_field=cfg.soft_delete_field,
        soft_delete_value=cfg.soft_delete_value,
        search_fields=cfg.search_fields,
        sortable_fields=cfg.sortable_fields,
        default_sort=cfg.default_sort,
        search_relations=cfg.search_relations,
        hide_soft_deleted=cfg.hide_soft_deleted,
    )
    router = APIRouter(
        prefix=f"/{cfg.prefix}",
        tags=[cfg.tag],
        dependencies=[Depends(get_current_user)],
        responses=_ERRORS,
    )
    PkPath = Annotated[cfg.pk_type, Path(description=f"{cfg.singular} identifier")]
    # EDIT-PLAN-5: the write routes carry the permission dependency; reads do not.
    write_deps = (
        [Depends(require_permission(*cfg.write_permissions,
                                    action=f"modify {plural.replace('_', ' ')}"))]
        if cfg.write_permissions else []
    )
    # ACCESS-RIGHTS C1 / RBAC-6: each write verb may need a verb-specific right on
    # top of the (optional) shared write right.
    create_deps = write_deps + (
        [Depends(require_permission(*cfg.create_permissions,
                                    action=f"create {cfg.singular.replace('_', ' ')}"))]
        if cfg.create_permissions else []
    )
    update_deps = write_deps + (
        [Depends(require_permission(*cfg.update_permissions,
                                    action=f"modify {plural.replace('_', ' ')}"))]
        if cfg.update_permissions else []
    )
    delete_deps = write_deps + (
        [Depends(require_permission(*cfg.delete_permissions,
                                    action=f"delete {plural.replace('_', ' ')}"))]
        if cfg.delete_permissions else []
    )
    versioned = hasattr(cfg.model, concurrency.VERSION_FIELD)
    # EDIT-PLAN-1: every versioned resource documents the precondition headers
    # its PATCH / DELETE honour and the 412 they can return.
    precondition_doc = (
        " Honours `If-Match` (the ETag from GET) and `If-Unmodified-Since`; "
        "a stale precondition is **412 precondition_failed** with the current version."
        if versioned else ""
    )
    write_responses = {412: {"model": ErrorResponse}} if versioned else {}

    router.get(
        "",
        response_model=PaginatedResponse[cfg.read_schema],
        operation_id=f"list_{plural}",
        summary=f"List {plural.replace('_', ' ')}",
    )(_make_list_endpoint(cfg, crud, plural))

    @router.post(
        "",
        response_model=cfg.read_schema,
        status_code=status.HTTP_201_CREATED,
        operation_id=f"create_{cfg.singular}",
        summary=f"Create {cfg.singular.replace('_', ' ')}",
        dependencies=create_deps,
    )
    def create_item(
        db: DbSession,
        tenant_id: TenantId,
        body: cfg.create_schema,  # type: ignore[valid-type]
        current=Depends(get_current_user),
        office=Depends(get_office_context),
    ):
        concurrency.reset()
        data = body.model_dump(exclude_unset=True)
        # OFF-SCOPE-1/3/11: validate a body office against the caller's
        # assignments, default-stamp the working office when omitted, and (when
        # configured + enabled) require an office on a point-of-service create.
        if cfg.office_scope is not None and office is not None:
            resolved = apply_write_office(office, data, cfg.office_scope)
            if (
                cfg.office_scope.require_on_create
                and settings.OFFICE_REQUIRE_POS_OFFICE
                and resolved is None
            ):
                raise ValidationError(
                    f"{cfg.office_scope.field} is required for this record",
                    code="office_id_required",
                    details={"field": cfg.office_scope.field},
                )
        obj = crud.create(db, data, tenant_id=tenant_id, created_by=current.id)
        if cfg.read_enrich is not None:
            cfg.read_enrich(db, [obj], tenant_id)
        return obj

    @router.get(
        "/{item_id}",
        response_model=cfg.read_schema,
        operation_id=f"get_{cfg.singular}",
        summary=f"Get {cfg.singular.replace('_', ' ')} by id",
    )
    def get_item(
        db: DbSession,
        tenant_id: TenantId,
        item_id: PkPath,
        response: Response,
        office=Depends(get_office_context),
    ):
        obj = crud.get(db, item_id, tenant_id=tenant_id)
        # OFF-SCOPE-6: a caller without patients:view_cross_office may only open a
        # chart whose home office is theirs, or one the patient was seen at.
        if (
            cfg.office_scope is not None
            and cfg.office_scope.enforce_patient_visibility
            and office is not None
        ):
            assert_patient_visible(office, obj)
        if cfg.read_enrich is not None:
            cfg.read_enrich(db, [obj], tenant_id)
        # EDIT-PLAN-1: the version a later PATCH / DELETE can assert with If-Match.
        etag = concurrency.etag_for(obj) if versioned else None
        if etag:
            response.headers["ETag"] = etag
        return obj

    @router.patch(
        "/{item_id}",
        response_model=cfg.read_schema,
        operation_id=f"update_{cfg.singular}",
        summary=f"Update {cfg.singular.replace('_', ' ')}",
        description=f"Partial update of one {cfg.singular.replace('_', ' ')}.{precondition_doc}",
        dependencies=update_deps,
        responses=write_responses,
    )
    def update_item(
        db: DbSession,
        tenant_id: TenantId,
        item_id: PkPath,
        body: cfg.update_schema,  # type: ignore[valid-type]
        request: Request,
        response: Response,
        current=Depends(get_current_user),
        office=Depends(get_office_context),
    ):
        concurrency.from_headers(request.headers)
        data = body.model_dump(exclude_unset=True)
        # OFF-SCOPE-1: a PATCH that *moves* a record to another office must target
        # one the caller is assigned to. The default-stamp is not applied on
        # update (an omitted office leaves the stored one) — only an explicit,
        # non-null office in the payload is validated.
        if cfg.office_scope is not None and office is not None and data.get(cfg.office_scope.field) is not None:
            validate_target_office(office, data[cfg.office_scope.field], field=cfg.office_scope.field)
        obj = crud.update(db, item_id, data, tenant_id=tenant_id, updated_by=current.id)
        if cfg.read_enrich is not None:
            cfg.read_enrich(db, [obj], tenant_id)
        etag = concurrency.etag_for(obj) if versioned else None
        if etag:
            response.headers["ETag"] = etag
        return obj

    @router.delete(
        "/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id=f"delete_{cfg.singular}",
        summary=f"Delete {cfg.singular.replace('_', ' ')}",
        description=f"Delete one {cfg.singular.replace('_', ' ')}.{precondition_doc}",
        dependencies=delete_deps,
        responses=write_responses,
    )
    def delete_item(db: DbSession, tenant_id: TenantId, item_id: PkPath, request: Request):
        concurrency.from_headers(request.headers)
        crud.delete(db, item_id, tenant_id=tenant_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
