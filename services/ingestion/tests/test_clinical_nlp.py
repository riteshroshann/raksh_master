import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.clinical_nlp import (
    ConTextEngine,
    DosageHazardDetector,
    EntityLinker,
    ClinicalTextAnalyzer,
    MEDICAL_ABBREVIATION_MAP,
    LOINC_PARTIAL_MAP,
    SNOMED_PARTIAL_MAP,
    NEGATION_TRIGGERS,
    UNCERTAINTY_TRIGGERS,
)


class TestConTextNegation:
    def setup_method(self):
        self.engine = ConTextEngine()

    def test_simple_negation(self):
        text = "Patient denies chest pain"
        span = (22, 32)
        assert self.engine.detect_negation(text, span) is True

    def test_no_negation_present(self):
        text = "Patient reports severe headache"
        span = (24, 32)
        assert self.engine.detect_negation(text, span) is False

    def test_negation_no_evidence_of(self):
        text = "There is no evidence of malignancy in the specimen"
        span = (23, 33)
        assert self.engine.detect_negation(text, span) is True

    def test_negation_ruled_out(self):
        text = "Pneumonia has been ruled out based on imaging"
        span = (0, 9)
        assert self.engine.detect_negation(text, span) is True

    def test_negation_scope_break_blocks(self):
        text = "No headache but severe chest pain is present"
        span = (26, 36)
        assert self.engine.detect_negation(text, span) is False

    def test_negation_without_keyword(self):
        text = "Patient presented without fever"
        span = (27, 32)
        assert self.engine.detect_negation(text, span) is True

    def test_double_negation_text(self):
        text = "Not without its challenges, the patient has diabetes"
        span = (44, 52)
        assert self.engine.detect_negation(text, span) is True

    def test_negation_far_away(self):
        text = "No issues were noted. The patient then reported that weeks later she developed a rash and fever and headache"
        span = (100, 108)
        assert self.engine.detect_negation(text, span) is False


class TestConTextUncertainty:
    def setup_method(self):
        self.engine = ConTextEngine()

    def test_possible_condition(self):
        text = "Findings are suggestive of tuberculosis"
        span = (31, 43)
        assert self.engine.detect_uncertainty(text, span) is True

    def test_definite_condition(self):
        text = "Confirmed diagnosis of diabetes mellitus"
        span = (23, 40)
        assert self.engine.detect_uncertainty(text, span) is False

    def test_cannot_rule_out(self):
        text = "Cannot rule out malignancy at this time"
        span = (16, 26)
        assert self.engine.detect_uncertainty(text, span) is True

    def test_preliminary_finding(self):
        text = "Preliminary results indicate elevated TSH"
        span = (37, 40)
        assert self.engine.detect_uncertainty(text, span) is True


class TestConTextFamilyHistory:
    def setup_method(self):
        self.engine = ConTextEngine()

    def test_family_history_detected(self):
        text = "Family history of diabetes and hypertension"
        span = (18, 26)
        assert self.engine.detect_family_history(text, span) is True

    def test_no_family_history(self):
        text = "Patient has been diagnosed with diabetes"
        span = (31, 39)
        assert self.engine.detect_family_history(text, span) is False

    def test_maternal_history(self):
        text = "Maternal grandmother had breast cancer"
        span = (31, 37)
        assert self.engine.detect_family_history(text, span) is True


class TestConTextHypothetical:
    def setup_method(self):
        self.engine = ConTextEngine()

    def test_hypothetical_detected(self):
        text = "If symptoms persist, consider adding metformin"
        span = (37, 46)
        assert self.engine.detect_hypothetical(text, span) is True

    def test_not_hypothetical(self):
        text = "Started metformin 500mg twice daily"
        span = (8, 17)
        assert self.engine.detect_hypothetical(text, span) is False


class TestAssertionClassification:
    def setup_method(self):
        self.engine = ConTextEngine()

    def test_affirmed(self):
        text = "Patient has diabetes mellitus type 2"
        span = (12, 30)
        assert self.engine.classify_assertion(text, span) == "affirmed"

    def test_negated(self):
        text = "No signs of pneumonia on imaging"
        span = (12, 21)
        assert self.engine.classify_assertion(text, span) == "negated"

    def test_uncertain(self):
        text = "Possibly early stage kidney disease"
        span = (22, 36)
        assert self.engine.classify_assertion(text, span) == "uncertain"

    def test_family_history_priority(self):
        text = "Family history of cancer, patient currently healthy"
        span = (18, 24)
        result = self.engine.classify_assertion(text, span)
        assert result == "family_history"


