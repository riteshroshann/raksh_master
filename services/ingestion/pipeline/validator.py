import structlog

from models.enums import DocumentType

logger = structlog.get_logger()

REQUIRED_FIELDS_BY_TYPE = {
    DocumentType.LAB_REPORT: {"parameter_name", "value", "unit"},
    DocumentType.PRESCRIPTION: {"medication_name", "dosage"},
    DocumentType.DISCHARGE_SUMMARY: {"diagnosis"},
    DocumentType.DOCTOR_NOTES: set(),
    DocumentType.PATHOLOGY_REPORT: {"specimen_type", "diagnosis"},
    DocumentType.REFERRAL_LETTER: {"referring_doctor", "target_specialty"},
    DocumentType.INSURANCE_BILLING: {"claim_number"},
    DocumentType.RADIOLOGY_REPORT: {"findings"},
}

PROHIBITED_DIAGNOSTIC_TERMS = [
    "you may have",
    "you might have",
    "suggests",
    "indicates",
    "consistent with",
    "diagnosed with",
    "diabetic",
    "hypothyroid",
    "anaemic",
    "anemic",
    "consult a",
    "see a doctor",
    "your ldl is high",
    "your hb is low",
]


def _check_prohibited_content(extractions: list[dict]) -> list[dict]:
    sanitized = []
    for field in extractions:
        value = str(field.get("value", "") or "").lower()
        raw = str(field.get("raw_ocr_output", "") or "").lower()

        contains_prohibited = any(
            term in value or term in raw
            for term in PROHIBITED_DIAGNOSTIC_TERMS
        )

        if contains_prohibited:
            logger.warning(
                "prohibited_content_removed",
                field_name=field.get("name"),
                detail="Constitutional prohibition: no diagnostic labels or suggestions",
            )
            continue

        sanitized.append(field)

    return sanitized


def validate_before_save(extractions: list[dict], doc_type: DocumentType) -> list[dict]:
    validated = _check_prohibited_content(extractions)

    result = []
    for field in validated:
        clean_field = {
            "name": field.get("name", "unknown_field"),
            "value": field.get("value"),
            "value_numeric": field.get("value_numeric"),
            "unit": field.get("unit"),
            "confidence": field.get("confidence", 0.0),
            "requires_manual_entry": field.get("requires_manual_entry", False),
            "bounding_box": field.get("bounding_box"),
            "raw_ocr_output": field.get("raw_ocr_output"),
            "extraction_model": field.get("extraction_model"),
        }
        result.append(clean_field)

    logger.info(
        "validation_completed",
        doc_type=doc_type.value,
        input_count=len(extractions),
        output_count=len(result),
    )

    return result
