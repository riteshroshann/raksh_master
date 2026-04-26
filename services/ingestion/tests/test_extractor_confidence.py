import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

sys.modules.setdefault("cv2", MagicMock())

from pipeline.extractor import _normalize_extraction, _compute_extraction_confidence
from models.enums import DocumentType


class TestSignalDerivedConfidence:
    def test_complete_lab_extraction_high_confidence(self):
        item = {
            "parameter_name": "hemoglobin",
            "value": "12.5",
            "unit": "g/dL",
            "reference_range_low": "12.0",
            "reference_range_high": "15.0",
            "test_date": "2024-01-15",
        }
        conf = _compute_extraction_confidence(
            "hemoglobin", "12.5", 12.5, "g/dL", item, DocumentType.LAB_REPORT
        )
        assert conf >= 0.90

    def test_missing_unit_lower_confidence(self):
        item = {
            "parameter_name": "hemoglobin",
            "value": "12.5",
        }
        conf = _compute_extraction_confidence(
            "hemoglobin", "12.5", 12.5, None, item, DocumentType.LAB_REPORT
        )
        assert conf < 0.90

    def test_missing_value_low_confidence(self):
        item = {
            "parameter_name": "hemoglobin",
        }
        conf = _compute_extraction_confidence(
            "hemoglobin", None, None, None, item, DocumentType.LAB_REPORT
        )
        assert conf < 0.75

    def test_unknown_field_name_penalty(self):
        item = {"value": "12.5", "unit": "g/dL"}
        conf = _compute_extraction_confidence(
            "unknown_field", "12.5", 12.5, "g/dL", item, DocumentType.LAB_REPORT
        )
        assert conf < 0.85

    def test_confidence_never_exceeds_098(self):
        item = {
            "parameter_name": "hemoglobin",
            "value": "12.5",
            "unit": "g/dL",
            "reference_range_low": "12.0",
            "reference_range_high": "15.0",
            "test_date": "2024-01-15",
        }
        conf = _compute_extraction_confidence(
            "hemoglobin", "12.5", 12.5, "g/dL", item, DocumentType.LAB_REPORT
        )
        assert conf <= 0.98

    def test_confidence_minimum_050(self):
        item = {}
        conf = _compute_extraction_confidence(
            "unknown_field", None, None, None, item, DocumentType.PRESCRIPTION
        )
        assert conf >= 0.50

    def test_prescription_no_bonus_without_unit(self):
        item = {"parameter_name": "metformin", "value": "500"}
        conf_no_unit = _compute_extraction_confidence(
            "metformin", "500", 500.0, None, item, DocumentType.LAB_REPORT
        )
        item_with_unit = {"parameter_name": "metformin", "value": "500", "unit": "mg"}
        conf_with_unit = _compute_extraction_confidence(
            "metformin", "500", 500.0, "mg", item_with_unit, DocumentType.LAB_REPORT
        )
        assert conf_with_unit > conf_no_unit


class TestNormalizationConfidenceIntegration:
    def test_normalize_sets_manual_entry_on_low_confidence(self):
        item = {"field_name": "some_field"}
        result = _normalize_extraction(item, DocumentType.LAB_REPORT)
        assert result["confidence"] < 0.70
        assert result["requires_manual_entry"] is True

    def test_normalize_complete_item_not_manual(self):
        item = {
            "parameter_name": "hemoglobin",
            "value": "12.5",
            "unit": "g/dL",
            "reference_range_low": "12.0",
            "reference_range_high": "15.0",
        }
        result = _normalize_extraction(item, DocumentType.LAB_REPORT)
        assert result["confidence"] >= 0.70
        assert result["requires_manual_entry"] is False

    def test_normalize_no_more_hardcoded_088(self):
        item = {
            "parameter_name": "hemoglobin",
            "value": "12.5",
            "unit": "g/dL",
        }
        result = _normalize_extraction(item, DocumentType.LAB_REPORT)
        assert result["confidence"] != 0.88
