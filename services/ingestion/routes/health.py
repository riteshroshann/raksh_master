import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from config import settings
from models.schemas import (
    AuditLogListResponse,
    ConsentCreateRequest,
    ConsentResponse,
    ConsentWithdrawRequest,
    DocumentListResponse,
    DocumentResponse,
    ErasureRequest,
    ErasureResponse,
    FamilyMemberCreate,
    FamilyMemberResponse,
    FHIRBundleResponse,
    HealthResponse,
    LineageResponse,
    MetricsData,
    ParameterResponse,
    ParameterTrendResponse,
    ReferenceRangeLookupRequest,
    ReferenceRangeResponse,
    UnlinkedDocumentResponse,
    LinkDocumentRequest,
    ABDMRegistrationRequest,
    ABDMRegistrationResponse,
    ABDMConsentRequest,
    ABDMConsentResponse,
)
from services.audit import AuditService
from services.consent import ConsentService
from services.database import DatabaseService
from services.fhir_mapper import fhir_mapper
from services.lineage import LineageService
from services.patient_linking import UnlinkedQueueService
from services.reference_ranges import ReferenceRangeService
from services.abdm_pacs import abdm_client

router = APIRouter()

SERVICE_START_TIME = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service="raksh-ingestion",
        version="1.0.0",
        environment=settings.environment,
        uptime_seconds=round(time.time() - SERVICE_START_TIME, 2),
    )


