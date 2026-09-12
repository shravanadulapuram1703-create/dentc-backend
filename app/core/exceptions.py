"""Application exception hierarchy and the global error contract.

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "details": ...}}

Domain code raises :class:`AppError` subclasses; FastAPI's ``HTTPException`` and
Pydantic ``RequestValidationError`` are normalised into the same shape by the
handlers registered in :func:`register_exception_handlers`.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class AppError(Exception):
    """Base class for all expected, client-facing application errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_error"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class LockedError(AppError):
    """Resource/account temporarily locked (e.g. too many failed logins)."""

    status_code = status.HTTP_423_LOCKED
    code = "account_locked"


class RateLimitError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class PreconditionFailedError(AppError):
    """EDIT-PLAN-1: an optimistic-concurrency precondition (``If-Match`` /
    ``If-Unmodified-Since`` / ``expected_updated_at``) did not hold — the row
    changed after the client read it. ``details.current`` carries the row's
    present version so the UI can say "changed by X at Y, reload?"."""

    status_code = status.HTTP_412_PRECONDITION_FAILED
    code = "precondition_failed"


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


# ── Database errors → the error contract (GAP-AP-26) ─────────────────────────
# Every driver-level failure used to surface as ``500 internal_error`` with no
# diagnostic, so a client could not tell a bad payload (do not retry) from an
# outage (retry / fall back) — the frontend's registration fallback was written
# around exactly that ambiguity, and it is what routed a 409 into a three-minute
# chained intake. These map the SQLSTATE classes that mean "your input" onto
# 422/409 with the table / column / constraint named. Anything else stays a 500.
_PG_UNIQUE = "23505"
_PG_FOREIGN_KEY = "23503"
_PG_NOT_NULL = "23502"
_PG_CHECK = "23514"
_PG_TOO_LONG = "22001"
_PG_NUMERIC_RANGE = "22003"
_PG_INVALID_TEXT = "22P02"
_PG_INVALID_DATETIME = ("22007", "22008")

_KEY_DETAIL = re.compile(r"Key \((?P<cols>[^)]+)\)=\((?P<vals>[^)]*)\)")
_VARCHAR_LEN = re.compile(r"character(?: varying)?\((?P<n>\d+)\)")
_SQLITE_CONSTRAINT = re.compile(
    r"(?P<kind>UNIQUE|NOT NULL|FOREIGN KEY|CHECK) constraint failed(?::\s*(?P<what>.+))?"
)


def _first_line(text: str) -> str:
    return (text or "").strip().splitlines()[0] if text else ""


def _split_sqlite_columns(what: str | None) -> tuple[str | None, list[str]]:
    """``"patients.chart_no, patients.tenant_id"`` -> (``patients``, [cols])."""
    if not what:
        return None, []
    table: str | None = None
    columns: list[str] = []
    for part in what.split(","):
        part = part.strip()
        if "." in part:
            t, _, c = part.partition(".")
            table = table or t
            columns.append(c)
        elif part:
            columns.append(part)
    return table, columns


