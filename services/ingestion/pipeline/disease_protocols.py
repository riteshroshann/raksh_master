import re
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger()


class DiseaseCategory(str, Enum):
    DIABETES = "diabetes"
    THYROID = "thyroid"
    CKD = "chronic_kidney_disease"
    CARDIAC = "cardiac"
    ANEMIA = "anemia"
    LIVER = "liver"
    LIPID = "lipid"
    INFECTION = "infection"


DISEASE_PANELS = {
    DiseaseCategory.DIABETES: {
        "canonical_parameters": [
            "glycated_hemoglobin", "fasting_plasma_glucose", "postprandial_glucose",
            "oral_glucose_tolerance_test", "fasting_insulin", "c_peptide",
            "creatinine", "estimated_glomerular_filtration_rate", "albumin_creatinine_ratio",
        ],
        "aliases": {
            "hba1c": "glycated_hemoglobin",
            "fpg": "fasting_plasma_glucose",
            "ppg": "postprandial_glucose",
            "ogtt": "oral_glucose_tolerance_test",
            "fbs": "fasting_plasma_glucose",
            "rbs": "postprandial_glucose",
        },
        "thresholds": {
            "glycated_hemoglobin": {
                "normal": (0, 5.7),
                "prediabetic": (5.7, 6.5),
                "diabetic": (6.5, 14.0),
                "critical_high": (10.0, 100.0),
                "target_controlled": (0, 7.0),
            },
            "fasting_plasma_glucose": {
                "normal": (70, 100),
                "prediabetic": (100, 126),
                "diabetic": (126, 500),
                "critical_low": (0, 54),
                "critical_high": (400, 2000),
            },
            "postprandial_glucose": {
                "normal": (70, 140),
                "prediabetic": (140, 200),
                "diabetic": (200, 600),
                "critical_high": (400, 2000),
            },
        },
        "deterioration_rules": [
            {
                "parameter": "glycated_hemoglobin",
                "condition": "rising",
                "threshold_delta": 0.5,
                "window_months": 3,
                "message": "HbA1c rising {delta}% over {months} months — glycemic control worsening",
                "severity": "warning",
            },
            {
                "parameter": "estimated_glomerular_filtration_rate",
                "condition": "falling",
                "threshold_delta": 5.0,
                "window_months": 6,
                "message": "eGFR declining {delta} mL/min over {months} months — possible diabetic nephropathy progression",
                "severity": "critical",
            },
        ],
        "co_monitoring": [
            {"primary": "glycated_hemoglobin", "required": ["creatinine", "albumin_creatinine_ratio"], "reason": "Diabetic nephropathy screening"},
            {"primary": "fasting_plasma_glucose", "required": ["glycated_hemoglobin"], "reason": "Single FPG without HbA1c is insufficient for long-term control assessment"},
        ],
    },

    DiseaseCategory.THYROID: {
        "canonical_parameters": [
            "thyroid_stimulating_hormone", "free_thyroxine", "free_triiodothyronine",
            "thyroxine", "triiodothyronine", "anti_tpo", "anti_thyroglobulin",
        ],
        "aliases": {
            "tsh": "thyroid_stimulating_hormone",
            "ft4": "free_thyroxine",
            "ft3": "free_triiodothyronine",
            "t4": "thyroxine",
            "t3": "triiodothyronine",
        },
        "thresholds": {
            "thyroid_stimulating_hormone": {
                "hyperthyroid": (0, 0.4),
                "normal": (0.4, 4.0),
                "subclinical_hypothyroid": (4.0, 10.0),
                "hypothyroid": (10.0, 100.0),
                "critical_high": (50.0, 500.0),
            },
            "free_thyroxine": {
                "low": (0, 0.8),
                "normal": (0.8, 1.8),
                "high": (1.8, 10.0),
            },
        },
        "deterioration_rules": [
            {
                "parameter": "thyroid_stimulating_hormone",
                "condition": "rising",
                "threshold_delta": 2.0,
                "window_months": 6,
                "message": "TSH rising {delta} mIU/L — levothyroxine dose may need adjustment",
                "severity": "warning",
            },
        ],
        "co_monitoring": [
            {"primary": "thyroid_stimulating_hormone", "required": ["free_thyroxine"], "reason": "TSH alone cannot distinguish central vs primary thyroid dysfunction"},
        ],
    },

    DiseaseCategory.CKD: {
        "canonical_parameters": [
            "creatinine", "blood_urea_nitrogen", "estimated_glomerular_filtration_rate",
            "albumin_creatinine_ratio", "uric_acid", "potassium", "sodium",
            "calcium", "phosphorus", "hemoglobin",
        ],
        "aliases": {
            "bun": "blood_urea_nitrogen",
            "egfr": "estimated_glomerular_filtration_rate",
            "acr": "albumin_creatinine_ratio",
            "ua": "uric_acid",
        },
        "thresholds": {
            "estimated_glomerular_filtration_rate": {
                "normal": (90, 200),
                "stage_1": (60, 90),
                "stage_2": (45, 60),
                "stage_3": (30, 45),
                "stage_4": (15, 30),
                "stage_5_dialysis": (0, 15),
            },
            "creatinine": {
                "normal_male": (0.7, 1.3),
                "normal_female": (0.6, 1.1),
                "elevated": (1.3, 5.0),
                "critical": (5.0, 20.0),
            },
            "potassium": {
                "critical_low": (0, 3.0),
                "low": (3.0, 3.5),
                "normal": (3.5, 5.0),
                "high": (5.0, 5.5),
                "critical_high": (5.5, 10.0),
            },
        },
        "deterioration_rules": [
            {
                "parameter": "estimated_glomerular_filtration_rate",
                "condition": "falling",
                "threshold_delta": 5.0,
                "window_months": 12,
                "message": "eGFR declining {delta} mL/min/year — CKD progression",
                "severity": "critical",
            },
        ],
        "co_monitoring": [
            {"primary": "creatinine", "required": ["estimated_glomerular_filtration_rate", "albumin_creatinine_ratio"], "reason": "Creatinine alone cannot stage CKD — requires eGFR + urine ACR"},
            {"primary": "estimated_glomerular_filtration_rate", "required": ["potassium", "calcium"], "reason": "eGFR <30 mandates electrolyte monitoring"},
        ],
    },

    DiseaseCategory.CARDIAC: {
        "canonical_parameters": [
            "troponin_i", "troponin_t", "brain_natriuretic_peptide", "creatine_phosphokinase",
            "ldl_cholesterol", "hdl_cholesterol", "triglycerides", "total_cholesterol",
            "international_normalized_ratio", "prothrombin_time",
        ],
        "aliases": {
            "bnp": "brain_natriuretic_peptide",
            "cpk": "creatine_phosphokinase",
            "ldl": "ldl_cholesterol",
            "hdl": "hdl_cholesterol",
            "tg": "triglycerides",
            "tc": "total_cholesterol",
            "inr": "international_normalized_ratio",
            "pt": "prothrombin_time",
        },
        "thresholds": {
            "troponin_i": {
                "normal": (0, 0.04),
                "elevated": (0.04, 0.4),
                "ami_likely": (0.4, 50.0),
            },
            "brain_natriuretic_peptide": {
                "normal": (0, 100),
                "borderline_hf": (100, 400),
                "heart_failure": (400, 50000),
            },
            "ldl_cholesterol": {
                "optimal": (0, 100),
                "near_optimal": (100, 130),
                "borderline_high": (130, 160),
                "high": (160, 190),
                "very_high": (190, 500),
            },
        },
        "deterioration_rules": [
            {
                "parameter": "ldl_cholesterol",
                "condition": "rising",
                "threshold_delta": 20.0,
                "window_months": 6,
                "message": "LDL rising {delta} mg/dL — statin efficacy may be inadequate",
                "severity": "warning",
            },
        ],
        "co_monitoring": [
            {"primary": "international_normalized_ratio", "required": ["prothrombin_time"], "reason": "INR must be interpreted alongside PT"},
        ],
    },

    DiseaseCategory.ANEMIA: {
        "canonical_parameters": [
            "hemoglobin", "hematocrit", "mean_corpuscular_volume",
            "mean_corpuscular_hemoglobin", "ferritin", "iron",
            "total_iron_binding_capacity", "vitamin_b12", "folate",
            "reticulocyte_count",
        ],
        "aliases": {
            "hb": "hemoglobin",
            "hgb": "hemoglobin",
            "hct": "hematocrit",
            "mcv": "mean_corpuscular_volume",
            "mch": "mean_corpuscular_hemoglobin",
            "tibc": "total_iron_binding_capacity",
        },
        "thresholds": {
            "hemoglobin": {
                "critical_low_male": (0, 7.0),
                "anemia_male": (7.0, 13.0),
                "normal_male": (13.0, 17.5),
                "critical_low_female": (0, 7.0),
                "anemia_female": (7.0, 12.0),
                "normal_female": (12.0, 15.5),
            },
            "ferritin": {
                "depleted": (0, 12),
                "low": (12, 30),
                "normal": (30, 300),
                "elevated": (300, 1000),
                "critical_high": (1000, 10000),
            },
        },
        "deterioration_rules": [
            {
                "parameter": "hemoglobin",
                "condition": "falling",
                "threshold_delta": 2.0,
                "window_months": 3,
                "message": "Hemoglobin dropping {delta} g/dL — investigate active blood loss or bone marrow suppression",
                "severity": "critical",
            },
        ],
        "co_monitoring": [
            {"primary": "hemoglobin", "required": ["ferritin", "mean_corpuscular_volume"], "reason": "Hemoglobin alone cannot classify anemia type — requires MCV + ferritin for iron-deficiency vs B12/folate deficiency"},
        ],
    },

    DiseaseCategory.LIVER: {
        "canonical_parameters": [
            "alanine_transaminase", "aspartate_transaminase",
            "alkaline_phosphatase", "gamma_glutamyl_transferase",
            "total_bilirubin", "direct_bilirubin", "albumin",
            "total_protein", "international_normalized_ratio",
        ],
        "aliases": {
            "alt": "alanine_transaminase",
            "sgpt": "alanine_transaminase",
            "ast": "aspartate_transaminase",
            "sgot": "aspartate_transaminase",
            "alp": "alkaline_phosphatase",
            "ggt": "gamma_glutamyl_transferase",
        },
        "thresholds": {
            "alanine_transaminase": {
                "normal": (0, 40),
                "mild_elevation": (40, 120),
                "moderate_elevation": (120, 400),
                "severe_elevation": (400, 10000),
            },
            "total_bilirubin": {
                "normal": (0, 1.2),
                "mild_jaundice": (1.2, 3.0),
                "moderate_jaundice": (3.0, 10.0),
                "severe_jaundice": (10.0, 50.0),
            },
            "albumin": {
                "low": (0, 3.5),
                "normal": (3.5, 5.0),
            },
        },
        "deterioration_rules": [
            {
                "parameter": "alanine_transaminase",
                "condition": "rising",
                "threshold_delta": 50.0,
                "window_months": 1,
                "message": "ALT rising {delta} U/L — possible acute hepatic injury",
                "severity": "critical",
            },
        ],
        "co_monitoring": [
            {"primary": "alanine_transaminase", "required": ["aspartate_transaminase", "alkaline_phosphatase"], "reason": "AST:ALT ratio differentiates alcoholic vs non-alcoholic liver disease"},
        ],
    },
}


