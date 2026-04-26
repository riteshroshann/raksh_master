import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.disease_protocols import (
    DiseaseProtocolEngine,
    DiseaseCategory,
    DISEASE_PANELS,
)


class TestDiseaseDetection:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_detect_diabetes(self):
        params = ["hba1c", "fasting_plasma_glucose", "creatinine"]
        categories = self.engine.detect_disease_category(params)
        assert DiseaseCategory.DIABETES in categories

    def test_detect_thyroid(self):
        params = ["tsh", "ft4", "ft3"]
        categories = self.engine.detect_disease_category(params)
        assert DiseaseCategory.THYROID in categories

    def test_detect_ckd(self):
        params = ["creatinine", "egfr", "potassium"]
        categories = self.engine.detect_disease_category(params)
        assert DiseaseCategory.CKD in categories

    def test_detect_cardiac(self):
        params = ["troponin_i", "bnp", "ldl"]
        categories = self.engine.detect_disease_category(params)
        assert DiseaseCategory.CARDIAC in categories

    def test_detect_anemia(self):
        params = ["hemoglobin", "ferritin", "mcv"]
        categories = self.engine.detect_disease_category(params)
        assert DiseaseCategory.ANEMIA in categories

    def test_detect_liver(self):
        params = ["alt", "ast", "total_bilirubin"]
        categories = self.engine.detect_disease_category(params)
        assert DiseaseCategory.LIVER in categories

    def test_single_param_no_detection(self):
        params = ["hemoglobin"]
        categories = self.engine.detect_disease_category(params)
        assert len(categories) == 0

    def test_multi_disease_detection(self):
        params = ["hba1c", "fbs", "hemoglobin", "ferritin", "mcv"]
        categories = self.engine.detect_disease_category(params)
        assert DiseaseCategory.DIABETES in categories
        assert DiseaseCategory.ANEMIA in categories


class TestDiabetesInterpretation:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_normal_hba1c(self):
        result = self.engine.interpret_parameter("hba1c", 5.2, DiseaseCategory.DIABETES)
        assert result["status"] == "normal"

    def test_prediabetic_hba1c(self):
        result = self.engine.interpret_parameter("hba1c", 6.0, DiseaseCategory.DIABETES)
        assert result["status"] == "prediabetic"

    def test_diabetic_hba1c(self):
        result = self.engine.interpret_parameter("hba1c", 8.5, DiseaseCategory.DIABETES)
        assert "diabetic" in result["status"]

    def test_critical_high_hba1c(self):
        result = self.engine.interpret_parameter("hba1c", 12.0, DiseaseCategory.DIABETES)
        assert "critical_high" in result["all_matched_ranges"]

    def test_normal_fpg(self):
        result = self.engine.interpret_parameter("fasting_plasma_glucose", 85, DiseaseCategory.DIABETES)
        assert result["status"] == "normal"

    def test_critical_low_fpg(self):
        result = self.engine.interpret_parameter("fasting_plasma_glucose", 45, DiseaseCategory.DIABETES)
        assert "critical" in result["status"]


class TestThyroidInterpretation:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_normal_tsh(self):
        result = self.engine.interpret_parameter("tsh", 2.0, DiseaseCategory.THYROID)
        assert result["status"] == "normal"

    def test_hypothyroid_tsh(self):
        result = self.engine.interpret_parameter("tsh", 15.0, DiseaseCategory.THYROID)
        assert "hypothyroid" in result["status"]

    def test_hyperthyroid_tsh(self):
        result = self.engine.interpret_parameter("tsh", 0.1, DiseaseCategory.THYROID)
        assert "hyperthyroid" in result["status"]

    def test_subclinical_hypothyroid(self):
        result = self.engine.interpret_parameter("tsh", 7.0, DiseaseCategory.THYROID)
        assert "subclinical" in result["status"]


class TestCKDStaging:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_normal_egfr(self):
        result = self.engine.interpret_parameter("egfr", 100, DiseaseCategory.CKD)
        assert result["status"] == "normal"

    def test_stage_3_ckd(self):
        result = self.engine.interpret_parameter("egfr", 40, DiseaseCategory.CKD)
        assert "stage_3" in result["status"]

    def test_stage_5_dialysis(self):
        result = self.engine.interpret_parameter("egfr", 10, DiseaseCategory.CKD)
        assert "stage_5" in result["status"]
        assert result["severity"] == "critical"

    def test_critical_potassium(self):
        result = self.engine.interpret_parameter("potassium", 6.0, DiseaseCategory.CKD)
        assert "critical" in result["status"]


