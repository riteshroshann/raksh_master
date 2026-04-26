from datetime import date, datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from models.enums import (
    DocumentType,
    FastingStatus,
    IngestChannel,
    ParameterFlag,
    ConsentPurpose,
    Sex,
)


class ExtractedField(BaseModel):
    name: str
    value: Optional[str] = None
    value_numeric: Optional[float] = None
    unit: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    requires_manual_entry: bool = False
    bounding_box: Optional[dict] = None
    raw_ocr_output: Optional[str] = None
    extraction_model: Optional[str] = None


class UploadResponse(BaseModel):
    storage_path: str
    doc_type: DocumentType
    extractions: list[ExtractedField]
    requires_confirmation: bool = True
    ingest_id: str
    content_hash: str


class ChunkUploadInitRequest(BaseModel):
    filename: str
    total_size_bytes: int = Field(gt=0)
    total_chunks: int = Field(gt=0)
    member_id: UUID
    content_type: str = "application/octet-stream"


class ChunkUploadInitResponse(BaseModel):
    upload_id: str
    chunk_size_bytes: int
    total_chunks: int


class ChunkUploadPartRequest(BaseModel):
    upload_id: str
    chunk_index: int = Field(ge=0)


class ChunkUploadCompleteRequest(BaseModel):
    upload_id: str
    member_id: UUID


class ChunkUploadCompleteResponse(BaseModel):
    storage_path: str
    doc_type: DocumentType
    extractions: list[ExtractedField]
    requires_confirmation: bool = True
    ingest_id: str
    content_hash: str


class ConfirmedParameter(BaseModel):
    parameter_name: str
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    lab_range_low: Optional[float] = None
    lab_range_high: Optional[float] = None
    indian_range_low: Optional[float] = None
    indian_range_high: Optional[float] = None
    flag: ParameterFlag = ParameterFlag.UNCONFIRMED
    confidence: float = Field(ge=0, le=1)
    fasting_status: FastingStatus = FastingStatus.UNKNOWN
    test_date: date
    patient_edited: bool = False
    original_value: Optional[str] = None
    extraction_model: Optional[str] = None
    raw_ocr_output: Optional[str] = None
    bounding_box: Optional[dict] = None


class ConfirmationPayload(BaseModel):
    member_id: UUID
    storage_path: str
    ingest_channel: IngestChannel = IngestChannel.UPLOAD
    doc_type: DocumentType
    doc_date: Optional[date] = None
    lab_name: Optional[str] = None
    doctor_name: Optional[str] = None
    content_hash: str
    parameters: list[ConfirmedParameter]

    @field_validator("parameters")
    @classmethod
    def validate_parameters_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one confirmed parameter is required")
        return v


class ConfirmationResponse(BaseModel):
    document_id: str
    status: str = "saved"
    parameters_saved: int


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "raksh-ingestion"
    version: str = "1.0.0"
    environment: str = "development"
    uptime_seconds: float = 0.0


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int
    ingest_id: Optional[str] = None


class MetricsData(BaseModel):
    total_ingestions: int = 0
    total_confirmations: int = 0
    average_confidence: float = 0.0
    patient_edit_rate: float = 0.0
    extractions_by_doc_type: dict[str, int] = {}
    extractions_by_channel: dict[str, int] = {}
    extraction_latency_ms: dict[str, float] = {}
    confidence_distribution: dict[str, float] = {}
    alert_active: bool = False
    alert_message: Optional[str] = None


class FamilyMemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    dob: date
    sex: Sex
    colour_hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class FamilyMemberResponse(BaseModel):
    id: UUID
    account_id: UUID
    name: str
    dob: date
    sex: str
    colour_hex: str
    created_at: datetime


