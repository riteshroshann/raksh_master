import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.unit_normaliser import normalise_unit, normalise_extraction, normalise_batch


class TestGlucoseConversion:
    def test_mmol_to_mg_dl(self):
        result = normalise_unit("fasting_plasma_glucose", 5.5, "mmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"
        assert abs(result["value"] - 99.09) < 0.5
        assert result["original_value"] == 5.5
        assert result["original_unit"] == "mmol/L"

    def test_mmol_lowercase(self):
        result = normalise_unit("glucose", 7.0, "mmol/l")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"
        assert abs(result["value"] - 126.11) < 0.5

    def test_fbs_alias(self):
        result = normalise_unit("fbs", 6.1, "mmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"

    def test_already_mg_dl(self):
        result = normalise_unit("fasting_plasma_glucose", 100.0, "mg/dL")
        assert result["was_converted"] is False
        assert result["value"] == 100.0
        assert result["unit"] == "mg/dL"


class TestCreatinineConversion:
    def test_umol_to_mg_dl(self):
        result = normalise_unit("creatinine", 88.4, "µmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"
        assert abs(result["value"] - 1.0) < 0.05

    def test_umol_ascii_variant(self):
        result = normalise_unit("creatinine", 176.8, "umol/L")
        assert result["was_converted"] is True
        assert abs(result["value"] - 2.0) < 0.05

    def test_micromol_variant(self):
        result = normalise_unit("creatinine", 88.4, "micromol/L")
        assert result["was_converted"] is True


class TestCholesterolConversion:
    def test_total_cholesterol(self):
        result = normalise_unit("total_cholesterol", 5.2, "mmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"
        assert abs(result["value"] - 201.08) < 1.0

    def test_ldl(self):
        result = normalise_unit("ldl_cholesterol", 3.4, "mmol/L")
        assert result["was_converted"] is True

    def test_hdl(self):
        result = normalise_unit("hdl_cholesterol", 1.3, "mmol/L")
        assert result["was_converted"] is True


class TestTriglycerideConversion:
    def test_mmol_to_mg_dl(self):
        result = normalise_unit("triglycerides", 1.7, "mmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"
        assert abs(result["value"] - 150.57) < 1.0


class TestBilirubinConversion:
    def test_umol_to_mg_dl(self):
        result = normalise_unit("total_bilirubin", 17.1, "µmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"
        assert abs(result["value"] - 1.0) < 0.05


class TestHemoglobinConversion:
    def test_g_per_l_to_g_per_dl(self):
        result = normalise_unit("hemoglobin", 125.0, "g/L")
        assert result["was_converted"] is True
        assert result["unit"] == "g/dL"
        assert abs(result["value"] - 12.5) < 0.1

    def test_mmol_to_g_per_dl(self):
        result = normalise_unit("hemoglobin", 7.76, "mmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "g/dL"
        assert abs(result["value"] - 12.5) < 0.2


class TestCalciumConversion:
    def test_mmol_to_mg_dl(self):
        result = normalise_unit("calcium", 2.5, "mmol/L")
        assert result["was_converted"] is True
        assert result["unit"] == "mg/dL"
        assert abs(result["value"] - 10.0) < 0.1


class TestAlbuminConversion:
    def test_g_per_l_to_g_per_dl(self):
        result = normalise_unit("albumin", 40.0, "g/L")
        assert result["was_converted"] is True
        assert result["unit"] == "g/dL"
        assert abs(result["value"] - 4.0) < 0.1


class TestUnknownParameter:
    def test_unknown_param_no_conversion(self):
        result = normalise_unit("completely_unknown", 42.0, "weird/unit")
        assert result["was_converted"] is False
        assert result["value"] == 42.0
        assert result["unit"] == "weird/unit"


class TestExtractionNormalisation:
    def test_normalise_extraction_converts(self):
        extraction = {
            "name": "fasting_plasma_glucose",
            "value": "5.5",
            "value_numeric": 5.5,
            "unit": "mmol/L",
        }
        result = normalise_extraction(extraction)
        assert result["unit"] == "mg/dL"
        assert result["original_unit"] == "mmol/L"
        assert result["unit_converted"] is True

    def test_normalise_extraction_no_value(self):
        extraction = {"name": "glucose", "value": None, "value_numeric": None, "unit": "mmol/L"}
        result = normalise_extraction(extraction)
        assert result.get("unit_converted") is None

    def test_normalise_extraction_no_unit(self):
        extraction = {"name": "glucose", "value": "100", "value_numeric": 100.0, "unit": ""}
        result = normalise_extraction(extraction)
        assert result.get("unit_converted") is None


class TestBatchNormalisation:
    def test_batch(self):
        extractions = [
            {"name": "glucose", "value": "5.5", "value_numeric": 5.5, "unit": "mmol/L"},
            {"name": "hemoglobin", "value": "12.5", "value_numeric": 12.5, "unit": "g/dL"},
            {"name": "creatinine", "value": "88.4", "value_numeric": 88.4, "unit": "µmol/L"},
        ]
        result = normalise_batch(extractions)
        assert len(result) == 3
        assert result[0]["unit"] == "mg/dL"
        assert result[1]["unit"] == "g/dL"  # unchanged
        assert result[2]["unit"] == "mg/dL"

    def test_empty_batch(self):
        result = normalise_batch([])
        assert result == []
