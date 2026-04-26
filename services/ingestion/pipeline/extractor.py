import io
import re
from typing import Any

import structlog
from PIL import Image

from config import settings
from models.enums import DocumentType, ExtractionBackend
from pipeline.preprocessing import prepare_for_ocr

logger = structlog.get_logger()

PRESCRIPTION_ABBREVIATION_HAZARDS = {
    "U": "units",
    "IU": "international units",
    "mcg": "micrograms",
    "ug": "micrograms",
}

DANGEROUS_ABBREVIATION_PATTERN = re.compile(r"\b(\d+)\s*U\b", re.IGNORECASE)


def _flag_abbreviation_hazards(raw_text: str, extractions: list[dict]) -> list[dict]:
    matches = DANGEROUS_ABBREVIATION_PATTERN.findall(raw_text)
    if matches:
        for extraction in extractions:
            if extraction.get("name") in ("dosage", "medication_name"):
                extraction["requires_manual_entry"] = True
                extraction["confidence"] = min(extraction.get("confidence", 0), 0.5)
                logger.warning(
                    "abbreviation_hazard_detected",
                    field=extraction["name"],
                    matches=matches,
                    detail="Potential U/units misread (10U -> 100 risk)",
                )
    return extractions


async def _extract_via_tesseract(image_bytes: bytes) -> tuple[str, list[dict]]:
    import pytesseract
    import numpy as np

    processed = prepare_for_ocr(image_bytes)
    pil_image = Image.fromarray(processed)

    raw_text = pytesseract.image_to_string(pil_image, lang="eng+hin")

    data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT)

    extractions = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        conf = float(data["conf"][i]) / 100.0 if data["conf"][i] != -1 else 0.0
        extractions.append({
            "name": "raw_field",
            "value": text,
            "confidence": conf,
            "bounding_box": {
                "x": data["left"][i],
                "y": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
            },
            "raw_ocr_output": text,
            "extraction_model": "tesseract-5",
        })

    return raw_text, extractions


async def _extract_via_anthropic(contents: bytes, doc_type: DocumentType) -> tuple[str, list[dict]]:
    import anthropic
    import base64

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    extraction_prompts = {
        DocumentType.LAB_REPORT: (
            "Extract all lab test parameters from this medical lab report. "
            "For each parameter, return: parameter_name, value (numeric if applicable), unit, "
            "reference_range_low, reference_range_high, and the test_date. "
            "Return as a JSON array of objects. Do not infer or guess any values not clearly visible."
        ),
        DocumentType.PRESCRIPTION: (
            "Extract all medications from this prescription. "
            "For each medication, return: medication_name, dosage, frequency, duration, "
            "and prescribing_doctor. Flag any ambiguous abbreviations especially U for units. "
            "Return as a JSON array. Do not infer values not clearly visible."
        ),
        DocumentType.DISCHARGE_SUMMARY: (
            "Extract from this discharge summary: diagnosis, treatment_received, "
            "medications_at_discharge (as array), follow_up_instructions, "
            "attending_doctor, admission_date, discharge_date. "
            "Return as JSON. Do not infer values not clearly visible."
        ),
        DocumentType.DOCTOR_NOTES: (
            "Extract from these clinical notes: chief_complaint, history, "
            "examination_findings, assessment, plan, doctor_name, date. "
            "Return as JSON. Do not infer values not clearly visible."
        ),
        DocumentType.PATHOLOGY_REPORT: (
            "Extract from this pathology report: specimen_type, gross_findings, "
            "microscopic_findings, diagnosis, staging (if present), doctor_name. "
            "Return as JSON. Do not infer values not clearly visible."
        ),
        DocumentType.REFERRAL_LETTER: (
            "Extract: referring_doctor, target_specialty, indication, patient_name, date. "
            "Return as JSON. Do not infer values not clearly visible."
        ),
        DocumentType.INSURANCE_BILLING: (
            "Extract: claim_number, policy_number, patient_name, diagnosis, "
            "procedure, amount, provider_name. "
            "Return as JSON. Do not infer values not clearly visible."
        ),
    }

    prompt = extraction_prompts.get(
        doc_type,
        "Extract all structured fields from this medical document as JSON. Do not infer values not clearly visible."
    )

    is_pdf = contents[:5] == b"%PDF-"

    if is_pdf:
        encoded = base64.standard_b64encode(contents).decode("utf-8")
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": encoded,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    else:
        encoded = base64.standard_b64encode(contents).decode("utf-8")
        media_type = "image/jpeg"
        if contents[:8] == b"\x89PNG\r\n\x1a\n":
            media_type = "image/png"
        elif contents[:4] == b"II*\x00" or contents[:4] == b"MM\x00*":
            media_type = "image/tiff"

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": encoded,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )

    raw_text = message.content[0].text
    extractions = _parse_vlm_response(raw_text, doc_type)

    return raw_text, extractions


