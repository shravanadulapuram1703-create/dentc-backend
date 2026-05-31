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
from dataclasses import dataclass, field
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy import inspect as sa_inspect

from app.api.deps import DbSession, PageParams, TenantId, get_current_user
from app.crud.base import CRUDBase
from app.schemas.common import ErrorResponse, PaginatedResponse


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
    filter_fields: tuple[str, ...] = ()
    range_fields: tuple[str, ...] = ()  # emit {f}_from / {f}_to typed query params
    default_sort: str = "created_at"
    soft_delete_field: str | None = "is_active"
    soft_delete_value: bool = False


def _col_pytype(columns, name: str) -> type | None:  # noqa: ANN001
    col = columns.get(name)
    if col is None:
        return None
    try:
        return col.type.python_type
    except Exception:  # noqa: BLE001
        return str


def _make_list_endpoint(cfg: "CrudConfig", crud: CRUDBase, plural: str):
    """Build a list handler whose signature declares one typed, OpenAPI-visible
    ``Query`` param per filter field (+ ``{f}_from``/``{f}_to`` per range field),
    so Orval generates typed filter arguments. Values are FastAPI-coerced."""
    columns = sa_inspect(cfg.model).columns
    eq_fields = [f for f in cfg.filter_fields if f in columns]
    rng_fields = [f for f in cfg.range_fields if f in columns]

    def list_items(db, tenant_id, page, **kwargs):  # noqa: ANN001
        filters = {f: kwargs.get(f) for f in eq_fields}
        range_filters: dict[str, dict[str, Any]] = {}
        for f in rng_fields:
            lo, hi = kwargs.get(f"{f}_from"), kwargs.get(f"{f}_to")
            if lo is not None or hi is not None:
                range_filters[f] = {}
                if lo is not None:
                    range_filters[f]["ge"] = lo
                if hi is not None:
                    range_filters[f]["le"] = hi
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
        )
        return PaginatedResponse.build(items, total, page.page, page.size)

    params = [
        inspect.Parameter("db", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=DbSession),
        inspect.Parameter("tenant_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=TenantId),
        inspect.Parameter("page", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=PageParams),
    ]
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
    crud: CRUDBase = CRUDBase(
        cfg.model,
        pk_attr=cfg.pk_name,
        soft_delete_field=cfg.soft_delete_field,
        soft_delete_value=cfg.soft_delete_value,
        search_fields=cfg.search_fields,
        sortable_fields=cfg.sortable_fields,
        default_sort=cfg.default_sort,
    )
    router = APIRouter(
        prefix=f"/{cfg.prefix}",
        tags=[cfg.tag],
        dependencies=[Depends(get_current_user)],
        responses=_ERRORS,
    )
    PkPath = Annotated[cfg.pk_type, Path(description=f"{cfg.singular} identifier")]

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
    )
    def create_item(
        db: DbSession,
        tenant_id: TenantId,
        body: cfg.create_schema,  # type: ignore[valid-type]
        current=Depends(get_current_user),
    ):
        data = body.model_dump(exclude_unset=True)
        return crud.create(db, data, tenant_id=tenant_id, created_by=current.id)

    @router.get(
        "/{item_id}",
        response_model=cfg.read_schema,
        operation_id=f"get_{cfg.singular}",
        summary=f"Get {cfg.singular.replace('_', ' ')} by id",
    )
    def get_item(db: DbSession, tenant_id: TenantId, item_id: PkPath):
        return crud.get(db, item_id, tenant_id=tenant_id)

    @router.patch(
        "/{item_id}",
        response_model=cfg.read_schema,
        operation_id=f"update_{cfg.singular}",
        summary=f"Update {cfg.singular.replace('_', ' ')}",
    )
    def update_item(
        db: DbSession,
        tenant_id: TenantId,
        item_id: PkPath,
        body: cfg.update_schema,  # type: ignore[valid-type]
    ):
        data = body.model_dump(exclude_unset=True)
        return crud.update(db, item_id, data, tenant_id=tenant_id)

    @router.delete(
        "/{item_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        operation_id=f"delete_{cfg.singular}",
        summary=f"Delete {cfg.singular.replace('_', ' ')}",
    )
    def delete_item(db: DbSession, tenant_id: TenantId, item_id: PkPath):
        crud.delete(db, item_id, tenant_id=tenant_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
