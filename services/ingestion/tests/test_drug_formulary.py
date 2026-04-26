import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.drug_formulary import (
    DrugFormulary,
    DrugSchedule,
    THERAPEUTIC_RANGES,
    CRITICAL_INTERACTIONS,
)


class TestDrugLookup:
    def setup_method(self):
        self.formulary = DrugFormulary()

    def test_lookup_known_drug(self):
        result = self.formulary.lookup("metformin")
        assert result is not None
        assert result["min_mg"] == 250
        assert result["max_mg"] == 2550

    def test_lookup_unknown_drug(self):
        assert self.formulary.lookup("fakedrug123") is None

    def test_lookup_case_insensitive(self):
        result = self.formulary.lookup("METFORMIN")
        assert result is not None

    def test_lookup_with_spaces(self):
        result = self.formulary.lookup("Insulin Glargine")
        assert result is not None


class TestDoseValidation:
    def setup_method(self):
        self.formulary = DrugFormulary()

    def test_within_range(self):
        result = self.formulary.validate_dose("metformin", 500)
        assert result["status"] == "within_range"
        assert result["severity"] == "ok"

    def test_exceeds_maximum(self):
        result = self.formulary.validate_dose("metformin", 3000)
        assert result["status"] == "exceeds_maximum"
        assert result["severity"] == "warning"

    def test_exceeds_double_maximum_critical(self):
        result = self.formulary.validate_dose("metformin", 6000)
        assert result["status"] == "exceeds_maximum"
        assert result["severity"] == "critical"

    def test_below_minimum(self):
        result = self.formulary.validate_dose("metformin", 100)
        assert result["status"] == "below_minimum"
        assert result["severity"] == "info"

    def test_unknown_drug(self):
        result = self.formulary.validate_dose("imaginarymedicine", 500)
        assert result["status"] == "unknown_drug"

    def test_warfarin_high_dose(self):
        result = self.formulary.validate_dose("warfarin", 15)
        assert result["status"] == "exceeds_maximum"

    def test_digoxin_therapeutic(self):
        result = self.formulary.validate_dose("digoxin", 0.125)
        assert result["status"] == "within_range"

    def test_digoxin_toxic(self):
        result = self.formulary.validate_dose("digoxin", 0.5)
        assert result["status"] == "exceeds_maximum"

    def test_boundary_exact_max(self):
        result = self.formulary.validate_dose("cetirizine", 10)
        assert result["status"] == "within_range"

    def test_boundary_exact_min(self):
        result = self.formulary.validate_dose("cetirizine", 5)
        assert result["status"] == "within_range"


class TestInteractionChecking:
    def setup_method(self):
        self.formulary = DrugFormulary()

    def test_warfarin_aspirin_interaction(self):
        interactions = self.formulary.check_interactions(["warfarin", "aspirin"])
        assert len(interactions) == 1
        assert interactions[0]["severity"] == "high"
        assert "bleeding" in interactions[0]["effect"].lower()

    def test_no_interaction(self):
        interactions = self.formulary.check_interactions(["paracetamol", "cetirizine"])
        assert len(interactions) == 0

    def test_multiple_interactions(self):
        interactions = self.formulary.check_interactions(["warfarin", "aspirin", "metronidazole"])
        assert len(interactions) == 2

    def test_lithium_nsaid_interaction(self):
        interactions = self.formulary.check_interactions(["lithium", "ibuprofen"])
        assert len(interactions) == 1
        assert "toxicity" in interactions[0]["effect"].lower()

    def test_methotrexate_nsaid_critical(self):
        interactions = self.formulary.check_interactions(["methotrexate", "ibuprofen"])
        assert len(interactions) == 1
        assert interactions[0]["severity"] == "critical"

    def test_sorted_by_severity(self):
        interactions = self.formulary.check_interactions([
            "warfarin", "aspirin", "methotrexate", "ibuprofen"
        ])
        if len(interactions) >= 2:
            severities = [i["severity"] for i in interactions]
            severity_order = {"critical": 0, "high": 1, "moderate": 2}
            numeric = [severity_order.get(s, 3) for s in severities]
            assert numeric == sorted(numeric)

    def test_single_drug_no_interaction(self):
        interactions = self.formulary.check_interactions(["metformin"])
        assert len(interactions) == 0

    def test_empty_list(self):
        interactions = self.formulary.check_interactions([])
        assert len(interactions) == 0


