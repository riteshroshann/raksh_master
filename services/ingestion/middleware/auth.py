import time
from collections import defaultdict
from typing import Optional

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import settings

logger = structlog.get_logger()

UNPROTECTED_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        api_key = request.headers.get("x-api-key")

        if not api_key:
            logger.warning(
                "auth_missing_api_key",
                path=request.url.path,
                client_ip=request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=401,
                content={"error": "Missing API key", "detail": "Provide x-api-key header"},
            )

        if api_key != settings.ingestion_api_key:
            logger.warning(
                "auth_invalid_api_key",
                path=request.url.path,
                client_ip=request.client.host if request.client else "unknown",
            )
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid API key"},
            )

        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_requests: int = 100, window_seconds: int = 60):
        super().__init__(app)
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        api_key = request.headers.get("x-api-key", "")
        identifier = f"{client_ip}:{api_key}"

        now = time.time()
        window_start = now - self._window_seconds

        self._requests[identifier] = [
            t for t in self._requests[identifier] if t > window_start
        ]

        if len(self._requests[identifier]) >= self._max_requests:
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                path=request.url.path,
                request_count=len(self._requests[identifier]),
            )

            remaining = 0
            retry_after = int(self._requests[identifier][0] + self._window_seconds - now) + 1

            response = JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "detail": f"Maximum {self._max_requests} requests per {self._window_seconds} seconds",
                    "retry_after_seconds": retry_after,
                },
            )
            response.headers["X-RateLimit-Limit"] = str(self._max_requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["Retry-After"] = str(retry_after)
            return response

        self._requests[identifier].append(now)

        response = await call_next(request)

        remaining = self._max_requests - len(self._requests[identifier])
        response.headers["X-RateLimit-Limit"] = str(self._max_requests)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))

        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "POST" and "multipart/form-data" not in (request.headers.get("content-type", "")):
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                    max_size = settings.max_upload_size_mb * 1024 * 1024
                    if size > max_size:
                        return JSONResponse(
                            status_code=413,
                            content={
                                "error": "Request too large",
                                "detail": f"Maximum content length is {settings.max_upload_size_mb} MB",
                            },
                        )
                except ValueError:
                    pass

        if request.url.path.startswith("/ingest"):
            user_agent = request.headers.get("user-agent", "")
            if not user_agent:
                logger.info("missing_user_agent", path=request.url.path)

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"

        return response
