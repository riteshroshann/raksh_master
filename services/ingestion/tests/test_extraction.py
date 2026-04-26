import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.classifier import _classify_by_keywords, _is_dicom
from pipeline.validator import validate_before_save, _check_prohibited_content
from models.enums import DocumentType


def test_classify_lab_report_by_keywords():
    text = "complete blood count hemoglobin wbc rbc platelet reference range"
    result = _classify_by_keywords(text)
    assert result == DocumentType.LAB_REPORT


def test_classify_prescription_by_keywords():
    text = "rx prescription tablet metformin 500mg twice daily after food"
    result = _classify_by_keywords(text)
    assert result == DocumentType.PRESCRIPTION


def test_classify_discharge_summary_by_keywords():
    text = "discharge summary admitted on final diagnosis treatment given follow up"
    result = _classify_by_keywords(text)
    assert result == DocumentType.DISCHARGE_SUMMARY


def test_classify_pathology_by_keywords():
    text = "histopathology biopsy gross examination microscopic specimen malignant"
    result = _classify_by_keywords(text)
    assert result == DocumentType.PATHOLOGY_REPORT


def test_classify_referral_by_keywords():
    text = "referral letter referred to specialist opinion kindly see"
    result = _classify_by_keywords(text)
    assert result == DocumentType.REFERRAL_LETTER


def test_classify_insurance_by_keywords():
    text = "insurance claim pre-authorization tpa policy number cashless reimbursement"
    result = _classify_by_keywords(text)
    assert result == DocumentType.INSURANCE_BILLING


def test_classify_unknown_defaults_to_lab():
    text = "some random text without any medical keywords"
    result = _classify_by_keywords(text)
    assert result == DocumentType.LAB_REPORT


def test_dicom_detection_valid():
    contents = b"\x00" * 128 + b"DICM" + b"\x00" * 100
    assert _is_dicom(contents) is True


def test_dicom_detection_invalid():
    contents = b"%PDF-1.4 some pdf content"
    assert _is_dicom(contents) is False


def test_dicom_detection_too_short():
    contents = b"short"
    assert _is_dicom(contents) is False


def test_prohibited_content_removed():
    extractions = [
        {"name": "finding", "value": "You may have anaemia", "raw_ocr_output": ""},
        {"name": "hb", "value": "11.5", "raw_ocr_output": ""},
    ]
    result = _check_prohibited_content(extractions)
    assert len(result) == 1
    assert result[0]["name"] == "hb"


def test_diagnostic_label_removed():
    extractions = [
        {"name": "diagnosis", "value": "Diabetic", "raw_ocr_output": ""},
    ]
    result = _check_prohibited_content(extractions)
    assert len(result) == 0


def test_clean_content_passes_through():
    extractions = [
        {"name": "hb", "value": "11.8", "raw_ocr_output": "Hb: 11.8 g/dL"},
        {"name": "tsh", "value": "3.2", "raw_ocr_output": "TSH: 3.2 mIU/L"},
    ]
    result = _check_prohibited_content(extractions)
    assert len(result) == 2


def test_validator_preserves_field_structure():
    extractions = [
        {
            "name": "hb",
            "value": "11.8",
            "value_numeric": 11.8,
            "unit": "g/dL",
            "confidence": 0.95,
            "requires_manual_entry": False,
            "bounding_box": {"x": 10, "y": 20, "w": 100, "h": 30},
            "raw_ocr_output": "Hb: 11.8",
            "extraction_model": "tesseract-5",
        }
    ]
    result = validate_before_save(extractions, DocumentType.LAB_REPORT)
    assert len(result) == 1
    assert result[0]["name"] == "hb"
    assert result[0]["value"] == "11.8"
    assert result[0]["confidence"] == 0.95


def test_validator_empty_extractions():
    result = validate_before_save([], DocumentType.LAB_REPORT)
    assert result == []