class TestDosageHazardDetector:
    def setup_method(self):
        self.detector = DosageHazardDetector()

    def test_insulin_unit_ambiguity(self):
        text = "Administer 10U insulin before meals"
        hazards = self.detector.scan(text)
        assert len(hazards) >= 1
        assert any(h["type"] == "insulin_unit_ambiguity" for h in hazards)
        assert any(h["severity"] == "critical" for h in hazards)

    def test_warfarin_dose(self):
        text = "Take 15mg of warfarin daily adjusted per INR"
        hazards = self.detector.scan(text)
        warfarin = [h for h in hazards if h["type"] == "warfarin_dose"]
        assert len(warfarin) >= 1
        assert warfarin[0]["severity"] == "critical"

    def test_safe_medication(self):
        text = "Paracetamol 500mg as needed"
        hazards = self.detector.scan(text)
        assert len(hazards) == 0

    def test_multiple_hazards(self):
        text = "10U insulin and 5mg of warfarin daily"
        hazards = self.detector.scan(text)
        assert len(hazards) >= 2

    def test_methotrexate_high_dose(self):
        text = "Take 30mg of methotrexate weekly"
        hazards = self.detector.scan(text)
        mtx = [h for h in hazards if h["type"] == "methotrexate_dose"]
        assert len(mtx) >= 1
        assert mtx[0]["severity"] == "critical"


class TestEntityLinker:
    def setup_method(self):
        self.linker = EntityLinker()

    def test_loinc_hemoglobin(self):
        assert self.linker.link_to_loinc("hemoglobin") == "718-7"

    def test_loinc_tsh(self):
        assert self.linker.link_to_loinc("tsh") == "3016-3"

    def test_loinc_unknown(self):
        assert self.linker.link_to_loinc("totally_made_up_test") is None

    def test_snomed_diabetes(self):
        assert self.linker.link_to_snomed("diabetes") == "73211009"

    def test_snomed_unknown(self):
        assert self.linker.link_to_snomed("alien_disease") is None

    def test_abbreviation_expansion_hb(self):
        assert self.linker.expand_abbreviation("hb") == "hemoglobin"

    def test_abbreviation_expansion_tab(self):
        assert self.linker.expand_abbreviation("tab") == "tablet"

    def test_abbreviation_expansion_unknown(self):
        assert self.linker.expand_abbreviation("zzzzz") is None

    def test_normalize_parameter_name(self):
        assert self.linker.normalize_parameter_name("HbA1c") == "glycated_hemoglobin"

    def test_normalize_preserves_unknown(self):
        result = self.linker.normalize_parameter_name("some_custom_test")
        assert result == "some_custom_test"

    def test_enrich_extraction(self):
        extraction = {"name": "hemoglobin", "value": "12.5", "confidence": 0.95}
        enriched = self.linker.enrich_extraction(extraction)
        assert enriched["loinc_code"] == "718-7"
        assert enriched["normalized_name"] == "hemoglobin"

    def test_batch_enrich(self):
        extractions = [
            {"name": "hemoglobin", "value": "12.5", "confidence": 0.95},
            {"name": "tsh", "value": "3.2", "confidence": 0.90},
            {"name": "custom_thing", "value": "1.0", "confidence": 0.80},
        ]
        enriched = self.linker.batch_enrich(extractions)
        assert len(enriched) == 3
        assert enriched[0].get("loinc_code") == "718-7"
        assert "expanded_name" in enriched[1]
        assert "loinc_code" not in enriched[2]


class TestClinicalTextAnalyzer:
    def setup_method(self):
        self.analyzer = ClinicalTextAnalyzer()

    def test_analyze_with_negation(self):
        text = "No evidence of diabetes. Patient has hypertension."
        result = self.analyzer.analyze(text)
        assert result["negated_count"] >= 1
        assert result["affirmed_count"] >= 1

    def test_analyze_empty_text(self):
        result = self.analyzer.analyze("")
        assert result["entities"] == []
        assert result["hazards"] == []

    def test_analyze_with_hazard(self):
        text = "Start insulin 10U before breakfast. Hemoglobin is normal."
        result = self.analyzer.analyze(text)
        assert len(result["hazards"]) >= 1

    def test_analyze_returns_all_keys(self):
        result = self.analyzer.analyze("Patient has diabetes")
        assert "entities" in result
        assert "hazards" in result
        assert "negated_count" in result
        assert "affirmed_count" in result
        assert "uncertain_count" in result


class TestAbbreviationMapCompleteness:
    def test_minimum_abbreviation_count(self):
        assert len(MEDICAL_ABBREVIATION_MAP) >= 90

    def test_loinc_map_coverage(self):
        assert len(LOINC_PARTIAL_MAP) >= 30

    def test_snomed_map_coverage(self):
        assert len(SNOMED_PARTIAL_MAP) >= 12

    def test_all_negation_triggers_are_lowercase(self):
        for trigger in NEGATION_TRIGGERS:
            assert trigger == trigger.lower()

    def test_all_uncertainty_triggers_are_lowercase(self):
        for trigger in UNCERTAINTY_TRIGGERS:
            assert trigger == trigger.lower()
