import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from middleware.auth import RateLimitMiddleware, SecurityHeadersMiddleware
except ImportError:
    pass
from models.enums import (
    IngestChannel, DocumentType, ParameterFlag, FastingStatus,
    Sex, ExtractionBackend, ConsentPurpose, AuditEvent,
    DicomModality, ImageQuality, ProcessingStatus,
)
from models.schemas import (
    ExtractedField, UploadResponse, ConfirmedParameter,
    ConfirmationPayload, HealthResponse, MetricsData,
    FamilyMemberCreate, ReferenceRangeLookupRequest,
    ChunkUploadInitRequest, ChunkUploadPartRequest,
    ConsentCreateRequest, ConsentWithdrawRequest,
    ErasureRequest, LinkDocumentRequest,
    ABDMRegistrationRequest,
)
from pipeline.confidence import score_confidence, FIELD_THRESHOLDS, DEFAULT_THRESHOLD
from pipeline.validator import validate_before_save, _check_prohibited_content, PROHIBITED_DIAGNOSTIC_TERMS
from pipeline.classifier import _classify_by_keywords
from services.patient_linking import PatientLinkingService, UnlinkedQueueService
from services.chunked_upload import ChunkedUploadManager


class TestEnumCompleteness:
    def test_all_ingest_channels(self):
        expected = {"upload", "folder_watch", "email", "fax", "scanner", "emr_ehr", "pacs", "hl7", "abdm"}
        actual = {e.value for e in IngestChannel}
        assert actual == expected

    def test_all_document_types_textual(self):
        textual = {"lab_report", "prescription", "discharge_summary", "doctor_notes", "pathology_report", "referral_letter", "insurance_billing", "radiology_report"}
        actual = {e.value for e in DocumentType}
        assert textual.issubset(actual)

    def test_all_document_types_imaging(self):
        imaging = {"xray", "mri", "ct_scan", "ultrasound", "ecg_eeg", "mammogram"}
        actual = {e.value for e in DocumentType}
        assert imaging.issubset(actual)

    def test_parameter_flags(self):
        expected = {"normal", "above_range", "below_range", "critical_high", "critical_low", "unconfirmed", "borderline"}
        actual = {e.value for e in ParameterFlag}
        assert actual == expected

    def test_fasting_statuses(self):
        expected = {"fasting", "non_fasting", "unknown"}
        actual = {e.value for e in FastingStatus}
        assert actual == expected

    def test_consent_purposes(self):
        expected = {"data_storage", "data_processing", "sharing_with_doctor", "abdm_linking", "analytics", "research"}
        actual = {e.value for e in ConsentPurpose}
        assert actual == expected

    def test_audit_events_count(self):
        assert len(AuditEvent) >= 19

    def test_processing_status_flow(self):
        statuses = [s.value for s in ProcessingStatus]
        assert "received" in statuses
        assert "confirmed" in statuses
        assert "failed" in statuses

    def test_dicom_modalities(self):
        assert len(DicomModality) >= 10


class TestSchemaValidation:
    def test_extracted_field_valid(self):
        field = ExtractedField(name="hb", value="11.8", confidence=0.95)
        assert field.name == "hb"
        assert field.confidence == 0.95

    def test_extracted_field_confidence_bounds(self):
        with pytest.raises(Exception):
            ExtractedField(name="hb", value="11.8", confidence=1.5)

        with pytest.raises(Exception):
            ExtractedField(name="hb", value="11.8", confidence=-0.1)

    def test_family_member_valid(self):
        from datetime import date
        member = FamilyMemberCreate(name="Ramesh", dob=date(1985, 6, 15), sex=Sex.MALE, colour_hex="#4A90D9")
        assert member.name == "Ramesh"

    def test_family_member_colour_hex_validation(self):
        from datetime import date
        with pytest.raises(Exception):
            FamilyMemberCreate(name="Test", dob=date(1990, 1, 1), sex=Sex.MALE, colour_hex="red")

    def test_family_member_name_too_short(self):
        from datetime import date
        with pytest.raises(Exception):
            FamilyMemberCreate(name="", dob=date(1990, 1, 1), sex=Sex.MALE, colour_hex="#4A90D9")

    def test_confirmation_payload_empty_params(self):
        from datetime import date
        from uuid import uuid4
        with pytest.raises(Exception):
            ConfirmationPayload(
                member_id=uuid4(),
                storage_path="test/path",
                doc_type=DocumentType.LAB_REPORT,
                content_hash="abc123",
                parameters=[],
            )

    def test_erasure_request_confirmation(self):
        from uuid import uuid4
        req = ErasureRequest(account_id=uuid4(), confirmation="ERASE_ALL_DATA")
        assert req.confirmation == "ERASE_ALL_DATA"

    def test_erasure_request_wrong_confirmation(self):
        from uuid import uuid4
        with pytest.raises(Exception):
            ErasureRequest(account_id=uuid4(), confirmation="delete_please")

    def test_health_response_defaults(self):
        health = HealthResponse()
        assert health.status == "healthy"
        assert health.service == "raksh-ingestion"
        assert health.version == "1.0.0"

    def test_metrics_data_defaults(self):
        metrics = MetricsData()
        assert metrics.total_ingestions == 0
        assert metrics.patient_edit_rate == 0.0
        assert metrics.alert_active is False

    def test_chunk_upload_init_request(self):
        from uuid import uuid4
        req = ChunkUploadInitRequest(
            filename="scan.dcm", total_size_bytes=100_000_000,
            total_chunks=20, member_id=uuid4(),
        )
        assert req.total_chunks == 20

    def test_chunk_upload_init_zero_size(self):
        from uuid import uuid4
        with pytest.raises(Exception):
            ChunkUploadInitRequest(
                filename="test.pdf", total_size_bytes=0,
                total_chunks=1, member_id=uuid4(),
            )

    def test_abha_id_format(self):
        from uuid import uuid4
        req = ABDMRegistrationRequest(abha_id="12345678901234", member_id=uuid4())
        assert len(req.abha_id) == 14

    def test_abha_id_invalid_format(self):
        from uuid import uuid4
        with pytest.raises(Exception):
            ABDMRegistrationRequest(abha_id="12345", member_id=uuid4())


