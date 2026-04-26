import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.loinc_mapping import LOINCService, CORE_LOINC_MAP


class TestLOINCLookup:
    def setup_method(self):
        self.service = LOINCService()

    def test_lookup_hemoglobin(self):
        result = self.service.lookup("hemoglobin")
        assert result is not None
        assert result["loinc_code"] == "718-7"

    def test_lookup_alias_hb(self):
        result = self.service.lookup("hb")
        assert result is not None
        assert result["loinc_code"] == "718-7"

    def test_lookup_hba1c(self):
        result = self.service.lookup("hba1c")
        assert result is not None
        assert result["loinc_code"] == "4548-4"

    def test_lookup_case_insensitive(self):
        result = self.service.lookup("HEMOGLOBIN")
        assert result is not None

    def test_lookup_with_spaces(self):
        result = self.service.lookup("total cholesterol")
        assert result is not None
        assert result["loinc_code"] == "2093-3"

    def test_lookup_unknown_returns_none(self):
        result = self.service.lookup("completely_fake_parameter")
        assert result is None


class TestLOINCCodeRetrieval:
    def setup_method(self):
        self.service = LOINCService()

    def test_get_loinc_code(self):
        code = self.service.get_loinc_code("creatinine")
        assert code == "2160-0"

    def test_get_loinc_code_unknown(self):
        code = self.service.get_loinc_code("fake_param")
        assert code is None


class TestFHIRCoding:
    def setup_method(self):
        self.service = LOINCService()

    def test_fhir_coding_structure(self):
        coding = self.service.get_fhir_coding("tsh")
        assert coding is not None
        assert coding["system"] == "http://loinc.org"
        assert coding["code"] == "3016-3"
        assert "TSH" in coding["display"]

    def test_fhir_coding_unknown(self):
        coding = self.service.get_fhir_coding("unknown_param")
        assert coding is None


class TestExtractionEnrichment:
    def setup_method(self):
        self.service = LOINCService()

    def test_enrich_single_extraction(self):
        extraction = {"name": "hemoglobin", "value": "12.5", "unit": "g/dL"}
        enriched = self.service.enrich_extraction(extraction)
        assert enriched["loinc_code"] == "718-7"
        assert enriched["loinc_name"] is not None

    def test_enrich_backfills_unit(self):
        extraction = {"name": "tsh", "value": "3.2", "unit": None}
        enriched = self.service.enrich_extraction(extraction)
        assert enriched["unit"] == "mIU/L"

    def test_enrich_preserves_existing_unit(self):
        extraction = {"name": "hemoglobin", "value": "12.5", "unit": "custom_unit"}
        enriched = self.service.enrich_extraction(extraction)
        assert enriched["unit"] == "custom_unit"

    def test_enrich_unknown_no_loinc(self):
        extraction = {"name": "unknown_param", "value": "42"}
        enriched = self.service.enrich_extraction(extraction)
        assert "loinc_code" not in enriched


class TestBatchEnrichment:
    def setup_method(self):
        self.service = LOINCService()

    def test_batch_enrichment(self):
        extractions = [
            {"name": "hemoglobin", "value": "12.5"},
            {"name": "tsh", "value": "3.2"},
            {"name": "unknown", "value": "42"},
        ]
        enriched = self.service.enrich_batch(extractions)
        assert len(enriched) == 3
        assert enriched[0].get("loinc_code") == "718-7"
        assert enriched[1].get("loinc_code") == "3016-3"
        assert "loinc_code" not in enriched[2]

    def test_empty_batch(self):
        enriched = self.service.enrich_batch([])
        assert enriched == []


class TestCoverageReport:
    def setup_method(self):
        self.service = LOINCService()

    def test_full_coverage(self):
        params = ["hemoglobin", "tsh", "creatinine"]
        report = self.service.coverage_report(params)
        assert report["coverage_percent"] == 100.0
        assert report["unmapped"] == 0

    def test_partial_coverage(self):
        params = ["hemoglobin", "unknown_thing"]
        report = self.service.coverage_report(params)
        assert report["coverage_percent"] == 50.0
        assert report["unmapped"] == 1

    def test_empty_params(self):
        report = self.service.coverage_report([])
        assert report["total"] == 0


class TestMapCompleteness:
    def test_minimum_mapping_count(self):
        unique_codes = {v["loinc_code"] for v in CORE_LOINC_MAP.values()}
        assert len(unique_codes) >= 50

    def test_all_mappings_have_required_fields(self):
        required = {"loinc_code", "loinc_name", "component", "system"}
        for param, mapping in CORE_LOINC_MAP.items():
            for field in required:
                assert field in mapping, f"{param} missing {field}"

    def test_cbc_panel_covered(self):
        cbc = ["hemoglobin", "hematocrit", "wbc", "rbc", "platelet_count", "mcv", "mch"]
        service = LOINCService()
        for param in cbc:
            assert service.lookup(param) is not None, f"CBC parameter {param} not mapped"

    def test_metabolic_panel_covered(self):
        metabolic = ["creatinine", "bun", "sodium", "potassium", "calcium", "albumin", "total_bilirubin"]
        service = LOINCService()
        for param in metabolic:
            assert service.lookup(param) is not None, f"Metabolic parameter {param} not mapped"

    def test_lipid_panel_covered(self):
        lipid = ["total_cholesterol", "hdl_cholesterol", "ldl_cholesterol", "triglycerides"]
        service = LOINCService()
        for param in lipid:
            assert service.lookup(param) is not None, f"Lipid parameter {param} not mapped"

    def test_liver_panel_covered(self):
        liver = ["alt", "ast", "alp", "total_bilirubin", "albumin", "total_protein"]
        service = LOINCService()
        for param in liver:
            assert service.lookup(param) is not None, f"Liver parameter {param} not mapped"

    def test_thyroid_panel_covered(self):
        thyroid = ["tsh", "ft4", "ft3"]
        service = LOINCService()
        for param in thyroid:
            assert service.lookup(param) is not None, f"Thyroid parameter {param} not mapped"
