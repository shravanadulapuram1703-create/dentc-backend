# import time
# import logging
# import uuid
# from fastapi import Request
# from app.core.request_id import request_id_ctx

# logger = logging.getLogger("request")


# async def request_logging_middleware(request: Request, call_next):
#     request_id = str(uuid.uuid4())
#     request_id_ctx.set(request_id)

#     start_time = time.time()
#     response = await call_next(request)
#     duration = round(time.time() - start_time, 4)

#     logger.info(
#         f"{request.method} {request.url.path} "
#         f"status={response.status_code} "
#         f"duration={duration}s"
#     )

#     return response


# app/middleware/request_logging.py
import time
import uuid
from fastapi import Request
from app.core.request_id import request_id_ctx
import logging
from app.core.logging import setup_logging
logger = setup_logging()
logger = logging.getLogger(__name__)
logger.info("Inside Middle ware  logging -------------- Role error")


async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    token = request_id_ctx.set(request_id)
    logger.info(f"Inside request_logging_middleware {request_id} {token}")

    start_time = time.time()
    try:
        logger.info(f"Inside request_logging_middleware request : {request} ")
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception:
        status_code = 500
        logger.exception("Unhandled exception while processing request")
        raise
    finally:
        duration = round((time.time() - start_time) * 1000, 2)

        logger.info(
            "%s %s%s | status=%s | duration=%sms | client=%s",
            request.method,
            request.url.path,
            f"?{request.url.query}" if request.url.query else "",
            status_code,
            duration,
            request.client.host if request.client else "-",
        )

        # reset context var to avoid leaking between requests
        request_id_ctx.reset(token)

