"""Generic, tenant-aware CRUD operations over a SQLAlchemy session.

One ``CRUDBase`` instance serves any model. It is the single data-access layer —
there is deliberately no repository abstraction on top. Entities needing real
business rules subclass this and override ``create``/``update`` to delegate to a
service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import func, inspect as sa_inspect, or_, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.core import audit_context, concurrency
from app.core.exceptions import NotFoundError, app_error_from_db
from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class _Blank:
    """Stand-in "before" object for a create: every payload key counts as changed."""

    def __getattr__(self, name: str) -> object:
        return _MISSING


_MISSING = object()


class CRUDBase(Generic[ModelT]):
    #: Filter fields this class resolves itself in :meth:`_extra_list_clauses`
    #: instead of plain ``column == value`` (e.g. a filter that must span a join
    #: table). Declared by subclasses; the generic equality pass skips them.
    custom_filter_fields: tuple[str, ...] = ()

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
    def get(
        self, db: Session, obj_id: Any, *, tenant_id: int | None = None,
        for_update: bool = False,
    ) -> ModelT:
        stmt = self._scope_tenant(select(self.model).where(self._pk == obj_id), tenant_id)
        # EDIT-PLAN-1: a write carrying a precondition locks the row for the
        # rest of the transaction so the version check and the UPDATE cannot
        # interleave with another writer (Postgres; SQLite has no row locks and
        # the dialect drops the clause).
        if for_update:
            stmt = stmt.with_for_update()
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
            if (
                value is not None
                and field not in self.custom_filter_fields
                and hasattr(self.model, field)
            ):
                stmt = stmt.where(getattr(self.model, field) == value)

        # subclass-resolved filters (a filter that is not a plain column compare)
        for clause in self._extra_list_clauses(filters or {}):
            stmt = stmt.where(clause)

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
        if search:
            term = f"%{search}%"
            clauses = [getattr(self.model, f).ilike(term) for f in self.search_fields]
            for fk_attr, related, rel_fields in self.search_relations:
                rel_pk = sa_inspect(related).primary_key[0]
                sub = select(rel_pk).where(
                    or_(*[getattr(related, rf).ilike(term) for rf in rel_fields])
                )
                clauses.append(getattr(self.model, fk_attr).in_(sub))
            # MH-9: a subclass can recognise a search term the plain column
            # ilikes cannot ("Last, First" reaches two columns at once).
            clauses.extend(self._extra_search_clauses(search))
            if clauses:
                stmt = stmt.where(or_(*clauses))

        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

        sort_col = sort if (sort and sort in self.sortable_fields) else self.default_sort
        column = getattr(self.model, sort_col)
        # MH-9: relevance first when the caller searched. Without it an exact
        # surname match is unreachable behind hundreds of substring hits paged
        # alphabetically, which is what made the patient picker unusable. The
        # caller's own sort still applies - it just decides ties within a tier.
        order_by = self._search_order(search) if search else []
        order_by.append(column.desc() if order == "desc" else column.asc())
        # INS-8: append the primary key as a deterministic tiebreaker so rows
        # never shift/drop/duplicate across page boundaries when the primary
        # sort column is non-unique (e.g. carriers/employers sorted by name).
        if sort_col != self.pk_attr:
            order_by.append(self._pk.asc())
        stmt = stmt.order_by(*order_by).offset((page - 1) * size).limit(size)

        items = list(db.execute(stmt).scalars().all())
        return items, total

    def _extra_list_clauses(self, filters: dict[str, Any]) -> list:  # noqa: ARG002
        """WHERE clauses for :attr:`custom_filter_fields`. Overridden by subclasses."""
        return []

    def _extra_search_clauses(self, search: str) -> list:  # noqa: ARG002
        """Extra OR-ed free-text clauses a subclass derives from the raw term."""
        return []

    def _search_order(self, search: str) -> list:  # noqa: ARG002
        """Relevance ``ORDER BY`` terms applied ahead of the caller's sort when a
        search term is present. Empty means "no ranking" (the historical
        behaviour), so only resources that declare one are affected."""
        return []

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
        self._audit(obj, after=audit_context.diff_fields(_Blank(), payload)[1])
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
        precondition = concurrency.snapshot()
        obj = self.get(db, obj_id, tenant_id=tenant_id, for_update=precondition is not None)
        # EDIT-PLAN-1: the caller said "only if unchanged since X" — judged
        # before anything is assigned, against the row as it is *now*.
        concurrency.check(obj, precondition, db=db, resource=self.resource_name)
        # MH-20: compare before assigning. A PATCH that re-sends the stored value
        # used to re-stamp ``updated_at`` / ``updated_by`` ("modified by Admin
        # User on 09/10" with nothing changed) — and the screen's old
        # PATCH-everything save did that to all 88 alerts on every Save. With no
        # difference there is no assignment, no actor stamp, no UPDATE and no
        # audit row worth writing.
        before, after = audit_context.diff_fields(obj, data)
        # A subclass may have mutated the row (or queued rows) before delegating
        # here; those still have to land even when the payload itself is a no-op.
        subclass_changed = db.is_modified(obj) or bool(db.new) or bool(db.deleted)
        if not before and not subclass_changed:
            return obj
        for key in before:
            setattr(obj, key, data[key])
        changed = bool(before) or db.is_modified(obj)
        # INS-6: server-maintained modified actor (integer updated_by columns only).
        if changed and updated_by is not None and self._is_int_col("updated_by"):
            obj.updated_by = updated_by
        # EDIT-PLAN-1: ``updated_at`` is the row's *version*. Stamp it here with
        # microsecond precision instead of leaving it to the column's
        # ``onupdate=now()`` — SQLite's CURRENT_TIMESTAMP is whole seconds, so
        # two saves inside one second read as the same version and a stale
        # precondition passes.
        if changed and hasattr(obj, concurrency.VERSION_FIELD):
            setattr(obj, concurrency.VERSION_FIELD,
                    datetime.now(timezone.utc).replace(tzinfo=None))
        self._commit(db)
        db.refresh(obj)
        # MH-19: the audit row carries what changed, so a second edit no longer
        # erases the first value.
        self._audit(obj, before=before, after=after)
        return obj

    def delete(self, db: Session, obj_id: Any, *, tenant_id: int | None = None) -> None:
        precondition = concurrency.snapshot()
        obj = self.get(db, obj_id, tenant_id=tenant_id, for_update=precondition is not None)
        concurrency.check(obj, precondition, db=db, resource=self.resource_name)
        self._audit(obj, before={"is_active": getattr(obj, "is_active", None)}
                    if self.soft_delete_field else {"deleted": True})
        if self.soft_delete_field:
            setattr(obj, self.soft_delete_field, self.soft_delete_value)
        else:
            db.delete(obj)
        self._commit(db)

    def _audit(self, obj: Any, *, before: dict | None = None, after: dict | None = None) -> None:
        """MH-19: hand the row identity + diff to the request's audit context."""
        try:
            pk = getattr(obj, self.pk_attr, None)
            patient_id = getattr(obj, "patient_id", None)
            if patient_id is None and self.model.__tablename__ == "patients":
                patient_id = pk
            audit_context.record(
                resource_id=str(pk) if pk is not None else None,
                row_id=pk,
                patient_id=patient_id if isinstance(patient_id, int) else None,
                before=before or None,
                after=after or None,
            )
        except Exception:  # noqa: BLE001 - auditing never breaks a write
            pass

    def _flush(self, db: Session) -> None:
        """A flush that can fail the same way ``_commit`` can (a subclass that
        needs the SERIAL id mid-transaction hits the unique/FK/length checks
        here, not at commit). Rolls back so the session is reusable, then maps
        the driver error the same way (GAP-AP-26)."""
        try:
            db.flush()
        except (IntegrityError, DataError) as exc:
            db.rollback()
            raise app_error_from_db(exc, resource=self.resource_name) from exc

    def _commit(self, db: Session) -> None:
        try:
            db.commit()
        except (IntegrityError, DataError) as exc:
            db.rollback()
            # GAP-AP-26: 409 ``constraint`` for a unique collision, 422 for a
            # dangling reference / missing column / over-long value — with the
            # table, column(s) and constraint named (was a bare 409 carrying the
            # raw driver string for every one of them).
            raise app_error_from_db(exc, resource=self.resource_name) from exc
