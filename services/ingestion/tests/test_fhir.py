import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.fhir_mapper import FHIRMapper, HL7v2Parser


def test_build_patient_basic():
    mapper = FHIRMapper()
    member = {"id": "abc-123", "name": "Ramesh Kumar", "dob": "1985-06-15", "sex": "male"}

    patient = mapper.build_patient(member)

    assert patient["resourceType"] == "Patient"
    assert patient["id"] == "abc-123"
    assert patient["name"][0]["text"] == "Ramesh Kumar"
    assert patient["birthDate"] == "1985-06-15"
    assert patient["gender"] == "male"


def test_build_patient_female():
    mapper = FHIRMapper()
    member = {"id": "def-456", "name": "Priya Sharma", "dob": "1990-03-22", "sex": "female"}

    patient = mapper.build_patient(member)
    assert patient["gender"] == "female"


def test_build_observation_numeric():
    mapper = FHIRMapper()
    param = {
        "id": "obs-1",
        "parameter_name": "hemoglobin",
        "value_numeric": 11.8,
        "unit": "g/dL",
        "test_date": "2024-01-15",
        "indian_range_low": 11.5,
        "indian_range_high": 16.0,
        "flag": "normal",
    }

    observation = mapper.build_observation(param, "patient-123")

    assert observation["resourceType"] == "Observation"
    assert observation["status"] == "final"
    assert observation["valueQuantity"]["value"] == 11.8
    assert observation["valueQuantity"]["unit"] == "g/dL"
    assert observation["subject"]["reference"] == "Patient/patient-123"
    assert len(observation["referenceRange"]) == 1
    assert observation["referenceRange"][0]["low"]["value"] == 11.5


def test_build_observation_text():
    mapper = FHIRMapper()
    param = {"id": "obs-2", "parameter_name": "blood_group", "value_text": "B+", "test_date": "2024-01-15"}

    observation = mapper.build_observation(param, "patient-123")
    assert observation["valueString"] == "B+"


def test_build_observation_high_flag():
    mapper = FHIRMapper()
    param = {"id": "obs-3", "parameter_name": "glucose", "value_numeric": 250.0, "unit": "mg/dL", "test_date": "2024-01-15", "flag": "above_range"}

    observation = mapper.build_observation(param, "patient-123")
    assert observation["interpretation"][0]["coding"][0]["code"] == "H"


def test_build_observation_low_flag():
    mapper = FHIRMapper()
    param = {"id": "obs-4", "parameter_name": "hemoglobin", "value_numeric": 8.0, "unit": "g/dL", "test_date": "2024-01-15", "flag": "below_range"}

    observation = mapper.build_observation(param, "patient-123")
    assert observation["interpretation"][0]["coding"][0]["code"] == "L"


def test_build_diagnostic_report():
    mapper = FHIRMapper()
    document = {"id": "doc-1", "doc_type": "lab_report", "doc_date": "2024-01-15", "confirmed_at": "2024-01-16", "doctor_name": "Dr. Patel"}
    parameters = [{"id": "obs-1"}, {"id": "obs-2"}]

    report = mapper.build_diagnostic_report(document, parameters, "patient-123")

    assert report["resourceType"] == "DiagnosticReport"
    assert report["status"] == "final"
    assert len(report["result"]) == 2
    assert report["performer"][0]["display"] == "Dr. Patel"


def test_build_medication_request():
    mapper = FHIRMapper()
    medication = {
        "id": "med-1",
        "parameter_name": "metformin",
        "value_text": "500mg twice daily",
        "frequency": "BD",
        "doctor_name": "Dr. Sharma",
    }

    request = mapper.build_medication_request(medication, "patient-123")

    assert request["resourceType"] == "MedicationRequest"
    assert request["status"] == "active"
    assert request["intent"] == "order"


def test_build_document_reference():
    mapper = FHIRMapper()
    document = {"id": "doc-1", "doc_type": "lab_report", "created_at": "2024-01-15", "file_path": "member1/report.pdf"}

    doc_ref = mapper.build_document_reference(document, "patient-123")

    assert doc_ref["resourceType"] == "DocumentReference"
    assert doc_ref["status"] == "current"


def test_build_imaging_study():
    mapper = FHIRMapper()
    document = {"id": "img-1", "doc_type": "xray", "doc_date": "2024-01-15", "file_path": "member1/xray.dcm"}

    study = mapper.build_imaging_study(document, "patient-123")

    assert study["resourceType"] == "ImagingStudy"
    assert study["status"] == "available"


def test_build_consent_active():
    mapper = FHIRMapper()
    consent_record = {"id": "consent-1", "account_id": "acc-1", "purpose": "data_storage", "granted_at": "2024-01-15", "withdrawn_at": None}

    consent = mapper.build_consent(consent_record)

    assert consent["resourceType"] == "Consent"
    assert consent["status"] == "active"


def test_build_consent_withdrawn():
    mapper = FHIRMapper()
    consent_record = {"id": "consent-2", "account_id": "acc-1", "purpose": "analytics", "granted_at": "2024-01-15", "withdrawn_at": "2024-06-01"}

    consent = mapper.build_consent(consent_record)
    assert consent["status"] == "rejected"


