import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.whistle_engine import WhistleTransformEngine, build_default_engine


class TestWhistlePathResolution:
    def setup_method(self):
        self.engine = WhistleTransformEngine()

    def test_simple_path(self):
        source = {"name": "Ramesh", "age": 45}
        result = self.engine._resolve_path(source, "name")
        assert result == "Ramesh"

    def test_nested_path(self):
        source = {"patient": {"name": "Kumar", "dob": "1985-06-15"}}
        result = self.engine._resolve_path(source, "patient.name")
        assert result == "Kumar"

    def test_deeply_nested(self):
        source = {"a": {"b": {"c": {"d": "found"}}}}
        result = self.engine._resolve_path(source, "a.b.c.d")
        assert result == "found"

    def test_missing_path(self):
        source = {"name": "Ramesh"}
        result = self.engine._resolve_path(source, "address.city")
        assert result is None

    def test_array_index(self):
        source = {"items": ["first", "second", "third"]}
        result = self.engine._resolve_path(source, "items.1")
        assert result == "second"

    def test_empty_path(self):
        source = {"name": "test"}
        result = self.engine._resolve_path(source, "")
        assert result is None


class TestWhistleBuiltinFunctions:
    def setup_method(self):
        self.engine = WhistleTransformEngine()

    def test_parse_float(self):
        assert self.engine._parse_float("12.5") == 12.5

    def test_parse_float_with_commas(self):
        assert self.engine._parse_float("1,234.56") == 1234.56

    def test_parse_float_none(self):
        assert self.engine._parse_float(None) is None

    def test_parse_float_invalid(self):
        assert self.engine._parse_float("not_a_number") is None

    def test_parse_int(self):
        assert self.engine._parse_int("42") == 42

    def test_parse_int_from_float_string(self):
        assert self.engine._parse_int("42.7") == 42

    def test_parse_date_yyyymmdd(self):
        assert self.engine._parse_date("20240115") == "2024-01-15"

    def test_parse_date_iso(self):
        assert self.engine._parse_date("2024-01-15") == "2024-01-15"

    def test_parse_date_indian_format(self):
        assert self.engine._parse_date("15/01/2024") == "2024-01-15"

    def test_parse_date_none(self):
        assert self.engine._parse_date(None) is None

    def test_str_join_list(self):
        assert self.engine._str_join(["Hello", "World"]) == "Hello World"

    def test_str_join_single(self):
        assert self.engine._str_join("Hello") == "Hello"


class TestWhistleTransform:
    def setup_method(self):
        self.engine = WhistleTransformEngine()

    def test_simple_mapping(self):
        mapping = {
            "full_name": "name",
            "patient_age": "age",
        }
        self.engine.register_mapping("simple", mapping)

        source = {"name": "Ramesh Kumar", "age": 45}
        result = self.engine.transform("simple", source)

        assert result["full_name"] == "Ramesh Kumar"
        assert result["patient_age"] == 45

    def test_nested_source_mapping(self):
        mapping = {
            "patient_name": "patient.name",
            "patient_dob": "patient.dob",
        }
        self.engine.register_mapping("nested", mapping)

        source = {"patient": {"name": "Kumar", "dob": "1985-06-15"}}
        result = self.engine.transform("nested", source)

        assert result["patient_name"] == "Kumar"
        assert result["patient_dob"] == "1985-06-15"

    def test_literal_value(self):
        mapping = {
            "resourceType": "@Patient",
            "status": "@active",
        }
        self.engine.register_mapping("literal", mapping)

        result = self.engine.transform("literal", {})
        assert result["resourceType"] == "Patient"
        assert result["status"] == "active"

    def test_nested_output(self):
        mapping = {
            "name": "patient_name",
            "vitals": {
                "height": "height_cm",
                "weight": "weight_kg",
            },
        }
        self.engine.register_mapping("nested_out", mapping)

        source = {"patient_name": "Ramesh", "height_cm": 175, "weight_kg": 72}
        result = self.engine.transform("nested_out", source)

        assert result["name"] == "Ramesh"
        assert result["vitals"]["height"] == 175
        assert result["vitals"]["weight"] == 72

    def test_unknown_mapping_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Unknown mapping"):
            self.engine.transform("nonexistent", {})

    def test_batch_transform(self):
        mapping = {"output_name": "name"}
        self.engine.register_mapping("batch", mapping)

        sources = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
        results = self.engine.transform_batch("batch", sources)

        assert len(results) == 3
        assert results[0]["output_name"] == "A"
        assert results[2]["output_name"] == "C"


class TestWhistleCodeMapping:
    def setup_method(self):
        self.engine = WhistleTransformEngine()

    def test_register_and_use(self):
        self.engine.register_code_mapping("hl7", "fhir", {
            "M": "male", "F": "female",
        })
        result = self.engine._map_code({
            "source_system": "hl7",
            "target_system": "fhir",
            "code": "M",
        })
        assert result == "male"

    def test_unknown_code_passthrough(self):
        self.engine.register_code_mapping("hl7", "fhir", {"M": "male"})
        result = self.engine._map_code({
            "source_system": "hl7",
            "target_system": "fhir",
            "code": "X",
        })
        assert result == "X"


class TestDefaultEngine:
    def test_builds_without_error(self):
        engine = build_default_engine()
        assert engine is not None

    def test_has_registered_mappings(self):
        engine = build_default_engine()
        assert "hl7_to_fhir_patient" in engine._mappings
        assert "csv_lab_to_fhir_observation" in engine._mappings

    def test_csv_lab_to_fhir(self):
        engine = build_default_engine()
        source = {
            "test_name": "Hemoglobin",
            "result_value": "13.5",
            "unit": "g/dL",
            "range_low": "13.0",
            "range_high": "17.5",
            "test_date": "20240115",
        }
        result = engine.transform("csv_lab_to_fhir_observation", source)

        assert result["resourceType"] == "Observation"
        assert result["status"] == "final"
        assert result["effectiveDateTime"] == "2024-01-15"
