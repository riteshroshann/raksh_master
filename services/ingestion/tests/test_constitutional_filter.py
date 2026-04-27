import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from middleware.constitutional_filter import _scan_value, _redact_value, PROHIBITED_TERMS


class TestScanValue:
    def test_finds_diabetic(self):
        violations = _scan_value("patient is diabetic")
        assert len(violations) == 1
        assert violations[0]["term"] == "diabetic"

    def test_finds_case_insensitive(self):
        violations = _scan_value("Patient is DIABETIC")
        assert len(violations) == 1

    def test_clean_string(self):
        violations = _scan_value("hemoglobin 12.5 g/dL")
        assert len(violations) == 0

    def test_finds_nephropathy(self):
        violations = _scan_value("possible diabetic nephropathy progression")
        assert any(v["term"] == "nephropathy" for v in violations)
        assert any(v["term"] == "diabetic" for v in violations)

    def test_finds_dose_adjustment(self):
        violations = _scan_value("levothyroxine dose may need adjustment")
        assert len(violations) >= 1

    def test_finds_consult_doctor(self):
        violations = _scan_value("consult your doctor immediately")
        assert len(violations) >= 1

    def test_finds_suggestive_of(self):
        violations = _scan_value("findings suggestive of hepatitis")
        assert any(v["term"] == "suggestive of" for v in violations)
        assert any(v["term"] == "hepatitis" for v in violations)


class TestScanNestedStructures:
    def test_scan_dict(self):
        data = {"status": "normal", "message": "you may have a condition"}
        violations = _scan_value(data)
        assert len(violations) >= 1
        assert violations[0]["path"] == "message"

    def test_scan_nested_dict(self):
        data = {"result": {"interpretation": "this indicates hypothyroid"}}
        violations = _scan_value(data)
        assert any(v["term"] == "hypothyroid" for v in violations)
        assert any("interpretation" in v["path"] for v in violations)

    def test_scan_list(self):
        data = ["normal", "anaemic", "fine"]
        violations = _scan_value(data)
        assert len(violations) >= 1

    def test_scan_list_of_dicts(self):
        data = [
            {"name": "hemoglobin", "value": "12.5"},
            {"name": "interpretation", "value": "consistent with anemia"},
        ]
        violations = _scan_value(data)
        assert any(v["term"] == "consistent with" for v in violations)

    def test_clean_nested_structure(self):
        data = {
            "parameters": [
                {"name": "hemoglobin", "value": "12.5", "unit": "g/dL"},
                {"name": "tsh", "value": "3.2", "unit": "mIU/L"},
            ],
            "status": "saved",
        }
        violations = _scan_value(data)
        assert len(violations) == 0


class TestRedactValue:
    def test_redact_string(self):
        result = _redact_value("patient is diabetic")
        assert "diabetic" not in result.lower()
        assert "[REDACTED]" in result

    def test_redact_dict(self):
        data = {"msg": "you may have hypothyroid"}
        result = _redact_value(data)
        assert "hypothyroid" not in result["msg"].lower()

    def test_redact_preserves_clean(self):
        data = {"value": "12.5", "unit": "g/dL"}
        result = _redact_value(data)
        assert result["value"] == "12.5"
        assert result["unit"] == "g/dL"

    def test_redact_nested(self):
        data = {"results": [{"interpretation": "diagnosed with anemia"}]}
        result = _redact_value(data)
        assert "diagnosed with" not in str(result).lower()


class TestProhibitedTermsList:
    def test_minimum_term_count(self):
        assert len(PROHIBITED_TERMS) >= 30

    def test_critical_terms_present(self):
        critical = [
            "diabetic", "hypothyroid", "anaemic", "nephropathy",
            "heart failure", "you may have", "consult a doctor",
            "diagnosis", "suggestive of",
        ]
        for term in critical:
            assert term in PROHIBITED_TERMS, f"missing critical term: {term}"

    def test_no_parameter_names_in_list(self):
        """prohibited terms should not include legitimate parameter names"""
        param_names = ["hemoglobin", "creatinine", "glucose", "cholesterol", "tsh"]
        for name in param_names:
            assert name not in PROHIBITED_TERMS, f"parameter name incorrectly prohibited: {name}"
