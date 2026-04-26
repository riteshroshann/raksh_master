import hashlib
import uuid

import structlog
from fastapi import APIRouter, HTTPException, UploadFile, Form

from config import settings
from models.enums import DocumentType, IngestChannel
from models.schemas import (
    ConfirmationPayload,
    ConfirmationResponse,
    ExtractedField,
    UploadResponse,
)
from pipeline.classifier import classify_document
from pipeline.confidence import score_confidence
from pipeline.extractor import extract_fields
from pipeline.validator import validate_before_save
from services.database import DatabaseService
from services.storage import StorageService

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
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Accepted: {', '.join(ALLOWED_CONTENT_TYPES)}",
        )

    contents = await file.read()

    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB",
        )

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

    db_service = DatabaseService()
    existing = await db_service.find_by_content_hash(content_hash, member_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Duplicate document detected. This file has already been ingested.",
        )

    storage_service = StorageService()
    storage_path = await storage_service.store_original(
        contents, file.filename or "unknown", member_id
    )

    doc_type = await classify_document(contents, file.content_type or "application/octet-stream")

    raw_extractions = await extract_fields(contents, doc_type)

    scored_extractions = score_confidence(raw_extractions)

    validated_extractions = validate_before_save(scored_extractions, doc_type)

    logger.info(
        "ingest_completed",
        ingest_id=ingest_id,
        doc_type=doc_type.value,
        num_fields=len(validated_extractions),
        channel=IngestChannel.UPLOAD.value,
    )

    return UploadResponse(
        storage_path=storage_path,
        doc_type=doc_type,
        extractions=[ExtractedField(**f) for f in validated_extractions],
        requires_confirmation=True,
        ingest_id=ingest_id,
        content_hash=content_hash,
    )


@router.post("/confirm", response_model=ConfirmationResponse)
async def ingest_confirm(payload: ConfirmationPayload) -> ConfirmationResponse:
    logger.info(
        "confirmation_started",
        member_id=str(payload.member_id),
        doc_type=payload.doc_type.value,
        num_parameters=len(payload.parameters),
    )

    db_service = DatabaseService()

    document_id = await db_service.write_confirmed_document(payload)

    logger.info(
        "confirmation_completed",
        document_id=document_id,
        num_parameters=len(payload.parameters),
    )

    return ConfirmationResponse(
        document_id=document_id,
        status="saved",
        parameters_saved=len(payload.parameters),
    )
