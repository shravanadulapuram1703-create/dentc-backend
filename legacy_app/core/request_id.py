import uuid
from contextvars import ContextVar

request_id_ctx = ContextVar("request_id", default="-")
user_id_ctx = ContextVar("user_id", default="-")
tenant_ctx = ContextVar("tenant", default="public")