class TestDrugSchedule:
    def setup_method(self):
        self.formulary = DrugFormulary()

    def test_otc_drug(self):
        result = self.formulary.check_schedule("paracetamol")
        assert result["schedule"] == "otc"
        assert result["requires_prescription"] is False

    def test_prescription_drug(self):
        result = self.formulary.check_schedule("metformin")
        assert result["schedule"] == "H"
        assert result["requires_prescription"] is True

    def test_controlled_drug(self):
        result = self.formulary.check_schedule("azithromycin")
        assert result["controlled"] is True

    def test_unknown_drug_assumes_prescription(self):
        result = self.formulary.check_schedule("unknowndrug")
        assert result["requires_prescription"] is True


class TestMedicationTextParsing:
    def setup_method(self):
        self.formulary = DrugFormulary()

    def test_parse_simple(self):
        result = self.formulary.parse_medication_text("Tab Metformin 500mg BD")
        assert result["drug_name"] == "metformin"
        assert result["dose_value"] == 500
        assert result["dose_unit"] == "mg"

    def test_parse_with_validation(self):
        result = self.formulary.parse_medication_text("Warfarin 15mg daily")
        assert result["drug_name"] == "warfarin"
        assert result["dose_validation"]["status"] == "exceeds_maximum"

    def test_parse_no_dose(self):
        result = self.formulary.parse_medication_text("metformin as directed")
        assert result["drug_name"] == "metformin"
        assert result["dose_value"] is None


class TestPrescriptionAnalysis:
    def setup_method(self):
        self.formulary = DrugFormulary()

    def test_safe_prescription(self):
        meds = ["Tab Metformin 500mg BD", "Tab Cetirizine 10mg OD"]
        result = self.formulary.analyze_prescription(meds)
        assert result["total_medications"] == 2
        assert result["has_critical_warnings"] is False

    def test_dangerous_prescription(self):
        meds = ["Warfarin 5mg daily", "Aspirin 150mg daily"]
        result = self.formulary.analyze_prescription(meds)
        assert len(result["interactions"]) >= 1
        assert any(w["type"] == "drug_interaction" for w in result["warnings"])

    def test_dose_warning(self):
        meds = ["Digoxin 0.5mg daily"]
        result = self.formulary.analyze_prescription(meds)
        assert any(w["type"] == "dose_exceeds_maximum" for w in result["warnings"])

    def test_warnings_sorted_by_severity(self):
        meds = ["Methotrexate 30mg weekly", "Ibuprofen 400mg TID", "Azithromycin 500mg OD"]
        result = self.formulary.analyze_prescription(meds)
        warnings = result["warnings"]
        if len(warnings) >= 2:
            severity_map = {"critical": 0, "high": 1, "warning": 2, "moderate": 3, "info": 4}
            scores = [severity_map.get(w["severity"], 5) for w in warnings]
            assert scores == sorted(scores)


class TestFormularyCompleteness:
    def test_minimum_drug_count(self):
        assert len(THERAPEUTIC_RANGES) >= 40

    def test_minimum_interaction_count(self):
        assert len(CRITICAL_INTERACTIONS) >= 10

    def test_all_drugs_have_required_fields(self):
        required = {"min_mg", "max_mg", "unit", "frequency", "schedule"}
        for drug, info in THERAPEUTIC_RANGES.items():
            for field in required:
                assert field in info, f"{drug} missing {field}"

    def test_all_interactions_have_required_fields(self):
        required = {"severity", "effect", "action"}
        for pair, info in CRITICAL_INTERACTIONS.items():
            for field in required:
                assert field in info, f"Interaction {pair} missing {field}"

    def test_min_less_than_max(self):
        for drug, info in THERAPEUTIC_RANGES.items():
            assert info["min_mg"] < info["max_mg"], f"{drug}: min >= max"