class TestConfidenceEdgeCases:
    def test_all_field_thresholds_exist(self):
        required_fields = ["medication_name", "dosage", "hb", "hemoglobin", "tsh", "insulin", "warfarin", "digoxin"]
        for field in required_fields:
            assert field in FIELD_THRESHOLDS

    def test_high_risk_medications_099(self):
        high_risk = ["insulin", "warfarin", "digoxin"]
        for field in high_risk:
            assert FIELD_THRESHOLDS[field] == 0.99

    def test_default_threshold_value(self):
        assert DEFAULT_THRESHOLD == 0.85

    def test_boundary_exactly_at_threshold(self):
        result = score_confidence([{"name": "hb", "value": 12.0, "confidence": 0.85}])
        assert result[0]["value"] == 12.0
        assert result[0]["requires_manual_entry"] is False

    def test_boundary_just_below_threshold(self):
        result = score_confidence([{"name": "hb", "value": 12.0, "confidence": 0.8499}])
        assert result[0]["value"] is None
        assert result[0]["requires_manual_entry"] is True

    def test_large_batch_scoring(self):
        extractions = [{"name": f"field_{i}", "value": f"val_{i}", "confidence": i / 100.0} for i in range(100)]
        result = score_confidence(extractions)
        assert len(result) == 100

    def test_missing_confidence_key(self):
        result = score_confidence([{"name": "hb", "value": 12.0}])
        assert result[0]["value"] is None
        assert result[0]["requires_manual_entry"] is True


class TestValidatorProhibitions:
    def test_all_prohibited_terms_blocked(self):
        for term in PROHIBITED_DIAGNOSTIC_TERMS:
            extractions = [{"name": "test", "value": f"Patient {term} something", "raw_ocr_output": ""}]
            result = _check_prohibited_content(extractions)
            assert len(result) == 0, f"Term '{term}' was not blocked"

    def test_prohibited_in_raw_ocr(self):
        extractions = [{"name": "test", "value": "safe_value", "raw_ocr_output": "You may have anaemia"}]
        result = _check_prohibited_content(extractions)
        assert len(result) == 0

    def test_case_insensitive_prohibition(self):
        extractions = [{"name": "test", "value": "DIABETIC condition", "raw_ocr_output": ""}]
        result = _check_prohibited_content(extractions)
        assert len(result) == 0

    def test_partial_match_prohibition(self):
        extractions = [{"name": "hba1c", "value": "5.6", "raw_ocr_output": "HbA1c: 5.6%"}]
        result = _check_prohibited_content(extractions)
        assert len(result) == 1

    def test_none_value_handled(self):
        extractions = [{"name": "test", "value": None, "raw_ocr_output": None}]
        result = _check_prohibited_content(extractions)
        assert len(result) == 1


class TestClassifierEdgeCases:
    def test_mixed_keywords(self):
        text = "hemoglobin prescription rx tab"
        result = _classify_by_keywords(text)
        assert result in (DocumentType.LAB_REPORT, DocumentType.PRESCRIPTION)

    def test_empty_text(self):
        result = _classify_by_keywords("")
        assert result == DocumentType.LAB_REPORT

    def test_case_insensitive_classification(self):
        text = "COMPLETE BLOOD COUNT HEMOGLOBIN WBC"
        result = _classify_by_keywords(text)
        assert result == DocumentType.LAB_REPORT


class TestUnlinkedQueue:
    @pytest.mark.asyncio
    async def test_add_and_get(self):
        queue = UnlinkedQueueService()
        await queue.add_to_queue("ingest-1", "path/to/file", "lab_report", [], "upload", "hash123")
        entries = await queue.get_queue()
        assert len(entries) == 1
        assert entries[0]["ingest_id"] == "ingest-1"

    @pytest.mark.asyncio
    async def test_remove(self):
        queue = UnlinkedQueueService()
        await queue.add_to_queue("ingest-2", "path", "prescription", [], "email", "hash456")
        removed = await queue.remove_from_queue("ingest-2")
        assert removed is not None
        assert removed["ingest_id"] == "ingest-2"
        remaining = await queue.get_queue()
        assert len(remaining) == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self):
        queue = UnlinkedQueueService()
        removed = await queue.remove_from_queue("nonexistent")
        assert removed is None

    @pytest.mark.asyncio
    async def test_queue_size(self):
        queue = UnlinkedQueueService()
        await queue.add_to_queue("a", "p", "t", [], "c", "h1")
        await queue.add_to_queue("b", "p", "t", [], "c", "h2")
        size = await queue.get_queue_size()
        assert size == 2