@router.get("/metrics", response_model=MetricsData)
async def metrics() -> MetricsData:
    db_service = DatabaseService()
    data = await db_service.get_pipeline_metrics()

    if data.patient_edit_rate > settings.patient_edit_rate_alert_threshold:
        data.alert_active = True
        data.alert_message = (
            f"Patient edit rate ({data.patient_edit_rate:.1f}%) exceeds "
            f"threshold ({settings.patient_edit_rate_alert_threshold}%). "
            f"Extraction quality may be degraded."
        )

    return data


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    member_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    doc_type: Optional[str] = None,
) -> DocumentListResponse:
    db_service = DatabaseService()
    documents, total = await db_service.list_documents(
        str(member_id), page, page_size, doc_type
    )
    return DocumentListResponse(
        documents=[DocumentResponse(**d) for d in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: UUID) -> DocumentResponse:
    db_service = DatabaseService()
    document = await db_service.get_document(str(document_id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(**document)


@router.get("/documents/{document_id}/parameters")
async def get_document_parameters(document_id: UUID) -> list[ParameterResponse]:
    db_service = DatabaseService()
    params = await db_service.get_parameters_for_document(str(document_id))
    return [ParameterResponse(**p) for p in params]


@router.get("/parameters/trend", response_model=ParameterTrendResponse)
async def get_parameter_trend(
    member_id: UUID,
    parameter_name: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> ParameterTrendResponse:
    db_service = DatabaseService()
    trend_data = await db_service.get_parameter_trend(str(member_id), parameter_name, limit)
    return ParameterTrendResponse(**trend_data)


@router.get("/lineage/{parameter_id}", response_model=list[LineageResponse])
async def get_parameter_lineage(parameter_id: UUID) -> list[LineageResponse]:
    lineage_service = LineageService()
    entries = await lineage_service.get_lineage_for_parameter(str(parameter_id))
    return [LineageResponse(**e) for e in entries]


@router.get("/reference-ranges/lookup", response_model=Optional[ReferenceRangeResponse])
async def lookup_reference_range(
    parameter_name: str,
    sex: str,
    age: Optional[int] = None,
    population: str = "indian",
) -> Optional[ReferenceRangeResponse]:
    range_service = ReferenceRangeService()
    result = await range_service.lookup(parameter_name, sex, age, population)
    if not result:
        raise HTTPException(status_code=404, detail=f"No reference range found for {parameter_name}")
    return ReferenceRangeResponse(**result)


@router.get("/reference-ranges/{parameter_name}", response_model=list[ReferenceRangeResponse])
async def get_reference_ranges(parameter_name: str) -> list[ReferenceRangeResponse]:
    range_service = ReferenceRangeService()
    ranges = await range_service.get_all_for_parameter(parameter_name)
    return [ReferenceRangeResponse(**r) for r in ranges]


@router.post("/consent", response_model=ConsentResponse)
async def grant_consent(request: ConsentCreateRequest, account_id: UUID = Query(...)) -> ConsentResponse:
    consent_service = ConsentService()
    record = await consent_service.grant_consent(account_id, request.purpose.value)
    return ConsentResponse(**record)


@router.post("/consent/withdraw", response_model=ConsentResponse)
async def withdraw_consent(request: ConsentWithdrawRequest, account_id: UUID = Query(...)) -> ConsentResponse:
    consent_service = ConsentService()
    record = await consent_service.withdraw_consent(account_id, request.purpose.value, request.withdrawal_method)
    if not record:
        raise HTTPException(status_code=404, detail="No active consent found for this purpose")
    return ConsentResponse(**record)


@router.get("/consent", response_model=list[ConsentResponse])
async def list_consents(account_id: UUID = Query(...)) -> list[ConsentResponse]:
    consent_service = ConsentService()
    records = await consent_service.get_consents(account_id)
    return [ConsentResponse(**r) for r in records]


@router.post("/erasure", response_model=ErasureResponse)
async def execute_erasure(request: ErasureRequest) -> ErasureResponse:
    consent_service = ConsentService()
    result = await consent_service.execute_erasure(request.account_id)
    return ErasureResponse(**result)


@router.get("/unlinked")
async def get_unlinked_queue() -> list[UnlinkedDocumentResponse]:
    queue_service = UnlinkedQueueService()
    entries = await queue_service.get_queue()
    return [UnlinkedDocumentResponse(**e) for e in entries]


@router.post("/unlinked/link")
async def link_unlinked_document(request: LinkDocumentRequest) -> dict:
    queue_service = UnlinkedQueueService()
    result = await queue_service.link_document(request.ingest_id, request.member_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found in unlinked queue")
    return {"status": "linked", "ingest_id": request.ingest_id, "member_id": str(request.member_id)}


@router.get("/audit", response_model=AuditLogListResponse)
async def get_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    event: Optional[str] = None,
    account_id: Optional[UUID] = None,
) -> AuditLogListResponse:
    audit_service = AuditService()
    entries, total = await audit_service.get_entries(event, account_id, page, page_size)
    return AuditLogListResponse(
        entries=entries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/fhir/bundle/{document_id}", response_model=FHIRBundleResponse)
async def get_fhir_bundle(document_id: UUID) -> FHIRBundleResponse:
    db_service = DatabaseService()
    document = await db_service.get_document(str(document_id))
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    member = await db_service.get_member(document["member_id"])
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    params = await db_service.get_parameters_for_document(str(document_id))

    bundle = fhir_mapper.build_lab_report_bundle(member, document, params)

    return FHIRBundleResponse(
        resource_type="Bundle",
        bundle_type="document",
        entry_count=len(bundle.get("entry", [])),
        fhir_json=bundle,
    )


@router.post("/abdm/register", response_model=ABDMRegistrationResponse)
async def abdm_register(request: ABDMRegistrationRequest) -> ABDMRegistrationResponse:
    result = await abdm_client.verify_abha_id(request.abha_id)

    return ABDMRegistrationResponse(
        abha_id=request.abha_id,
        member_id=request.member_id,
        linked=result.get("verified", False),
        health_id=result.get("profile", {}).get("healthId"),
    )


@router.post("/abdm/consent-request", response_model=ABDMConsentResponse)
async def abdm_consent_request(request: ABDMConsentRequest) -> ABDMConsentResponse:
    from datetime import datetime

    result = await abdm_client.create_consent_request(
        patient_abha_id=request.patient_abha_id,
        purpose=request.purpose,
        requester_name=request.requester_name,
        date_from=request.date_range_from.isoformat(),
        date_to=request.date_range_to.isoformat(),
        health_info_types=request.health_info_types,
    )

    return ABDMConsentResponse(
        consent_request_id=result.get("consentRequestId", ""),
        status="REQUESTED",
        created_at=datetime.utcnow(),
    )