class DiseaseProtocolEngine:
    def __init__(self):
        self._panels = DISEASE_PANELS

    def detect_disease_category(self, parameter_names: list[str]) -> list[DiseaseCategory]:
        normalized = {self._normalize(p) for p in parameter_names}
        detected = []

        for category, panel in self._panels.items():
            canonical = set(panel["canonical_parameters"])
            aliases = set(panel.get("aliases", {}).keys())
            all_terms = canonical | aliases

            overlap = normalized & all_terms
            if len(overlap) >= 2:
                detected.append(category)

        return detected

    def interpret_parameter(
        self,
        parameter_name: str,
        value: float,
        category: DiseaseCategory,
        sex: str = "any",
    ) -> dict:
        normalized = self._normalize(parameter_name)
        panel = self._panels.get(category)
        if not panel:
            return {"status": "unknown_category", "parameter": normalized}

        aliases = panel.get("aliases", {})
        canonical = aliases.get(normalized, normalized)

        thresholds = panel.get("thresholds", {}).get(canonical, {})
        if not thresholds:
            return {
                "parameter": canonical,
                "value": value,
                "category": category.value,
                "status": "no_disease_specific_threshold",
            }

        matched_ranges = []
        for label, (low, high) in thresholds.items():
            if sex != "any" and sex in label.split("_"):
                pass
            elif sex != "any" and any(s in label for s in ["male", "female"]) and sex not in label:
                continue

            if low <= value < high:
                matched_ranges.append(label)

        status = matched_ranges[0] if matched_ranges else "out_of_all_ranges"

        severity = "info"
        if any(k in status for k in ("critical", "severe", "stage_5", "ami_likely")):
            severity = "critical"
        elif any(k in status for k in ("diabetic", "hypothyroid", "heart_failure", "elevated", "high", "anemia", "stage_3", "stage_4")):
            severity = "warning"
        elif any(k in status for k in ("prediabetic", "subclinical", "borderline", "low", "mild")):
            severity = "attention"

        return {
            "parameter": canonical,
            "value": value,
            "category": category.value,
            "status": status,
            "severity": severity,
            "all_matched_ranges": matched_ranges,
        }

    def check_co_monitoring_gaps(
        self,
        parameter_names: list[str],
        category: DiseaseCategory,
    ) -> list[dict]:
        normalized = {self._normalize(p) for p in parameter_names}
        panel = self._panels.get(category)
        if not panel:
            return []

        aliases = panel.get("aliases", {})

        def resolve(name: str) -> str:
            n = self._normalize(name)
            return aliases.get(n, n)

        resolved = {resolve(p) for p in parameter_names}

        gaps = []
        for rule in panel.get("co_monitoring", []):
            primary = rule["primary"]
            if primary in resolved:
                missing = [r for r in rule["required"] if r not in resolved]
                if missing:
                    gaps.append({
                        "primary_parameter": primary,
                        "missing_parameters": missing,
                        "reason": rule["reason"],
                        "category": category.value,
                    })

        return gaps

    def evaluate_trend(
        self,
        parameter_name: str,
        data_points: list[dict],
        category: DiseaseCategory,
    ) -> list[dict]:
        panel = self._panels.get(category)
        if not panel:
            return []

        normalized = self._normalize(parameter_name)
        aliases = panel.get("aliases", {})
        canonical = aliases.get(normalized, normalized)

        alerts = []
        for rule in panel.get("deterioration_rules", []):
            if rule["parameter"] != canonical:
                continue

            if len(data_points) < 2:
                continue

            sorted_points = sorted(data_points, key=lambda p: p.get("date", ""))
            first_val = sorted_points[0].get("value")
            last_val = sorted_points[-1].get("value")

            if first_val is None or last_val is None:
                continue

            delta = last_val - first_val

            if rule["condition"] == "rising" and delta >= rule["threshold_delta"]:
                alerts.append({
                    "parameter": canonical,
                    "condition": "rising",
                    "delta": round(delta, 2),
                    "severity": rule["severity"],
                    "message": rule["message"].format(delta=round(abs(delta), 2), months=rule["window_months"]),
                })
            elif rule["condition"] == "falling" and delta <= -rule["threshold_delta"]:
                alerts.append({
                    "parameter": canonical,
                    "condition": "falling",
                    "delta": round(abs(delta), 2),
                    "severity": rule["severity"],
                    "message": rule["message"].format(delta=round(abs(delta), 2), months=rule["window_months"]),
                })

        return alerts

    def full_analysis(
        self,
        parameters: list[dict],
        sex: str = "any",
    ) -> dict:
        param_names = [p.get("name", p.get("parameter_name", "")) for p in parameters]
        categories = self.detect_disease_category(param_names)

        interpretations = []
        co_monitoring_gaps = []
        trend_alerts = []

        for category in categories:
            for param in parameters:
                name = param.get("name", param.get("parameter_name", ""))
                value = param.get("value_numeric")
                if value is not None:
                    interpretation = self.interpret_parameter(name, float(value), category, sex)
                    if interpretation.get("status") != "no_disease_specific_threshold":
                        interpretations.append(interpretation)

            gaps = self.check_co_monitoring_gaps(param_names, category)
            co_monitoring_gaps.extend(gaps)

            for param in parameters:
                name = param.get("name", param.get("parameter_name", ""))
                trend_data = param.get("trend_data", [])
                if trend_data:
                    alerts = self.evaluate_trend(name, trend_data, category)
                    trend_alerts.extend(alerts)

        critical_count = sum(1 for i in interpretations if i.get("severity") == "critical")
        warning_count = sum(1 for i in interpretations if i.get("severity") == "warning")

        return {
            "detected_categories": [c.value for c in categories],
            "interpretations": interpretations,
            "co_monitoring_gaps": co_monitoring_gaps,
            "trend_alerts": trend_alerts,
            "critical_findings": critical_count,
            "warning_findings": warning_count,
            "has_critical": critical_count > 0,
        }

    def _normalize(self, name: str) -> str:
        return re.sub(r"[^a-z0-9_]", "", name.lower().strip().replace(" ", "_"))


disease_engine = DiseaseProtocolEngine()