class TestCardiacMarkers:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_normal_troponin(self):
        result = self.engine.interpret_parameter("troponin_i", 0.02, DiseaseCategory.CARDIAC)
        assert result["status"] == "normal"

    def test_ami_troponin(self):
        result = self.engine.interpret_parameter("troponin_i", 2.0, DiseaseCategory.CARDIAC)
        assert "ami" in result["status"]
        assert result["severity"] == "critical"

    def test_heart_failure_bnp(self):
        result = self.engine.interpret_parameter("bnp", 800, DiseaseCategory.CARDIAC)
        assert "heart_failure" in result["status"]

    def test_optimal_ldl(self):
        result = self.engine.interpret_parameter("ldl", 80, DiseaseCategory.CARDIAC)
        assert result["status"] == "optimal"


class TestCoMonitoringGaps:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_hba1c_without_creatinine(self):
        params = ["hba1c", "fasting_plasma_glucose"]
        gaps = self.engine.check_co_monitoring_gaps(params, DiseaseCategory.DIABETES)
        gap_params = [item for gap in gaps for item in gap["missing_parameters"]]
        assert "creatinine" in gap_params or "albumin_creatinine_ratio" in gap_params

    def test_tsh_without_ft4(self):
        params = ["tsh"]
        gaps = self.engine.check_co_monitoring_gaps(params, DiseaseCategory.THYROID)
        assert len(gaps) > 0
        assert "free_thyroxine" in gaps[0]["missing_parameters"]

    def test_complete_panel_no_gaps(self):
        params = ["tsh", "ft4"]
        gaps = self.engine.check_co_monitoring_gaps(params, DiseaseCategory.THYROID)
        assert len(gaps) == 0

    def test_hemoglobin_without_ferritin(self):
        params = ["hemoglobin", "hematocrit"]
        gaps = self.engine.check_co_monitoring_gaps(params, DiseaseCategory.ANEMIA)
        assert len(gaps) > 0


class TestTrendEvaluation:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_rising_hba1c_alert(self):
        data_points = [
            {"date": "2024-01-01", "value": 6.5},
            {"date": "2024-04-01", "value": 7.2},
        ]
        alerts = self.engine.evaluate_trend("hba1c", data_points, DiseaseCategory.DIABETES)
        assert len(alerts) >= 1
        assert alerts[0]["condition"] == "rising"

    def test_stable_hba1c_no_alert(self):
        data_points = [
            {"date": "2024-01-01", "value": 6.5},
            {"date": "2024-04-01", "value": 6.6},
        ]
        alerts = self.engine.evaluate_trend("hba1c", data_points, DiseaseCategory.DIABETES)
        assert len(alerts) == 0

    def test_falling_egfr_alert(self):
        data_points = [
            {"date": "2024-01-01", "value": 60},
            {"date": "2024-07-01", "value": 50},
        ]
        alerts = self.engine.evaluate_trend("egfr", data_points, DiseaseCategory.CKD)
        assert len(alerts) >= 1
        assert alerts[0]["severity"] == "critical"


class TestFullAnalysis:
    def setup_method(self):
        self.engine = DiseaseProtocolEngine()

    def test_diabetic_panel_analysis(self):
        params = [
            {"name": "hba1c", "value_numeric": 8.5},
            {"name": "fasting_plasma_glucose", "value_numeric": 180},
            {"name": "creatinine", "value_numeric": 1.2},
        ]
        analysis = self.engine.full_analysis(params)
        assert "diabetes" in analysis["detected_categories"]
        assert analysis["has_critical"] or analysis["warning_findings"] > 0

    def test_empty_params(self):
        analysis = self.engine.full_analysis([])
        assert analysis["detected_categories"] == []
        assert analysis["has_critical"] is False

    def test_critical_flagging(self):
        params = [
            {"name": "troponin_i", "value_numeric": 5.0},
            {"name": "bnp", "value_numeric": 1000},
        ]
        analysis = self.engine.full_analysis(params)
        assert analysis["has_critical"]


class TestPanelCompleteness:
    def test_all_categories_have_required_fields(self):
        required_keys = {"canonical_parameters", "aliases", "thresholds", "deterioration_rules", "co_monitoring"}
        for category, panel in DISEASE_PANELS.items():
            for key in required_keys:
                assert key in panel, f"{category.value} missing {key}"

    def test_minimum_six_categories(self):
        assert len(DISEASE_PANELS) >= 6

    def test_all_deterioration_rules_have_fields(self):
        required = {"parameter", "condition", "threshold_delta", "window_months", "message", "severity"}
        for category, panel in DISEASE_PANELS.items():
            for rule in panel["deterioration_rules"]:
                for field in required:
                    assert field in rule, f"{category.value} deterioration rule missing {field}"
