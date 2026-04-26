import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.confidence import score_confidence


def test_low_confidence_returns_blank():
    result = score_confidence([{"name": "hb", "value": 11.8, "confidence": 0.60}])
    assert result[0]["value"] is None
    assert result[0]["requires_manual_entry"] is True


def test_high_confidence_passes_through():
    result = score_confidence([{"name": "hb", "value": 11.8, "confidence": 0.95}])
    assert result[0]["value"] == 11.8
    assert result[0]["requires_manual_entry"] is False


def test_medication_name_high_threshold():
    result = score_confidence([{"name": "medication_name", "value": "Metformin", "confidence": 0.90}])
    assert result[0]["value"] is None
    assert result[0]["requires_manual_entry"] is True


def test_medication_name_passes_at_threshold():
    result = score_confidence([{"name": "medication_name", "value": "Metformin", "confidence": 0.93}])
    assert result[0]["value"] == "Metformin"
    assert result[0]["requires_manual_entry"] is False


def test_dosage_high_threshold():
    result = score_confidence([{"name": "dosage", "value": "500mg", "confidence": 0.91}])
    assert result[0]["value"] is None
    assert result[0]["requires_manual_entry"] is True


def test_insulin_non_negotiable_threshold():
    result = score_confidence([{"name": "insulin", "value": "10U", "confidence": 0.98}])
    assert result[0]["value"] is None
    assert result[0]["requires_manual_entry"] is True


def test_insulin_passes_at_099():
    result = score_confidence([{"name": "insulin", "value": "10U", "confidence": 0.995}])
    assert result[0]["value"] == "10U"
    assert result[0]["requires_manual_entry"] is False


def test_date_lower_threshold():
    result = score_confidence([{"name": "date", "value": "2024-01-15", "confidence": 0.81}])
    assert result[0]["value"] == "2024-01-15"
    assert result[0]["requires_manual_entry"] is False


def test_lab_name_lowest_threshold():
    result = score_confidence([{"name": "lab_name", "value": "SRL Diagnostics", "confidence": 0.76}])
    assert result[0]["value"] == "SRL Diagnostics"
    assert result[0]["requires_manual_entry"] is False


def test_default_threshold_applied():
    result = score_confidence([{"name": "unknown_field", "value": "some_value", "confidence": 0.84}])
    assert result[0]["value"] is None
    assert result[0]["requires_manual_entry"] is True


def test_multiple_fields_scored_independently():
    extractions = [
        {"name": "hb", "value": 11.8, "confidence": 0.95},
        {"name": "medication_name", "value": "Aspirin", "confidence": 0.70},
        {"name": "date", "value": "2024-03-10", "confidence": 0.85},
    ]
    result = score_confidence(extractions)

    assert result[0]["value"] == 11.8
    assert result[0]["requires_manual_entry"] is False

    assert result[1]["value"] is None
    assert result[1]["requires_manual_entry"] is True

    assert result[2]["value"] == "2024-03-10"
    assert result[2]["requires_manual_entry"] is False


def test_empty_extractions():
    result = score_confidence([])
    assert result == []


def test_zero_confidence_always_blanked():
    result = score_confidence([{"name": "hb", "value": 12.0, "confidence": 0.0}])
    assert result[0]["value"] is None
    assert result[0]["requires_manual_entry"] is True
