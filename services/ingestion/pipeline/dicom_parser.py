import io
import struct
from datetime import datetime, date
from typing import Optional

import structlog

logger = structlog.get_logger()


DICOM_PREAMBLE_SIZE = 128
DICOM_PREFIX = b"DICM"
DICOM_PREFIX_OFFSET = 128


CRITICAL_TAGS = {
    (0x0010, 0x0010): "patient_name",
    (0x0010, 0x0020): "patient_id",
    (0x0010, 0x0030): "patient_dob",
    (0x0010, 0x0040): "patient_sex",
    (0x0008, 0x0060): "modality",
    (0x0008, 0x0020): "study_date",
    (0x0008, 0x0030): "study_time",
    (0x0008, 0x0050): "accession_number",
    (0x0008, 0x1030): "study_description",
    (0x0008, 0x103E): "series_description",
    (0x0020, 0x000D): "study_instance_uid",
    (0x0020, 0x000E): "series_instance_uid",
    (0x0008, 0x0016): "sop_class_uid",
    (0x0008, 0x0018): "sop_instance_uid",
    (0x0008, 0x0080): "institution_name",
    (0x0008, 0x0090): "referring_physician",
    (0x0028, 0x0010): "rows",
    (0x0028, 0x0011): "columns",
    (0x0028, 0x0100): "bits_allocated",
    (0x0028, 0x0101): "bits_stored",
    (0x0028, 0x0004): "photometric_interpretation",
    (0x0018, 0x0015): "body_part_examined",
    (0x0018, 0x0050): "slice_thickness",
    (0x0018, 0x0060): "kvp",
    (0x0018, 0x1151): "tube_current",
    (0x0020, 0x0013): "instance_number",
    (0x0020, 0x0032): "image_position",
    (0x0020, 0x0037): "image_orientation",
}


MODALITY_TO_DOC_TYPE = {
    "CR": "xray",
    "DX": "xray",
    "CT": "ct_scan",
    "MR": "mri",
    "US": "ultrasound",
    "MG": "mammogram",
    "NM": "radiology_report",
    "PT": "radiology_report",
    "XA": "radiology_report",
    "OT": "radiology_report",
}

PHI_TAGS = {
    (0x0010, 0x0010),
    (0x0010, 0x0020),
    (0x0010, 0x0030),
    (0x0010, 0x1000),
    (0x0010, 0x1001),
    (0x0010, 0x1010),
    (0x0010, 0x1020),
    (0x0010, 0x1030),
    (0x0010, 0x1040),
    (0x0010, 0x2154),
    (0x0008, 0x0080),
    (0x0008, 0x0081),
    (0x0008, 0x0090),
    (0x0008, 0x1070),
    (0x0008, 0x1048),
}


def is_dicom(data: bytes) -> bool:
    if len(data) < DICOM_PREFIX_OFFSET + 4:
        return False

    return data[DICOM_PREFIX_OFFSET:DICOM_PREFIX_OFFSET + 4] == DICOM_PREFIX


def parse_dicom_header(data: bytes) -> dict:
    metadata = {}

    if not is_dicom(data):
        logger.warning("not_valid_dicom")
        return metadata

    try:
        offset = DICOM_PREFIX_OFFSET + 4
        max_offset = min(len(data), 65536)

        while offset < max_offset - 8:
            group = struct.unpack_from("<H", data, offset)[0]
            element = struct.unpack_from("<H", data, offset + 2)[0]

            tag = (group, element)

            vr = data[offset + 4:offset + 6].decode("ascii", errors="ignore")

            if vr in ("OB", "OW", "OF", "SQ", "UC", "UN", "UR", "UT"):
                if offset + 12 > len(data):
                    break
                value_length = struct.unpack_from("<I", data, offset + 8)[0]
                value_offset = offset + 12
            else:
                if offset + 8 > len(data):
                    break
                value_length = struct.unpack_from("<H", data, offset + 6)[0]
                value_offset = offset + 8

            if value_length == 0xFFFFFFFF:
                offset = value_offset
                continue

            if value_length > 0 and value_offset + value_length <= len(data):
                raw_value = data[value_offset:value_offset + value_length]

                if tag in CRITICAL_TAGS:
                    field_name = CRITICAL_TAGS[tag]

                    if vr in ("US", "SS"):
                        if len(raw_value) >= 2:
                            metadata[field_name] = struct.unpack_from("<H", raw_value)[0]
                    elif vr in ("UL", "SL"):
                        if len(raw_value) >= 4:
                            metadata[field_name] = struct.unpack_from("<I", raw_value)[0]
                    elif vr == "FL":
                        if len(raw_value) >= 4:
                            metadata[field_name] = struct.unpack_from("<f", raw_value)[0]
                    elif vr == "FD":
                        if len(raw_value) >= 8:
                            metadata[field_name] = struct.unpack_from("<d", raw_value)[0]
                    else:
                        decoded = raw_value.decode("ascii", errors="replace").strip().rstrip("\x00")
                        metadata[field_name] = decoded

                offset = value_offset + value_length
            else:
                break

    except Exception as exc:
        logger.error("dicom_parse_error", error=str(exc))

    logger.info(
        "dicom_header_parsed",
        tags_found=len(metadata),
        modality=metadata.get("modality"),
        study_date=metadata.get("study_date"),
    )

    return metadata


