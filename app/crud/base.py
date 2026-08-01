"""Generic, tenant-aware CRUD operations over a SQLAlchemy session.

One ``CRUDBase`` instance serves any model. It is the single data-access layer —
there is deliberately no repository abstraction on top. Entities needing real
business rules subclass this and override ``create``/``update`` to delegate to a
service.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import func, inspect as sa_inspect, or_, select
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
        search_relations: tuple[tuple[str, type, tuple[str, ...]], ...] = (),
        hide_soft_deleted: bool = False,
    ) -> None:
        self.model = model
        self.pk_attr = pk_attr
        self.soft_delete_field = soft_delete_field if hasattr(model, soft_delete_field or "") else None
        self.soft_delete_value = soft_delete_value
        # PP-1: when True, ``list`` hides rows DELETE soft-deleted unless the caller
        # explicitly filters on the soft-delete column itself. Opt-in per resource
        # because some screens (providers, definitions) legitimately want to see
        # inactive rows in the default listing.
        self.hide_soft_deleted = hide_soft_deleted
        self.search_fields = tuple(f for f in search_fields if hasattr(model, f))
        self.sortable_fields = tuple(f for f in sortable_fields if hasattr(model, f))
        # INS-9: extend free-text search across a related table via an FK, e.g.
        # match an insurance plan by its carrier/employer *name* (plans store ids).
        # Each entry is (fk_attr_on_self, related_model, related_search_fields).
        self.search_relations = tuple(
            (fk, rel, fields)
            for fk, rel, fields in search_relations
            if hasattr(model, fk)
        )
        self.default_sort = default_sort if hasattr(model, default_sort) else pk_attr
        self.resource_name = model.__name__

    # ── helpers ────────────────────────────────────────────────────────────
    @property
    def _pk(self):
        return getattr(self.model, self.pk_attr)

    def _is_int_col(self, name: str) -> bool:
        """True if ``name`` maps to an integer column (so an actor user id fits)."""
        col = sa_inspect(self.model).columns.get(name)
        if col is None:
            return False
        try:
            return col.type.python_type is int
        except Exception:  # noqa: BLE001
            return False

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
        id_in: list[Any] | None = None,
    ) -> tuple[list[ModelT], int]:
        stmt = self._scope_tenant(select(self.model), tenant_id)

        # restrict to an explicit id set (e.g. join-derived membership)
        if id_in is not None:
            stmt = stmt.where(self._pk.in_(id_in))

        # equality filters on whitelisted columns
        for field, value in (filters or {}).items():
            if value is not None and hasattr(self.model, field):
                stmt = stmt.where(getattr(self.model, field) == value)

        # PP-1: a soft-deleted row must not come back on the next page load. Only
        # applied when the caller did not ask about the soft-delete column itself,
        # so ``?is_active=false`` still surfaces the deleted rows on purpose.
        if (
            self.hide_soft_deleted
            and self.soft_delete_field
            and (filters or {}).get(self.soft_delete_field) is None
        ):
            stmt = stmt.where(
                getattr(self.model, self.soft_delete_field) != self.soft_delete_value
            )

        # range filters: {field: {"ge": lo, "le": hi}} (either bound optional)
        for field, bounds in (range_filters or {}).items():
            if not hasattr(self.model, field):
                continue
            column = getattr(self.model, field)
            if bounds.get("ge") is not None:
                stmt = stmt.where(column >= bounds["ge"])
            if bounds.get("le") is not None:
                stmt = stmt.where(column <= bounds["le"])

        # free-text search across declared columns (+ related-table names, INS-9)
        if search and (self.search_fields or self.search_relations):
            term = f"%{search}%"
            clauses = [getattr(self.model, f).ilike(term) for f in self.search_fields]
            for fk_attr, related, rel_fields in self.search_relations:
                rel_pk = sa_inspect(related).primary_key[0]
                sub = select(rel_pk).where(
                    or_(*[getattr(related, rf).ilike(term) for rf in rel_fields])
                )
                clauses.append(getattr(self.model, fk_attr).in_(sub))
            if clauses:
                stmt = stmt.where(or_(*clauses))

        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

        sort_col = sort if (sort and sort in self.sortable_fields) else self.default_sort
        column = getattr(self.model, sort_col)
        order_by = [column.desc() if order == "desc" else column.asc()]
        # INS-8: append the primary key as a deterministic tiebreaker so rows
        # never shift/drop/duplicate across page boundaries when the primary
        # sort column is non-unique (e.g. carriers/employers sorted by name).
        if sort_col != self.pk_attr:
            order_by.append(self._pk.asc())
        stmt = stmt.order_by(*order_by).offset((page - 1) * size).limit(size)

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
        # Only stamp the actor id into an *integer* created_by column; legacy
        # free-text created_by columns (carriers, etc.) are left untouched.
        if created_by is not None and self._is_int_col("created_by"):
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
        updated_by: int | None = None,
    ) -> ModelT:
        obj = self.get(db, obj_id, tenant_id=tenant_id)
        for key, value in data.items():
            setattr(obj, key, value)
        # INS-6: server-maintained modified actor (integer updated_by columns only).
        if updated_by is not None and self._is_int_col("updated_by"):
            obj.updated_by = updated_by
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
