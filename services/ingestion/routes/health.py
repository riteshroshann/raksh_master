import time

from fastapi import APIRouter

from models.schemas import HealthResponse, MetricsData
from services.database import DatabaseService

router = APIRouter()

SERVICE_START_TIME = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service="raksh-ingestion",
        version="1.0.0",
    )


@router.get("/metrics")
async def metrics() -> MetricsData:
    db_service = DatabaseService()
    return await db_service.get_pipeline_metrics()