def _parse_vlm_response(raw_text: str, doc_type: DocumentType) -> list[dict]:
    import json

    json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if not json_match:
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return [_normalize_extraction(parsed, doc_type)]
            except json.JSONDecodeError:
                return []
        return []

    try:
        parsed_list = json.loads(json_match.group())
    except json.JSONDecodeError:
        return []

    return [_normalize_extraction(item, doc_type) for item in parsed_list]


def _normalize_extraction(item: dict[str, Any], doc_type: DocumentType) -> dict:
    name = (
        item.get("parameter_name")
        or item.get("medication_name")
        or item.get("test_name")
        or item.get("field_name")
        or item.get("name")
        or "unknown_field"
    )

    value = item.get("value") or item.get("dosage") or item.get("result")
    value_numeric = None
    if value is not None:
        try:
            value_numeric = float(str(value).replace(",", ""))
            value = str(value)
        except (ValueError, TypeError):
            value = str(value) if value else None

    unit = item.get("unit") or item.get("units") or None

    confidence = _compute_extraction_confidence(name, value, value_numeric, unit, item, doc_type)

    return {
        "name": str(name).lower().replace(" ", "_"),
        "value": value,
        "value_numeric": value_numeric,
        "unit": unit,
        "confidence": confidence,
        "requires_manual_entry": confidence < 0.70,
        "bounding_box": item.get("bounding_box"),
        "raw_ocr_output": str(item),
        "extraction_model": "anthropic-claude-sonnet",
    }


def _compute_extraction_confidence(
    name: str,
    value: Any,
    value_numeric: float | None,
    unit: str | None,
    raw_item: dict,
    doc_type: DocumentType,
) -> float:
    score = 0.50

    if name and name != "unknown_field":
        score += 0.12

    if value is not None and str(value).strip():
        score += 0.12

    if value_numeric is not None:
        score += 0.08

    if unit is not None:
        score += 0.06

    ref_low = raw_item.get("reference_range_low")
    ref_high = raw_item.get("reference_range_high")
    if ref_low is not None or ref_high is not None:
        score += 0.06

    if doc_type == DocumentType.LAB_REPORT:
        if value_numeric is not None and unit:
            score += 0.04

    if raw_item.get("test_date") or raw_item.get("date"):
        score += 0.02

    return round(min(score, 0.98), 2)


async def _extract_dicom_metadata(contents: bytes) -> list[dict]:
    metadata_fields = []

    if len(contents) < 132 or contents[128:132] != b"DICM":
        return metadata_fields

    metadata_fields.append({
        "name": "modality",
        "value": "unknown",
        "confidence": 0.5,
        "requires_manual_entry": True,
        "extraction_model": "dicom-parser",
    })

    return metadata_fields


async def extract_fields(contents: bytes, doc_type: DocumentType) -> list[dict]:
    logger.info("extraction_started", doc_type=doc_type.value, size_bytes=len(contents))

    if doc_type in {
        DocumentType.XRAY, DocumentType.MRI, DocumentType.CT_SCAN,
        DocumentType.ULTRASOUND, DocumentType.ECG_EEG,
    }:
        extractions = await _extract_dicom_metadata(contents)
        logger.info("extraction_completed", doc_type=doc_type.value, method="dicom", num_fields=len(extractions))
        return extractions

    backend = ExtractionBackend(settings.extraction_backend)

    if backend == ExtractionBackend.API and settings.anthropic_api_key:
        try:
            raw_text, extractions = await _extract_via_anthropic(contents, doc_type)
            extractions = _flag_abbreviation_hazards(raw_text, extractions)
            logger.info("extraction_completed", doc_type=doc_type.value, method="anthropic", num_fields=len(extractions))
            return extractions
        except Exception as exc:
            logger.error("anthropic_extraction_failed", error=str(exc), doc_type=doc_type.value)

    try:
        raw_text, extractions = await _extract_via_tesseract(contents)
        extractions = _flag_abbreviation_hazards(raw_text, extractions)
        logger.info("extraction_completed", doc_type=doc_type.value, method="tesseract", num_fields=len(extractions))
        return extractions
    except Exception as exc:
        logger.error("tesseract_extraction_failed", error=str(exc), doc_type=doc_type.value)
        return []