def test_build_bundle():
    mapper = FHIRMapper()
    entries = [{"resourceType": "Patient", "id": "p1"}, {"resourceType": "Observation", "id": "o1"}]

    bundle = mapper.build_bundle(entries, "document")

    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "document"
    assert len(bundle["entry"]) == 2
    assert bundle["entry"][0]["resource"]["resourceType"] == "Patient"


def test_build_lab_report_bundle():
    mapper = FHIRMapper()
    member = {"id": "m1", "name": "Test Patient", "dob": "1990-01-01", "sex": "male"}
    document = {"id": "d1", "doc_type": "lab_report", "doc_date": "2024-01-15", "confirmed_at": "2024-01-16", "doctor_name": "Dr. Test", "created_at": "2024-01-15", "file_path": "test/path"}
    parameters = [
        {"id": "p1", "parameter_name": "hemoglobin", "value_numeric": 12.0, "unit": "g/dL", "test_date": "2024-01-15", "flag": "normal", "indian_range_low": 11.5, "indian_range_high": 16.0},
        {"id": "p2", "parameter_name": "tsh", "value_numeric": 3.5, "unit": "mIU/L", "test_date": "2024-01-15", "flag": "normal"},
    ]

    bundle = mapper.build_lab_report_bundle(member, document, parameters)

    assert bundle["resourceType"] == "Bundle"
    assert len(bundle["entry"]) == 5


def test_gender_mapping():
    mapper = FHIRMapper()
    assert mapper._map_gender("male") == "male"
    assert mapper._map_gender("female") == "female"
    assert mapper._map_gender("other") == "other"
    assert mapper._map_gender("nonbinary") == "unknown"


def test_hl7_oru_parsing():
    parser = HL7v2Parser()
    raw_message = (
        "MSH|^~\\&|LAB_SYSTEM|HOSPITAL|RAKSH|RAKSH|20240115120000||ORU^R01|MSG001|P|2.5\r"
        "PID|||12345^^^MRN||Kumar^Ramesh||19850615|M\r"
        "OBX|1|NM|718-7^Hemoglobin||11.8|g/dL|11.5-16.0|N|||F|||20240115\r"
        "OBX|2|NM|2947-0^TSH||3.5|mIU/L|0.5-5.5|N|||F|||20240115\r"
    )

    parsed = parser.parse_oru(raw_message)

    assert parsed["message_type"] == "ORU^R01"
    assert parsed["sending_facility"] == "HOSPITAL"
    assert parsed["patient"]["id"] == "12345"
    assert parsed["patient"]["name"] == "Ramesh Kumar"
    assert parsed["patient"]["dob"] == "19850615"
    assert parsed["patient"]["sex"] == "M"
    assert len(parsed["observations"]) == 2


def test_hl7_oru_to_extractions():
    parser = HL7v2Parser()
    raw_message = (
        "MSH|^~\\&|LAB|HOSP|RAKSH|RAKSH|20240115||ORU^R01|MSG002|P|2.5\r"
        "PID|||999^^^MRN||Test^Patient||19900101|F\r"
        "OBX|1|NM|718-7^Hemoglobin||12.5|g/dL|11.5-16.0|N|||F|||20240115\r"
    )

    parsed = parser.parse_oru(raw_message)
    extractions = parser.oru_to_extractions(parsed)

    assert len(extractions) == 1
    assert extractions[0]["name"] == "hemoglobin"
    assert extractions[0]["value_numeric"] == 12.5
    assert extractions[0]["unit"] == "g/dL"
    assert extractions[0]["lab_range_low"] == 11.5
    assert extractions[0]["lab_range_high"] == 16.0
    assert extractions[0]["confidence"] == 0.95
    assert extractions[0]["extraction_model"] == "hl7v2-parser"


def test_hl7_adt_parsing():
    parser = HL7v2Parser()
    raw_message = (
        "MSH|^~\\&|ADT|HOSP|RAKSH|RAKSH|20240115||ADT^A01|MSG003|P|2.5\r"
        "PID|||54321^^^MRN||Sharma^Priya||19900322|F|||123 Main St\r"
        "PV1||I|Ward3|||Dr^Patel\r"
    )

    parsed = parser.parse_adt(raw_message)

    assert "ADT" in parsed["message_type"]
    assert parsed["patient"]["id"] == "54321"
    assert parsed["patient"]["name"] == "Priya Sharma"


def test_hl7_name_parsing():
    parser = HL7v2Parser()

    assert parser._parse_hl7_name("Kumar^Ramesh") == "Ramesh Kumar"
    assert parser._parse_hl7_name("SingleName") == "SingleName"
    assert parser._parse_hl7_name("") == ""


def test_hl7_empty_message():
    parser = HL7v2Parser()
    parsed = parser.parse_oru("")

    assert parsed["message_type"] == ""
    assert len(parsed["observations"]) == 0
