"""
Performance monitoring middleware
Tracks request/response times and logs performance metrics
"""
import time
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware to track request performance metrics."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timing
        start_time = time.time()
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log error with timing
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} - "
                f"Time: {process_time:.3f}s - Error: {str(e)}",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "process_time": process_time,
                    "error": str(e)
                }
            )
            raise
        
        # Calculate process time
        process_time = time.time() - start_time
        
        # Log performance metrics
        logger.info(
            f"{request.method} {request.url.path} - "
            f"Status: {response.status_code} - "
            f"Time: {process_time:.3f}s",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time,
                "query_params": str(request.query_params) if request.query_params else None
            }
        )
        
        # Add performance headers
        response.headers["X-Process-Time"] = f"{process_time:.3f}"
        
        # Log slow requests
        if process_time > 1.0:  # Requests taking more than 1 second
            logger.warning(
                f"Slow request detected: {request.method} {request.url.path} - "
                f"Time: {process_time:.3f}s",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "process_time": process_time,
                    "slow_request": True
                }
            )
        
        return response
