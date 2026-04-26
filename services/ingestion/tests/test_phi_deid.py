import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.phi_deid import DeIdentificationPipeline, PHIEntity


class TestAadhaarDetection:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_detects_aadhaar_with_spaces(self):
        text = "Patient Aadhaar: 2345 6789 0123"
        entities = self.pipeline.scan(text)
        aadhaar = [e for e in entities if e.entity_type == "AADHAAR"]
        assert len(aadhaar) >= 1

    def test_detects_aadhaar_without_spaces(self):
        text = "Aadhaar number 234567890123 on file"
        entities = self.pipeline.scan(text)
        aadhaar = [e for e in entities if e.entity_type == "AADHAAR"]
        assert len(aadhaar) >= 1

    def test_rejects_aadhaar_starting_with_0(self):
        text = "Invalid aadhaar 012345678901"
        entities = self.pipeline.scan(text)
        aadhaar = [e for e in entities if e.entity_type == "AADHAAR"]
        assert len(aadhaar) == 0

    def test_rejects_aadhaar_starting_with_1(self):
        text = "Invalid aadhaar 123456789012"
        entities = self.pipeline.scan(text)
        aadhaar = [e for e in entities if e.entity_type == "AADHAAR"]
        assert len(aadhaar) == 0

    def test_rejects_all_same_digits(self):
        text = "Repeated digits 222222222222"
        entities = self.pipeline.scan(text)
        aadhaar = [e for e in entities if e.entity_type == "AADHAAR"]
        assert len(aadhaar) == 0


class TestPANDetection:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_detects_pan(self):
        text = "PAN Card: ABCDE1234F"
        entities = self.pipeline.scan(text)
        pan = [e for e in entities if e.entity_type == "PAN"]
        assert len(pan) >= 1

    def test_pan_correct_format(self):
        text = "PAN BXYPK5432A verified"
        entities = self.pipeline.scan(text)
        pan = [e for e in entities if e.entity_type == "PAN"]
        assert len(pan) >= 1


class TestABHADetection:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_detects_abha(self):
        text = "ABHA ID: 12-3456-7890-1234"
        entities = self.pipeline.scan(text)
        abha = [e for e in entities if e.entity_type == "ABHA"]
        assert len(abha) >= 1


class TestPhoneDetection:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_detects_indian_mobile(self):
        text = "Contact: 9876543210"
        entities = self.pipeline.scan(text)
        phone = [e for e in entities if e.entity_type == "PHONE"]
        assert len(phone) >= 1

    def test_detects_with_country_code(self):
        text = "Call +91-9876543210"
        entities = self.pipeline.scan(text)
        phone = [e for e in entities if e.entity_type in ("PHONE", "PHONE_NUMBER")]
        assert len(phone) >= 1


class TestEmailDetection:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_detects_email(self):
        text = "Email: patient@hospital.com"
        entities = self.pipeline.scan(text)
        email = [e for e in entities if e.entity_type == "EMAIL"]
        assert len(email) >= 1


class TestDeIdentification:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_redacts_aadhaar(self):
        text = "Patient Aadhaar: 2345 6789 0123"
        redacted, entities = self.pipeline.deidentify(text)
        assert "2345" not in redacted
        assert "[AADHAAR_REDACTED]" in redacted

    def test_redacts_pan(self):
        text = "PAN: ABCDE1234F"
        redacted, entities = self.pipeline.deidentify(text)
        assert "ABCDE1234F" not in redacted
        assert "[PAN_REDACTED]" in redacted

    def test_preserves_clinical_data(self):
        text = "Hemoglobin: 12.5 g/dL, TSH: 3.2 mIU/L"
        redacted, entities = self.pipeline.deidentify(text)
        assert "12.5" in redacted
        assert "3.2" in redacted

    def test_multiple_phi_redacted(self):
        text = "Patient Aadhaar 2345 6789 0123, PAN ABCDE1234F, phone 9876543210"
        redacted, entities = self.pipeline.deidentify(text)
        assert "2345" not in redacted
        assert "ABCDE1234F" not in redacted
        assert len(entities) >= 3

    def test_empty_text(self):
        redacted, entities = self.pipeline.deidentify("")
        assert redacted == ""
        assert entities == []


class TestStructuredDeIdentification:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_redacts_sensitive_fields(self):
        data = {
            "patient_name": "Ramesh Kumar",
            "aadhaar_number": "234567890123",
            "hemoglobin": "12.5",
        }
        redacted, entities = self.pipeline.deidentify_structured(data)
        assert redacted["patient_name"] != "Ramesh Kumar"
        assert redacted["aadhaar_number"] != "234567890123"
        assert redacted["hemoglobin"] == "12.5"

    def test_nested_dict_redaction(self):
        data = {
            "report": {
                "patient_name": "Sita Devi",
                "results": {"tsh": "3.2"},
            }
        }
        redacted, entities = self.pipeline.deidentify_structured(data)
        assert redacted["report"]["patient_name"] != "Sita Devi"
        assert redacted["report"]["results"]["tsh"] == "3.2"


class TestValidateClean:
    def setup_method(self):
        self.pipeline = DeIdentificationPipeline()

    def test_clean_text(self):
        text = "Hemoglobin is 12.5 g/dL within normal range"
        result = self.pipeline.validate_clean(text)
        assert result["is_clean"] is True
        assert result["residual_phi_count"] == 0

    def test_dirty_text(self):
        text = "Patient Aadhaar 2345 6789 0123 needs followup"
        result = self.pipeline.validate_clean(text)
        assert result["is_clean"] is False
        assert result["residual_phi_count"] >= 1


class TestPHIEntitySlots:
    def test_entity_has_slots(self):
        entity = PHIEntity("AADHAAR", "2345 6789 0123", 0, 14)
        assert entity.entity_type == "AADHAAR"
        assert entity.text == "2345 6789 0123"

    def test_entity_immutability(self):
        entity = PHIEntity("PAN", "ABCDE1234F", 0, 10)
        import pytest
        with pytest.raises(AttributeError):
            entity.random_attr = "fail"
