"""Generic, tenant-aware CRUD operations over a SQLAlchemy session.

One ``CRUDBase`` instance serves any model. It is the single data-access layer —
there is deliberately no repository abstraction on top. Entities needing real
business rules subclass this and override ``create``/``update`` to delegate to a
service.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class CRUDBase(Generic[ModelT]):
    def __init__(
        self,
        model: type[ModelT],
        *,
        pk_attr: str = "id",
        soft_delete_field: str | None = "is_active",
        soft_delete_value: bool = False,
        search_fields: tuple[str, ...] = (),
        sortable_fields: tuple[str, ...] = (),
        default_sort: str = "created_at",
    ) -> None:
        self.model = model
        self.pk_attr = pk_attr
        self.soft_delete_field = soft_delete_field if hasattr(model, soft_delete_field or "") else None
        self.soft_delete_value = soft_delete_value
        self.search_fields = tuple(f for f in search_fields if hasattr(model, f))
        self.sortable_fields = tuple(f for f in sortable_fields if hasattr(model, f))
        self.default_sort = default_sort if hasattr(model, default_sort) else pk_attr
        self.resource_name = model.__name__

    # ── helpers ────────────────────────────────────────────────────────────
    @property
    def _pk(self):
        return getattr(self.model, self.pk_attr)

    def _scope_tenant(self, stmt, tenant_id: int | None):
        if tenant_id is not None and hasattr(self.model, "tenant_id"):
            stmt = stmt.where(self.model.tenant_id == tenant_id)
        return stmt

    # ── reads ──────────────────────────────────────────────────────────────
    def get(self, db: Session, obj_id: Any, *, tenant_id: int | None = None) -> ModelT:
        stmt = self._scope_tenant(select(self.model).where(self._pk == obj_id), tenant_id)
        obj = db.execute(stmt).scalar_one_or_none()
        if obj is None:
            raise NotFoundError(f"{self.resource_name} '{obj_id}' was not found")
        return obj

    def list(
        self,
        db: Session,
        *,
        tenant_id: int | None = None,
        page: int = 1,
        size: int = 20,
        sort: str | None = None,
        order: str = "desc",
        search: str | None = None,
        filters: dict[str, Any] | None = None,
        range_filters: dict[str, dict[str, Any]] | None = None,
    ) -> tuple[list[ModelT], int]:
        stmt = self._scope_tenant(select(self.model), tenant_id)

        # equality filters on whitelisted columns
        for field, value in (filters or {}).items():
            if value is not None and hasattr(self.model, field):
                stmt = stmt.where(getattr(self.model, field) == value)

        # range filters: {field: {"ge": lo, "le": hi}} (either bound optional)
        for field, bounds in (range_filters or {}).items():
            if not hasattr(self.model, field):
                continue
            column = getattr(self.model, field)
            if bounds.get("ge") is not None:
                stmt = stmt.where(column >= bounds["ge"])
            if bounds.get("le") is not None:
                stmt = stmt.where(column <= bounds["le"])

        # free-text search across declared columns
        if search and self.search_fields:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(*[getattr(self.model, f).ilike(term) for f in self.search_fields])
            )

        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

        sort_col = sort if (sort and sort in self.sortable_fields) else self.default_sort
        column = getattr(self.model, sort_col)
        stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
        stmt = stmt.offset((page - 1) * size).limit(size)

        items = list(db.execute(stmt).scalars().all())
        return items, total

    # ── writes ───────────────────────────────────────────────────────────
    def create(
        self,
        db: Session,
        data: dict[str, Any],
        *,
        tenant_id: int | None = None,
        created_by: int | None = None,
    ) -> ModelT:
        payload = dict(data)
        if tenant_id is not None and hasattr(self.model, "tenant_id"):
            payload.setdefault("tenant_id", tenant_id)
        if created_by is not None and hasattr(self.model, "created_by"):
            payload.setdefault("created_by", created_by)
        obj = self.model(**payload)
        db.add(obj)
        self._commit(db)
        db.refresh(obj)
        return obj

    def update(
        self,
        db: Session,
        obj_id: Any,
        data: dict[str, Any],
        *,
        tenant_id: int | None = None,
    ) -> ModelT:
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        for key, value in data.items():
            setattr(obj, key, value)
        self._commit(db)
        db.refresh(obj)
        return obj

    def delete(self, db: Session, obj_id: Any, *, tenant_id: int | None = None) -> None:
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        if self.soft_delete_field:
            setattr(obj, self.soft_delete_field, self.soft_delete_value)
        else:
            db.delete(obj)
        self._commit(db)

    def _commit(self, db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError(
                f"{self.resource_name} violates a uniqueness or reference constraint",
                details=str(getattr(exc, "orig", exc)),
            ) from exc
