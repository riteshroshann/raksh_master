import hashlib
import time
import uuid

import structlog
from fastapi import APIRouter, HTTPException, UploadFile, Form

from config import settings
from models.enums import DocumentType, FastingStatus, IngestChannel
from models.schemas import (
    ChunkUploadCompleteRequest,
    ChunkUploadCompleteResponse,
    ChunkUploadInitRequest,
    ChunkUploadInitResponse,
    ChunkUploadPartRequest,
    ConfirmationPayload,
    ConfirmationResponse,
    ExtractedField,
    UploadResponse,
)
from pipeline.classifier import classify_document
from pipeline.confidence import score_confidence
from pipeline.extractor import extract_fields
from pipeline.validator import validate_before_save
from services.audit import AuditService
from services.database import DatabaseService
from services.storage import StorageService
from services.chunked_upload import chunked_upload_manager

logger = structlog.get_logger()
router = APIRouter(prefix="/ingest")

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/tiff",
    "application/dicom",
    "application/octet-stream",
}

MAX_UPLOAD_BYTES = settings.max_upload_size_mb * 1024 * 1024


@router.post("/upload", response_model=UploadResponse)
async def ingest_upload(
    file: UploadFile,
    member_id: str = Form(...),
) -> UploadResponse:
    start_time = time.monotonic()

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Accepted: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    contents = await file.read()

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB")

    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    ingest_id = str(uuid.uuid4())
    content_hash = hashlib.sha256(contents).hexdigest()

    logger.info(
        "ingest_started",
        ingest_id=ingest_id,
        filename=file.filename,
        content_type=file.content_type,
        size_bytes=len(contents),
        member_id=member_id,
        channel=IngestChannel.UPLOAD.value,
    )

    audit_service = AuditService()
    await audit_service.log_document_upload(ingest_id, IngestChannel.UPLOAD.value, member_id)

    db_service = DatabaseService()
    existing = await db_service.find_by_content_hash(content_hash, member_id)
    if existing:
        await audit_service.log_duplicate_detected(content_hash, member_id)
        raise HTTPException(status_code=409, detail="Duplicate document detected. This file has already been ingested.")

    storage_service = StorageService()
    storage_path = await storage_service.store_original(contents, file.filename or "unknown", member_id)

    try:
        doc_type = await classify_document(contents, file.content_type or "application/octet-stream")
    except Exception as exc:
        await audit_service.log_classification_failure(ingest_id, str(exc))
        raise HTTPException(status_code=422, detail=f"Document classification failed: {str(exc)}")

    extraction_model_used = "none"
    try:
        raw_extractions = await extract_fields(contents, doc_type)
        extraction_model_used = raw_extractions[0].get("extraction_model", "unknown") if raw_extractions else "none"
        await audit_service.log_extraction(
            ingest_id, doc_type.value,
            extraction_model_used,
            len(raw_extractions),
        )
    except Exception as exc:
        logger.error(
            "extraction_failed_vlm_to_ocr_fallback",
            ingest_id=ingest_id,
            doc_type=doc_type.value,
            error=str(exc),
            severity="ERROR",
        )
        await audit_service.log_extraction_failure(ingest_id, "unknown", str(exc))
        raw_extractions = []

    scored_extractions = score_confidence(raw_extractions)
    validated_extractions = validate_before_save(scored_extractions, doc_type)

    from pipeline.phi_deid import deid_pipeline

    deidentified_extractions = []
    phi_entities_found = 0
    for extraction in validated_extractions:
        cleaned, entities = deid_pipeline.deidentify_structured(extraction)
        phi_entities_found += len(entities)
        deidentified_extractions.append(cleaned)

    if phi_entities_found > 0:
        logger.warning(
            "phi_detected_and_redacted_in_extraction",
            ingest_id=ingest_id,
            phi_entities_redacted=phi_entities_found,
        )

    from services.review_queue import review_queue
    review_queue.queue_low_confidence_extractions(
        ingest_id=ingest_id,
        document_id=None,
        member_id=member_id,
        extractions=deidentified_extractions,
        threshold=0.70,
    )

    elapsed_ms = (time.monotonic() - start_time) * 1000

    logger.info(
        "ingest_completed",
        ingest_id=ingest_id,
        doc_type=doc_type.value,
        num_fields=len(deidentified_extractions),
        channel=IngestChannel.UPLOAD.value,
        duration_ms=round(elapsed_ms, 2),
        phi_redacted=phi_entities_found,
    )

    return UploadResponse(
        storage_path=storage_path,
        doc_type=doc_type,
        extractions=[ExtractedField(**f) for f in deidentified_extractions],
        requires_confirmation=True,
        ingest_id=ingest_id,
        content_hash=content_hash,
    )


