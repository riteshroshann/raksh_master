from datetime import datetime
from typing import Optional, Any
from uuid import UUID

import structlog

logger = structlog.get_logger()


class FHIRMapper:
    def build_patient(self, member: dict) -> dict:
        return {
            "resourceType": "Patient",
            "id": str(member.get("id", "")),
            "name": [{"use": "official", "text": member.get("name", "")}],
            "birthDate": str(member.get("dob", "")),
            "gender": self._map_gender(member.get("sex", "other")),
        }

    def build_observation(self, parameter: dict, patient_id: str) -> dict:
        observation = {
            "resourceType": "Observation",
            "id": str(parameter.get("id", "")),
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "display": parameter.get("parameter_name", ""),
                }],
                "text": parameter.get("parameter_name", ""),
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": str(parameter.get("test_date", "")),
        }

        if parameter.get("value_numeric") is not None:
            observation["valueQuantity"] = {
                "value": parameter["value_numeric"],
                "unit": parameter.get("unit", ""),
                "system": "http://unitsofmeasure.org",
            }
        elif parameter.get("value_text"):
            observation["valueString"] = parameter["value_text"]

        reference_range_entries = []
        if parameter.get("indian_range_low") is not None or parameter.get("indian_range_high") is not None:
            indian_range = {"text": "Indian reference range (ICMR)"}
            if parameter.get("indian_range_low") is not None:
                indian_range["low"] = {"value": parameter["indian_range_low"], "unit": parameter.get("unit", "")}
            if parameter.get("indian_range_high") is not None:
                indian_range["high"] = {"value": parameter["indian_range_high"], "unit": parameter.get("unit", "")}
            reference_range_entries.append(indian_range)

        if parameter.get("lab_range_low") is not None or parameter.get("lab_range_high") is not None:
            lab_range = {"text": "Lab reference range"}
            if parameter.get("lab_range_low") is not None:
                lab_range["low"] = {"value": parameter["lab_range_low"], "unit": parameter.get("unit", "")}
            if parameter.get("lab_range_high") is not None:
                lab_range["high"] = {"value": parameter["lab_range_high"], "unit": parameter.get("unit", "")}
            reference_range_entries.append(lab_range)

        if reference_range_entries:
            observation["referenceRange"] = reference_range_entries

        flag = parameter.get("flag")
        if flag == "above_range":
            observation["interpretation"] = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "H", "display": "High"}]}]
        elif flag == "below_range":
            observation["interpretation"] = [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", "code": "L", "display": "Low"}]}]

        return observation

    def build_diagnostic_report(
        self,
        document: dict,
        parameters: list[dict],
        patient_id: str,
    ) -> dict:
        observation_refs = [
            {"reference": f"Observation/{p.get('id', '')}"}
            for p in parameters
        ]

        return {
            "resourceType": "DiagnosticReport",
            "id": str(document.get("id", "")),
            "status": "final",
            "code": {"text": document.get("doc_type", "lab_report")},
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": str(document.get("doc_date", "")),
            "issued": str(document.get("confirmed_at", "")),
            "result": observation_refs,
            "performer": [{"display": document.get("doctor_name", "")}] if document.get("doctor_name") else [],
        }

    def build_medication_request(self, medication: dict, patient_id: str) -> dict:
        return {
            "resourceType": "MedicationRequest",
            "id": str(medication.get("id", "")),
            "status": "active",
            "intent": "order",
            "medicationCodeableConcept": {
                "text": medication.get("medication_name", medication.get("parameter_name", "")),
            },
            "subject": {"reference": f"Patient/{patient_id}"},
            "dosageInstruction": [{
                "text": medication.get("dosage", medication.get("value_text", "")),
                "timing": {"code": {"text": medication.get("frequency", "")}},
            }],
            "requester": {"display": medication.get("doctor_name", "")},
        }

    def build_document_reference(self, document: dict, patient_id: str) -> dict:
        return {
            "resourceType": "DocumentReference",
            "id": str(document.get("id", "")),
            "status": "current",
            "type": {"text": document.get("doc_type", "")},
            "subject": {"reference": f"Patient/{patient_id}"},
            "date": str(document.get("created_at", "")),
            "content": [{
                "attachment": {
                    "contentType": "application/pdf",
                    "url": document.get("file_path", ""),
                },
            }],
        }

    def build_imaging_study(self, document: dict, patient_id: str) -> dict:
        return {
            "resourceType": "ImagingStudy",
            "id": str(document.get("id", "")),
            "status": "available",
            "subject": {"reference": f"Patient/{patient_id}"},
            "started": str(document.get("doc_date", "")),
            "modality": [{"system": "http://dicom.nema.org/resources/ontology/DCM", "code": document.get("doc_type", "").upper()}],
            "endpoint": [{"reference": document.get("file_path", "")}],
        }

    def build_consent(self, consent_record: dict) -> dict:
        return {
            "resourceType": "Consent",
            "id": str(consent_record.get("id", "")),
            "status": "active" if not consent_record.get("withdrawn_at") else "rejected",
            "scope": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/consentscope", "code": "patient-privacy"}]},
            "category": [{"coding": [{"system": "http://loinc.org", "code": "59284-0"}]}],
            "patient": {"reference": f"Patient/{consent_record.get('account_id', '')}"},
            "dateTime": str(consent_record.get("granted_at", "")),
            "provision": {"type": "permit", "purpose": [{"display": consent_record.get("purpose", "")}]},
        }

    def build_bundle(self, entries: list[dict], bundle_type: str = "document") -> dict:
        return {
            "resourceType": "Bundle",
            "type": bundle_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "entry": [{"resource": entry} for entry in entries],
        }

    def build_lab_report_bundle(
        self,
        member: dict,
        document: dict,
        parameters: list[dict],
    ) -> dict:
        patient_id = str(member.get("id", ""))

        patient = self.build_patient(member)
        observations = [self.build_observation(p, patient_id) for p in parameters]
        diagnostic_report = self.build_diagnostic_report(document, parameters, patient_id)
        doc_ref = self.build_document_reference(document, patient_id)

        entries = [patient, diagnostic_report, doc_ref] + observations

        bundle = self.build_bundle(entries, "document")

        logger.info(
            "fhir_bundle_built",
            bundle_type="lab_report",
            entry_count=len(entries),
            patient_id=patient_id,
        )

        return bundle

    def build_prescription_bundle(
        self,
        member: dict,
        document: dict,
        medications: list[dict],
    ) -> dict:
        patient_id = str(member.get("id", ""))

        patient = self.build_patient(member)
        med_requests = [self.build_medication_request(m, patient_id) for m in medications]
        doc_ref = self.build_document_reference(document, patient_id)

        entries = [patient, doc_ref] + med_requests
        return self.build_bundle(entries, "document")

    def _map_gender(self, sex: str) -> str:
        mapping = {"male": "male", "female": "female", "other": "other"}
        return mapping.get(sex.lower(), "unknown")


class HL7v2Parser:
    def parse_oru(self, raw_message: str) -> dict:
        segments = raw_message.strip().split("\r")
        parsed = {"message_type": "", "patient": {}, "observations": []}

        for segment in segments:
            fields = segment.split("|")
            segment_type = fields[0] if fields else ""

            if segment_type == "MSH":
                parsed["message_type"] = fields[8] if len(fields) > 8 else ""
                parsed["sending_facility"] = fields[3] if len(fields) > 3 else ""
                parsed["message_datetime"] = fields[6] if len(fields) > 6 else ""

            elif segment_type == "PID":
                parsed["patient"]["id"] = fields[3].split("^")[0] if len(fields) > 3 else ""
                parsed["patient"]["name"] = self._parse_hl7_name(fields[5]) if len(fields) > 5 else ""
                parsed["patient"]["dob"] = fields[7] if len(fields) > 7 else ""
                parsed["patient"]["sex"] = fields[8] if len(fields) > 8 else ""

            elif segment_type == "OBX":
                observation = {
                    "set_id": fields[1] if len(fields) > 1 else "",
                    "value_type": fields[2] if len(fields) > 2 else "",
                    "identifier": fields[3].split("^")[0] if len(fields) > 3 else "",
                    "identifier_text": fields[3].split("^")[1] if len(fields) > 3 and "^" in fields[3] else "",
                    "value": fields[5] if len(fields) > 5 else "",
                    "units": fields[6].split("^")[0] if len(fields) > 6 else "",
                    "reference_range": fields[7] if len(fields) > 7 else "",
                    "abnormal_flag": fields[8] if len(fields) > 8 else "",
                    "status": fields[11] if len(fields) > 11 else "",
                    "observation_datetime": fields[14] if len(fields) > 14 else "",
                }
                parsed["observations"].append(observation)

        logger.info(
            "hl7_oru_parsed",
            patient_id=parsed["patient"].get("id"),
            observation_count=len(parsed["observations"]),
        )

        return parsed

    def parse_adt(self, raw_message: str) -> dict:
        segments = raw_message.strip().split("\r")
        parsed = {"message_type": "", "patient": {}, "visit": {}}

        for segment in segments:
            fields = segment.split("|")
            segment_type = fields[0] if fields else ""

            if segment_type == "MSH":
                parsed["message_type"] = fields[8] if len(fields) > 8 else ""

            elif segment_type == "PID":
                parsed["patient"]["id"] = fields[3].split("^")[0] if len(fields) > 3 else ""
                parsed["patient"]["name"] = self._parse_hl7_name(fields[5]) if len(fields) > 5 else ""
                parsed["patient"]["dob"] = fields[7] if len(fields) > 7 else ""
                parsed["patient"]["sex"] = fields[8] if len(fields) > 8 else ""
                parsed["patient"]["address"] = fields[11] if len(fields) > 11 else ""
                parsed["patient"]["phone"] = fields[13] if len(fields) > 13 else ""

            elif segment_type == "PV1":
                parsed["visit"]["patient_class"] = fields[2] if len(fields) > 2 else ""
                parsed["visit"]["attending_doctor"] = self._parse_hl7_name(fields[7]) if len(fields) > 7 else ""
                parsed["visit"]["admit_datetime"] = fields[44] if len(fields) > 44 else ""

        return parsed

    def oru_to_extractions(self, parsed_oru: dict) -> list[dict]:
        extractions = []
        for obs in parsed_oru.get("observations", []):
            value = obs.get("value", "")
            value_numeric = None
            try:
                value_numeric = float(value.replace(",", ""))
            except (ValueError, TypeError):
                pass

            ref_range = obs.get("reference_range", "")
            range_low = None
            range_high = None
            if "-" in ref_range:
                parts = ref_range.split("-")
                try:
                    range_low = float(parts[0].strip())
                    range_high = float(parts[1].strip())
                except (ValueError, IndexError):
                    pass

            extractions.append({
                "name": obs.get("identifier_text", obs.get("identifier", "")).lower().replace(" ", "_"),
                "value": value,
                "value_numeric": value_numeric,
                "unit": obs.get("units"),
                "lab_range_low": range_low,
                "lab_range_high": range_high,
                "confidence": 0.95,
                "requires_manual_entry": False,
                "extraction_model": "hl7v2-parser",
                "raw_ocr_output": f"OBX|{obs.get('set_id')}|{obs.get('value_type')}|{obs.get('identifier')}",
            })

        return extractions

    def _parse_hl7_name(self, name_field: str) -> str:
        parts = name_field.split("^")
        if len(parts) >= 2:
            return f"{parts[1]} {parts[0]}".strip()
        return parts[0] if parts else ""


fhir_mapper = FHIRMapper()
hl7v2_parser = HL7v2Parser()