class DocumentResponse(BaseModel):
    id: UUID
    member_id: UUID
    ingest_channel: str
    file_path: str
    doc_type: str
    doc_date: Optional[date] = None
    lab_name: Optional[str] = None
    doctor_name: Optional[str] = None
    content_hash: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class ParameterResponse(BaseModel):
    id: UUID
    document_id: UUID
    member_id: UUID
    parameter_name: str
    value_numeric: Optional[float] = None
    value_text: Optional[str] = None
    unit: Optional[str] = None
    lab_range_low: Optional[float] = None
    lab_range_high: Optional[float] = None
    indian_range_low: Optional[float] = None
    indian_range_high: Optional[float] = None
    flag: Optional[str] = None
    confidence: float
    fasting_status: Optional[str] = None
    test_date: date
    created_at: datetime


class ParameterTrendResponse(BaseModel):
    parameter_name: str
    unit: Optional[str] = None
    data_points: list[dict]
    indian_range_low: Optional[float] = None
    indian_range_high: Optional[float] = None


class LineageResponse(BaseModel):
    id: UUID
    parameter_id: UUID
    document_id: UUID
    extraction_model: str
    raw_ocr_output: Optional[str] = None
    bounding_box: Optional[dict] = None
    confidence_raw: Optional[float] = None
    patient_edited: bool
    original_value: Optional[str] = None
    created_at: datetime


class ConsentCreateRequest(BaseModel):
    purpose: ConsentPurpose
    granted: bool = True


class ConsentResponse(BaseModel):
    id: UUID
    account_id: UUID
    purpose: str
    granted_at: Optional[datetime] = None
    withdrawn_at: Optional[datetime] = None
    withdrawal_method: Optional[str] = None
    created_at: datetime


class ConsentWithdrawRequest(BaseModel):
    purpose: ConsentPurpose
    withdrawal_method: str = Field(min_length=1, max_length=255)


class ErasureRequest(BaseModel):
    account_id: UUID
    confirmation: str = Field(pattern=r"^ERASE_ALL_DATA$")


class ErasureResponse(BaseModel):
    status: str = "completed"
    account_id: UUID
    erased_at: datetime


class ReferenceRangeResponse(BaseModel):
    id: UUID
    parameter_name: str
    sex: Optional[str] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    range_low: Optional[float] = None
    range_high: Optional[float] = None
    unit: str
    source: str
    source_citation: str
    population: str
    version: int
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class ReferenceRangeLookupRequest(BaseModel):
    parameter_name: str
    sex: Sex
    age: Optional[int] = None
    population: str = "indian"


class AuditLogEntry(BaseModel):
    id: UUID
    event: str
    account_id: Optional[UUID] = None
    details: Optional[dict] = None
    executed_at: datetime


class AuditLogListResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int
    page: int
    page_size: int


class UnlinkedDocumentResponse(BaseModel):
    id: str
    ingest_id: str
    storage_path: str
    doc_type: DocumentType
    extractions: list[ExtractedField]
    ingest_channel: IngestChannel
    content_hash: str
    created_at: datetime


class LinkDocumentRequest(BaseModel):
    ingest_id: str
    member_id: UUID


class PatientMatchCandidate(BaseModel):
    member_id: UUID
    name: str
    dob: date
    match_score: float = Field(ge=0, le=1)
    match_signals: list[str]


class PatientMatchResponse(BaseModel):
    candidates: list[PatientMatchCandidate]
    auto_linked: bool = False
    linked_member_id: Optional[UUID] = None


class FHIRBundleResponse(BaseModel):
    resource_type: str = "Bundle"
    bundle_type: str = "document"
    entry_count: int
    fhir_json: dict


class ABDMRegistrationRequest(BaseModel):
    abha_id: str = Field(pattern=r"^\d{14}$")
    member_id: UUID


class ABDMRegistrationResponse(BaseModel):
    abha_id: str
    member_id: UUID
    linked: bool
    health_id: Optional[str] = None


class ABDMConsentRequest(BaseModel):
    purpose: str
    patient_abha_id: str
    requester_name: str
    date_range_from: date
    date_range_to: date
    health_info_types: list[str]


class ABDMConsentResponse(BaseModel):
    consent_request_id: str
    status: str
    created_at: datetime