@router.post("/confirm", response_model=ConfirmationResponse)
async def ingest_confirm(payload: ConfirmationPayload) -> ConfirmationResponse:
    start_time = time.monotonic()

    logger.info(
        "confirmation_started",
        member_id=str(payload.member_id),
        doc_type=payload.doc_type.value,
        num_parameters=len(payload.parameters),
    )

    db_service = DatabaseService()
    audit_service = AuditService()

    member = await db_service.get_member(str(payload.member_id))
    member_sex = member.get("sex", "any") if member else "any"
    member_dob = None
    if member and member.get("dob"):
        from datetime import date as date_type
        try:
            if isinstance(member["dob"], str):
                member_dob = date_type.fromisoformat(member["dob"])
            else:
                member_dob = member["dob"]
        except (ValueError, TypeError):
            pass

    from services.reference_ranges import ReferenceRangeEnrichmentService
    enrichment_service = ReferenceRangeEnrichmentService()

    param_dicts = [p.model_dump() for p in payload.parameters]
    enriched_params = await enrichment_service.enrich_parameters(param_dicts, member_sex, member_dob)

    for i, enriched in enumerate(enriched_params):
        if enriched.get("indian_range_low") is not None:
            payload.parameters[i].indian_range_low = enriched["indian_range_low"]
        if enriched.get("indian_range_high") is not None:
            payload.parameters[i].indian_range_high = enriched["indian_range_high"]
        if enriched.get("flag"):
            from models.enums import ParameterFlag
            try:
                payload.parameters[i].flag = ParameterFlag(enriched["flag"])
            except ValueError:
                pass

    fasting_violations = []
    for param in payload.parameters:
        range_info = enriched_params[payload.parameters.index(param)] if payload.parameters.index(param) < len(enriched_params) else {}
        if range_info.get("fasting_required") and param.fasting_status in (None, FastingStatus.UNKNOWN):
            fasting_violations.append(param.parameter_name)

    if fasting_violations:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "fasting_status_required",
                "message": "Fasting status must be confirmed for these parameters",
                "affected_parameters": fasting_violations,
            },
        )

    document_id = await db_service.write_confirmed_document(payload)

    await audit_service.log_confirmation(document_id, str(payload.member_id), len(payload.parameters))

    elapsed_ms = (time.monotonic() - start_time) * 1000

    logger.info(
        "confirmation_completed",
        document_id=document_id,
        num_parameters=len(payload.parameters),
        duration_ms=round(elapsed_ms, 2),
    )

    return ConfirmationResponse(
        document_id=document_id,
        status="saved",
        parameters_saved=len(payload.parameters),
    )


@router.post("/chunked/init", response_model=ChunkUploadInitResponse)
async def chunked_upload_init(request: ChunkUploadInitRequest) -> ChunkUploadInitResponse:
    result = chunked_upload_manager.init_upload(
        filename=request.filename,
        total_size_bytes=request.total_size_bytes,
        total_chunks=request.total_chunks,
        member_id=str(request.member_id),
        content_type=request.content_type,
    )

    return ChunkUploadInitResponse(**result)


@router.post("/chunked/part")
async def chunked_upload_part(
    file: UploadFile,
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
) -> dict:
    chunk_data = await file.read()

    try:
        result = chunked_upload_manager.add_chunk(upload_id, chunk_index, chunk_data)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/chunked/complete", response_model=ChunkUploadCompleteResponse)
async def chunked_upload_complete(request: ChunkUploadCompleteRequest) -> ChunkUploadCompleteResponse:
    try:
        contents, metadata = chunked_upload_manager.assemble(request.upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ingest_id = str(uuid.uuid4())
    content_hash = metadata["content_hash"]
    member_id = str(request.member_id)

    audit_service = AuditService()
    await audit_service.log_document_upload(ingest_id, "chunked_upload", member_id)

    db_service = DatabaseService()
    existing = await db_service.find_by_content_hash(content_hash, member_id)
    if existing:
        chunked_upload_manager.cleanup(request.upload_id)
        raise HTTPException(status_code=409, detail="Duplicate document detected.")

    storage_service = StorageService()
    storage_path = await storage_service.store_original(contents, metadata["filename"], member_id)

    try:
        doc_type = await classify_document(contents, metadata["content_type"])
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Document classification failed: {str(exc)}")

    try:
        raw_extractions = await extract_fields(contents, doc_type)
    except Exception as exc:
        logger.error(
            "chunked_extraction_failed_vlm_to_ocr_fallback",
            ingest_id=ingest_id,
            error=str(exc),
            severity="ERROR",
        )
        raw_extractions = []

    scored_extractions = score_confidence(raw_extractions)
    validated_extractions = validate_before_save(scored_extractions, doc_type)

    from pipeline.phi_deid import deid_pipeline

    deidentified_extractions = []
    phi_entities_found = 0
    for extraction in validated_extractions:
        cleaned, entities = deid_pipeline.deidentify_structured(extraction)
        phi_entities_found += len(entities)
        deidentified_extractions.append(cleaned)

    if phi_entities_found > 0:
        logger.warning(
            "phi_detected_and_redacted_in_chunked_upload",
            ingest_id=ingest_id,
            phi_entities_redacted=phi_entities_found,
        )

    chunked_upload_manager.cleanup(request.upload_id)

    logger.info(
        "chunked_ingest_completed",
        ingest_id=ingest_id,
        doc_type=doc_type.value,
        num_fields=len(deidentified_extractions),
        phi_redacted=phi_entities_found,
    )

    return ChunkUploadCompleteResponse(
        storage_path=storage_path,
        doc_type=doc_type,
        extractions=[ExtractedField(**f) for f in deidentified_extractions],
        requires_confirmation=True,
        ingest_id=ingest_id,
        content_hash=content_hash,
    )


@router.get("/chunked/status/{upload_id}")
async def chunked_upload_status(upload_id: str) -> dict:
    status = chunked_upload_manager.get_upload_status(upload_id)
    if not status:
        raise HTTPException(status_code=404, detail="Upload not found")
    return status
