# app/core/logging_filter.py
import logging
from app.core.request_id import request_id_ctx, user_id_ctx, tenant_ctx

class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get(None) or "-"
        record.user_id = user_id_ctx.get(None) or "-"
        record.tenant = tenant_ctx.get(None) or "-"
        return True