def dicom_to_doc_type(metadata: dict) -> str:
    modality = metadata.get("modality", "")
    return MODALITY_TO_DOC_TYPE.get(modality, "radiology_report")


def dicom_metadata_to_extractions(metadata: dict) -> list[dict]:
    extractions = []

    direct_fields = [
        "modality", "study_date", "study_description",
        "series_description", "body_part_examined",
        "institution_name", "referring_physician",
        "accession_number",
    ]

    for field in direct_fields:
        if field in metadata:
            extractions.append({
                "name": field,
                "value": str(metadata[field]),
                "value_numeric": None,
                "unit": None,
                "confidence": 0.98,
                "requires_manual_entry": False,
                "extraction_model": "dicom-header-parser",
                "raw_ocr_output": None,
            })

    numeric_fields = {
        "rows": ("pixels", None),
        "columns": ("pixels", None),
        "bits_allocated": ("bits", None),
        "bits_stored": ("bits", None),
        "slice_thickness": ("mm", None),
        "kvp": ("kV", None),
        "tube_current": ("mA", None),
    }

    for field, (unit, _) in numeric_fields.items():
        if field in metadata:
            try:
                val = float(metadata[field])
                extractions.append({
                    "name": field,
                    "value": str(metadata[field]),
                    "value_numeric": val,
                    "unit": unit,
                    "confidence": 0.99,
                    "requires_manual_entry": False,
                    "extraction_model": "dicom-header-parser",
                    "raw_ocr_output": None,
                })
            except (ValueError, TypeError):
                pass

    return extractions


def deidentify_dicom_metadata(metadata: dict) -> dict:
    cleaned = dict(metadata)

    phi_field_names = set()
    for tag, field_name in CRITICAL_TAGS.items():
        if tag in PHI_TAGS:
            phi_field_names.add(field_name)

    for field_name in phi_field_names:
        if field_name in cleaned:
            del cleaned[field_name]

    return cleaned


def validate_dicom_integrity(data: bytes) -> dict:
    result = {
        "valid": False,
        "has_preamble": False,
        "has_prefix": False,
        "file_size": len(data),
        "errors": [],
    }

    if len(data) < DICOM_PREFIX_OFFSET + 4:
        result["errors"].append("File too small for DICOM format")
        return result

    result["has_preamble"] = True

    if data[DICOM_PREFIX_OFFSET:DICOM_PREFIX_OFFSET + 4] == DICOM_PREFIX:
        result["has_prefix"] = True
    else:
        result["errors"].append("Missing DICM prefix")
        return result

    metadata = parse_dicom_header(data)

    if not metadata.get("sop_class_uid"):
        result["errors"].append("Missing SOP Class UID")

    if not metadata.get("study_instance_uid"):
        result["errors"].append("Missing Study Instance UID")

    if not result["errors"]:
        result["valid"] = True

    result["metadata_tags_found"] = len(metadata)
    result["modality"] = metadata.get("modality")
    result["study_date"] = metadata.get("study_date")

    return result
