from fastapi import Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
import structlog

from config import settings

logger = structlog.get_logger()

UNPROTECTED_PATHS = {"/health", "/metrics", "/docs", "/openapi.json", "/redoc"}


def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key != settings.ingestion_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in UNPROTECTED_PATHS:
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        if not api_key or api_key != settings.ingestion_api_key:
            logger.warning(
                "unauthorized_request",
                path=request.url.path,
                remote=request.client.host if request.client else "unknown",
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "detail": "Invalid or missing API key", "status_code": 401},
            )

        return await call_next(request)
