import time

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from middleware.auth import ApiKeyMiddleware
from routes.health import router as health_router
from routes.ingest import router as ingest_router

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(structlog.get_config()["wrapper_class"]._log_level if hasattr(structlog.get_config().get("wrapper_class", object), "_log_level") else 0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

app = FastAPI(
    title="Raksh Ingestion Service",
    description="Medical document ingestion, classification, extraction, and confidence scoring pipeline. HIPAA/DPDP Act 2023 compliant.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start_time = time.monotonic()
    request_id = request.headers.get("X-Request-ID", str(id(request)))

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else "unknown",
    )

    try:
        response: Response = await call_next(request)
    except Exception as exc:
        duration_ms = (time.monotonic() - start_time) * 1000
        logger.error(
            "request_error",
            method=request.method,
            path=request.url.path,
            error=str(exc),
            duration_ms=round(duration_ms, 2),
        )
        raise

    duration_ms = (time.monotonic() - start_time) * 1000

    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-Ms"] = str(round(duration_ms, 2))
    response.headers["X-Service"] = "raksh-ingestion"
    response.headers["X-Version"] = "1.0.0"

    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)

app.add_middleware(ApiKeyMiddleware)

app.include_router(health_router)
app.include_router(ingest_router)


@app.on_event("startup")
async def on_startup():
    logger.info(
        "service_started",
        environment=settings.environment,
        extraction_backend=settings.extraction_backend,
        max_upload_mb=settings.max_upload_size_mb,
        data_region=settings.data_region,
    )


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("service_shutting_down")
