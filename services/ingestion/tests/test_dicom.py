import sys
import os
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.dicom_parser import (
    is_dicom,
    parse_dicom_header,
    dicom_to_doc_type,
    dicom_metadata_to_extractions,
    deidentify_dicom_metadata,
    validate_dicom_integrity,
    DICOM_PREAMBLE_SIZE,
    DICOM_PREFIX,
    DICOM_PREFIX_OFFSET,
)


def _build_dicom_header(tags: dict) -> bytes:
    preamble = b"\x00" * DICOM_PREAMBLE_SIZE
    prefix = DICOM_PREFIX

    data = preamble + prefix

    for (group, element), (vr, value) in tags.items():
        tag_bytes = struct.pack("<HH", group, element)
        vr_bytes = vr.encode("ascii")

        if isinstance(value, str):
            value_bytes = value.encode("ascii")
            if len(value_bytes) % 2 != 0:
                value_bytes += b"\x20"
        elif isinstance(value, int):
            value_bytes = struct.pack("<H", value)
        else:
            value_bytes = value

        length_bytes = struct.pack("<H", len(value_bytes))
        data += tag_bytes + vr_bytes + length_bytes + value_bytes

    return data


def test_is_dicom_valid():
    data = b"\x00" * DICOM_PREAMBLE_SIZE + DICOM_PREFIX + b"\x00" * 100
    assert is_dicom(data) is True


def test_is_dicom_invalid():
    data = b"NOT A DICOM FILE" + b"\x00" * 200
    assert is_dicom(data) is False


def test_is_dicom_too_small():
    data = b"\x00" * 10
    assert is_dicom(data) is False


def test_parse_dicom_with_modality():
    tags = {
        (0x0008, 0x0060): ("CS", "CT"),
    }
    data = _build_dicom_header(tags)
    metadata = parse_dicom_header(data)
    assert metadata.get("modality") == "CT"


def test_parse_dicom_with_patient():
    tags = {
        (0x0010, 0x0010): ("PN", "Kumar^Ramesh"),
        (0x0010, 0x0020): ("LO", "MRN12345"),
        (0x0010, 0x0030): ("DA", "19850615"),
        (0x0010, 0x0040): ("CS", "M"),
    }
    data = _build_dicom_header(tags)
    metadata = parse_dicom_header(data)

    assert "patient_name" in metadata
    assert metadata["patient_name"] == "Kumar^Ramesh"
    assert metadata.get("patient_id") == "MRN12345"
    assert metadata.get("patient_sex") == "M"


def test_parse_dicom_with_study():
    tags = {
        (0x0008, 0x0020): ("DA", "20240115"),
        (0x0008, 0x1030): ("LO", "Chest CT"),
        (0x0008, 0x0080): ("LO", "Apollo Hospital"),
    }
    data = _build_dicom_header(tags)
    metadata = parse_dicom_header(data)

    assert metadata.get("study_date") == "20240115"
    assert metadata.get("study_description") == "Chest CT"
    assert metadata.get("institution_name") == "Apollo Hospital"


def test_parse_invalid_dicom():
    data = b"NOT DICOM DATA"
    metadata = parse_dicom_header(data)
    assert metadata == {}


def test_dicom_to_doc_type_ct():
    metadata = {"modality": "CT"}
    assert dicom_to_doc_type(metadata) == "ct_scan"


def test_dicom_to_doc_type_mr():
    metadata = {"modality": "MR"}
    assert dicom_to_doc_type(metadata) == "mri"


def test_dicom_to_doc_type_cr():
    metadata = {"modality": "CR"}
    assert dicom_to_doc_type(metadata) == "xray"


def test_dicom_to_doc_type_us():
    metadata = {"modality": "US"}
    assert dicom_to_doc_type(metadata) == "ultrasound"


def test_dicom_to_doc_type_mg():
    metadata = {"modality": "MG"}
    assert dicom_to_doc_type(metadata) == "mammogram"


def test_dicom_to_doc_type_unknown():
    metadata = {"modality": "XX"}
    assert dicom_to_doc_type(metadata) == "radiology_report"


def test_dicom_to_doc_type_missing():
    metadata = {}
    assert dicom_to_doc_type(metadata) == "radiology_report"


def test_metadata_to_extractions():
    metadata = {
        "modality": "CT",
        "study_date": "20240115",
        "study_description": "Chest CT",
        "rows": 512,
        "columns": 512,
        "slice_thickness": 1.25,
    }
    extractions = dicom_metadata_to_extractions(metadata)

    names = [e["name"] for e in extractions]
    assert "modality" in names
    assert "study_date" in names
    assert "rows" in names

    rows_extraction = next(e for e in extractions if e["name"] == "rows")
    assert rows_extraction["value_numeric"] == 512.0
    assert rows_extraction["unit"] == "pixels"
    assert rows_extraction["extraction_model"] == "dicom-header-parser"


def test_metadata_to_extractions_empty():
    extractions = dicom_metadata_to_extractions({})
    assert extractions == []


def test_deidentify_metadata():
    metadata = {
        "patient_name": "Ramesh Kumar",
        "patient_id": "MRN12345",
        "patient_dob": "19850615",
        "modality": "CT",
        "study_date": "20240115",
        "institution_name": "Apollo Hospital",
    }

    cleaned = deidentify_dicom_metadata(metadata)

    assert "patient_name" not in cleaned
    assert "patient_id" not in cleaned
    assert "patient_dob" not in cleaned
    assert "institution_name" not in cleaned
    assert cleaned["modality"] == "CT"
    assert cleaned["study_date"] == "20240115"


def test_deidentify_no_phi():
    metadata = {"modality": "MR", "study_date": "20240115"}
    cleaned = deidentify_dicom_metadata(metadata)
    assert cleaned == metadata


def test_validate_dicom_valid():
    tags = {
        (0x0008, 0x0016): ("UI", "1.2.840.10008.5.1.4.1.1.2"),
        (0x0020, 0x000D): ("UI", "1.2.3.4.5.6.7.8.9"),
    }
    data = _build_dicom_header(tags)
    result = validate_dicom_integrity(data)

    assert result["has_preamble"] is True
    assert result["has_prefix"] is True
    assert result["valid"] is True
    assert len(result["errors"]) == 0


def test_validate_dicom_too_small():
    data = b"\x00" * 10
    result = validate_dicom_integrity(data)

    assert result["valid"] is False
    assert "too small" in result["errors"][0]


def test_validate_dicom_missing_prefix():
    data = b"\x00" * DICOM_PREAMBLE_SIZE + b"XXXX" + b"\x00" * 100
    result = validate_dicom_integrity(data)

    assert result["valid"] is False
    assert result["has_prefix"] is False
