from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from models.enums import (
    DocumentType,
    FastingStatus,
    IngestChannel,
    ParameterFlag,
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


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    status_code: int


class MetricsData(BaseModel):
    total_ingestions: int = 0
    total_confirmations: int = 0
    average_confidence: float = 0.0
    patient_edit_rate: float = 0.0
    extractions_by_doc_type: dict[str, int] = {}
    extractions_by_channel: dict[str, int] = {}
