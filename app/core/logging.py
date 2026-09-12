"""Structured logging setup.

``setup_logging()`` is called once from the app factory. It installs a single
stream handler with a context-aware formatter so every line carries the request
id, user, and tenant when available (populated by the request-context middleware
via :class:`contextvars`).
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys

# Per-request context, populated by middleware and read by the log filter.
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="-")
tenant_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("tenant_id", default="-")
# SIG-8: the signature audit trail records *which workstation* captured a
# signature. The CRUD engine never sees the Request object, so the middleware
# parks the client address + User-Agent here and ``signature_service`` reads them.
client_ip_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("client_ip", default=None)
user_agent_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_agent", default=None)
# CS-6: the base URL the *caller* reached us on (scheme + host, honouring
# X-Forwarded-Proto/Host), so a document ``file_url`` built during this request
# points at the API the frontend is actually talking to — not a fixed
# ``PUBLIC_API_BASE_URL`` that names another environment.
request_base_url_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_base_url", default=None)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.user_id = user_id_ctx.get()
        record.tenant_id = tenant_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user_id": getattr(record, "user_id", "-"),
            "tenant_id": getattr(record, "tenant_id", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


_TEXT_FORMAT = (
    "%(asctime)s | %(levelname)-7s | %(name)s | "
    "req=%(request_id)s user=%(user_id)s tenant=%(tenant_id)s | %(message)s"
)


def setup_logging(level: str = "INFO", json_logs: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if json_logs else logging.Formatter(_TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Quiet noisy third-party loggers.
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