def app_error_from_db(exc: Exception, *, resource: str | None = None) -> AppError:
    """Classify a SQLAlchemy ``IntegrityError``/``DataError`` into an ``AppError``.

    Works from the Postgres SQLSTATE + ``diag`` block when the driver supplies
    them and from the message text otherwise (SQLite in the test suite), so the
    contract is the same on both. ``details`` always carries ``sqlstate`` and
    the driver's first message line so a support log can be matched to it.
    """
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "pgcode", None)
    diag = getattr(orig, "diag", None)
    raw = _first_line(str(orig or exc))
    subject = f"{resource}: " if resource else ""
    details: dict[str, Any] = {"sqlstate": sqlstate, "db_message": raw}
    if diag is not None:
        for attr in ("table_name", "column_name", "constraint_name"):
            value = getattr(diag, attr, None)
            if value:
                details[attr.replace("_name", "")] = value
        detail_line = getattr(diag, "message_detail", None)
        if detail_line:
            m = _KEY_DETAIL.search(detail_line)
            if m:
                details["columns"] = [c.strip() for c in m.group("cols").split(",")]
                details["values"] = [v.strip() for v in m.group("vals").split(",")]

    if isinstance(exc, DataError) or (sqlstate or "").startswith("22"):
        if sqlstate == _PG_TOO_LONG or "too long" in raw.lower():
            m = _VARCHAR_LEN.search(raw)
            if m:
                details["max_length"] = int(m.group("n"))
            return ValidationError(
                f"{subject}a value is longer than the column allows"
                + (f" (max {details['max_length']} characters)" if "max_length" in details else "")
                + ".",
                code="value_too_long", details=details,
            )
        if sqlstate == _PG_NUMERIC_RANGE or "out of range" in raw.lower():
            return ValidationError(
                f"{subject}a numeric value is out of range for its column.",
                code="value_out_of_range", details=details,
            )
        if sqlstate in _PG_INVALID_DATETIME or sqlstate == _PG_INVALID_TEXT:
            return ValidationError(
                f"{subject}a value has the wrong format for its column.",
                code="invalid_value", details=details,
            )
        return ValidationError(
            f"{subject}the database rejected a value.", code="invalid_value", details=details,
        )

    # IntegrityError — the constraint kind decides the status: a *unique*
    # collision is a conflict with what exists (409); a dangling reference, a
    # missing required column or a failed CHECK is a defect in the payload (422).
    kind: str | None = None
    if sqlstate == _PG_UNIQUE:
        kind = "unique"
    elif sqlstate == _PG_FOREIGN_KEY:
        kind = "foreign_key"
    elif sqlstate == _PG_NOT_NULL:
        kind = "not_null"
    elif sqlstate == _PG_CHECK:
        kind = "check"
    else:
        m = _SQLITE_CONSTRAINT.search(raw)
        if m:
            kind = {"UNIQUE": "unique", "NOT NULL": "not_null",
                    "FOREIGN KEY": "foreign_key", "CHECK": "check"}[m.group("kind")]
            table, columns = _split_sqlite_columns(m.group("what"))
            if table:
                details.setdefault("table", table)
            if columns:
                if kind == "check":
                    details.setdefault("constraint", columns[0])
                else:
                    details.setdefault("columns", columns)
                    if len(columns) == 1:
                        details.setdefault("column", columns[0])
    details["kind"] = kind or "unknown"

    if kind == "unique":
        cols = details.get("columns") or ([details["column"]] if details.get("column") else [])
        where = f" on {', '.join(cols)}" if cols else ""
        return ConflictError(
            f"{subject}a record with the same value{where} already exists.",
            code="constraint", details=details,
        )
    if kind == "foreign_key":
        return ValidationError(
            f"{subject}a referenced record does not exist.",
            code="foreign_key_violation", details=details,
        )
    if kind == "not_null":
        col = details.get("column")
        return ValidationError(
            f"{subject}required value missing" + (f" for '{col}'" if col else "") + ".",
            code="not_null_violation", details=details,
        )
    if kind == "check":
        return ValidationError(
            f"{subject}a value violates a database check constraint.",
            code="check_violation", details=details,
        )
    return ConflictError(
        f"{subject}the write violates a database constraint.",
        code="constraint", details=details,
    )


# Map of HTTP status -> stable error code for HTTPException normalisation.
_STATUS_CODE_MAP = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_412_PRECONDITION_FAILED: "precondition_failed",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "validation_error",
    status.HTTP_423_LOCKED: "account_locked",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODE_MAP.get(exc.status_code, "http_error")
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        details = None if isinstance(exc.detail, str) else exc.detail
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code, message, details),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # jsonable_encoder: Pydantic error ``input`` values can be non-JSON-native
        # types (e.g. a Decimal for a NUMERIC field) that plain json.dumps rejects.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                "validation_error", "Request validation failed", jsonable_encoder(exc.errors())
            ),
        )

    @app.exception_handler(IntegrityError)
    @app.exception_handler(DataError)
    async def _db_error_handler(_: Request, exc: Exception) -> JSONResponse:
        # GAP-AP-26: a payload the database refused is the client's to fix —
        # tell it which value, not "an unexpected error occurred".
        err = app_error_from_db(exc)
        logger.warning("Database rejected request: %s -> %s %s", _first_line(str(exc)),
                       err.status_code, err.code)
        return JSONResponse(
            status_code=err.status_code,
            content=_error_body(err.code, err.message, jsonable_encoder(err.details)),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        # Genuinely unexpected: no internals leak, but the request id lets a
        # client-side report be matched to the server log line above.
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                "internal_error", "An unexpected error occurred",
                {"request_id": request_id_ctx.get()},
            ),
        )
