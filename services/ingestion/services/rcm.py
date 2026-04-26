import re
import json
from datetime import datetime, date
from typing import Optional
from enum import Enum

import structlog

logger = structlog.get_logger()


class ClaimStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    DENIED = "denied"
    APPEALED = "appealed"
    PAID = "paid"
    PARTIAL = "partial"
    VOIDED = "voided"


class DenialReason(str, Enum):
    DUPLICATE = "duplicate_claim"
    MISSING_INFO = "missing_information"
    NOT_COVERED = "service_not_covered"
    AUTHORIZATION = "prior_authorization_required"
    TIMELY_FILING = "timely_filing_exceeded"
    CODING_ERROR = "coding_error"
    ELIGIBILITY = "patient_eligibility"
    MEDICAL_NECESSITY = "medical_necessity"
    BUNDLING = "procedure_bundling"
    COORDINATION = "coordination_of_benefits"


DENIAL_RISK_FEATURES = {
    "missing_authorization": 0.35,
    "out_of_network": 0.28,
    "timely_filing_risk": 0.22,
    "coding_mismatch": 0.18,
    "duplicate_submission": 0.15,
    "missing_modifier": 0.12,
    "invalid_diagnosis_code": 0.25,
    "age_gender_mismatch": 0.10,
    "frequency_exceeded": 0.14,
    "non_covered_service": 0.30,
}


class ClaimGuardPredictor:
    def __init__(self):
        self._feature_weights = {
            "missing_authorization": 0.85,
            "out_of_network_provider": 0.72,
            "coding_complexity_high": 0.45,
            "timely_filing_days_remaining": -0.03,
            "duplicate_window_match": 0.90,
            "modifier_missing": 0.55,
            "diagnosis_procedure_mismatch": 0.68,
            "patient_eligibility_gap": 0.78,
            "historical_denial_rate_payer": 0.40,
            "claim_amount_outlier": 0.35,
        }
        self._base_denial_rate = 0.08
        self._threshold = 0.50

    def predict_denial_risk(self, claim: dict) -> dict:
        features = self._extract_features(claim)
        score = self._compute_score(features)
        risk_factors = self._identify_risk_factors(features)

        prediction = {
            "denial_probability": round(score, 4),
            "risk_level": self._risk_level(score),
            "recommendation": self._generate_recommendation(score, risk_factors),
            "risk_factors": risk_factors,
            "features_computed": len(features),
            "threshold": self._threshold,
        }

        logger.info(
            "claim_denial_prediction",
            claim_id=claim.get("claim_id"),
            probability=prediction["denial_probability"],
            risk_level=prediction["risk_level"],
        )

        return prediction

    def batch_predict(self, claims: list[dict]) -> list[dict]:
        return [self.predict_denial_risk(claim) for claim in claims]

    def _extract_features(self, claim: dict) -> dict:
        features = {}

        features["missing_authorization"] = 1.0 if not claim.get("prior_auth_number") else 0.0

        features["out_of_network_provider"] = 1.0 if claim.get("out_of_network", False) else 0.0

        procedures = claim.get("procedure_codes", [])
        features["coding_complexity_high"] = 1.0 if len(procedures) > 5 else len(procedures) / 10.0

        filing_date = claim.get("service_date")
        if filing_date:
            try:
                if isinstance(filing_date, str):
                    svc_date = datetime.strptime(filing_date, "%Y-%m-%d").date()
                else:
                    svc_date = filing_date
                days_elapsed = (date.today() - svc_date).days
                days_limit = claim.get("timely_filing_limit", 90)
                features["timely_filing_days_remaining"] = max(0, days_limit - days_elapsed)
            except (ValueError, TypeError):
                features["timely_filing_days_remaining"] = 90

        features["duplicate_window_match"] = 1.0 if claim.get("potential_duplicate", False) else 0.0

        modifiers = claim.get("modifiers", [])
        needs_modifier = claim.get("modifier_required", False)
        features["modifier_missing"] = 1.0 if needs_modifier and not modifiers else 0.0

        dx_codes = claim.get("diagnosis_codes", [])
        px_codes = claim.get("procedure_codes", [])
        features["diagnosis_procedure_mismatch"] = self._check_dx_px_compatibility(dx_codes, px_codes)

        features["patient_eligibility_gap"] = 1.0 if claim.get("eligibility_unverified", False) else 0.0

        payer_denial_history = claim.get("payer_historical_denial_rate", 0.08)
        features["historical_denial_rate_payer"] = payer_denial_history

        amount = claim.get("total_charge", 0)
        avg_for_procedure = claim.get("average_charge_for_procedure", amount)
        if avg_for_procedure > 0:
            ratio = amount / avg_for_procedure
            features["claim_amount_outlier"] = max(0, ratio - 1.5) / 2.0
        else:
            features["claim_amount_outlier"] = 0.0

        return features

    def _compute_score(self, features: dict) -> float:
        score = self._base_denial_rate

        for feature_name, feature_value in features.items():
            weight = self._feature_weights.get(feature_name, 0.0)
            score += weight * feature_value

        return max(0.0, min(1.0, score))

    def _risk_level(self, score: float) -> str:
        if score >= 0.75:
            return "critical"
        elif score >= 0.50:
            return "high"
        elif score >= 0.25:
            return "medium"
        return "low"

    def _identify_risk_factors(self, features: dict) -> list[dict]:
        risk_factors = []

        factor_descriptions = {
            "missing_authorization": "Prior authorization not obtained",
            "out_of_network_provider": "Provider is out of network",
            "coding_complexity_high": "High coding complexity increases audit risk",
            "duplicate_window_match": "Potential duplicate claim detected",
            "modifier_missing": "Required modifier not present on procedure code",
            "diagnosis_procedure_mismatch": "Diagnosis codes may not support procedure",
            "patient_eligibility_gap": "Patient eligibility not verified",
            "historical_denial_rate_payer": "Payer has elevated historical denial rate",
            "claim_amount_outlier": "Claim amount significantly above average",
        }

        for feature_name, feature_value in features.items():
            if feature_name == "timely_filing_days_remaining":
                if feature_value < 15:
                    risk_factors.append({
                        "factor": "timely_filing_risk",
                        "severity": "high" if feature_value < 7 else "medium",
                        "description": f"Only {int(feature_value)} days remaining for timely filing",
                        "value": feature_value,
                    })
                continue

            if feature_value > 0.3:
                risk_factors.append({
                    "factor": feature_name,
                    "severity": "high" if feature_value > 0.7 else "medium",
                    "description": factor_descriptions.get(feature_name, feature_name),
                    "value": round(feature_value, 3),
                })

        return sorted(risk_factors, key=lambda x: x["value"], reverse=True)

    def _generate_recommendation(self, score: float, risk_factors: list[dict]) -> str:
        if score < 0.25:
            return "Low denial risk. Proceed with submission."
        elif score < 0.50:
            return f"Moderate risk. Review {len(risk_factors)} risk factor(s) before submission."
        elif score < 0.75:
            return f"High denial risk. Address {len(risk_factors)} issue(s) before submission. Consider peer review."
        return f"Critical denial risk ({score:.0%}). DO NOT submit without resolving all {len(risk_factors)} flagged issues."

    def _check_dx_px_compatibility(self, dx_codes: list[str], px_codes: list[str]) -> float:
        if not dx_codes or not px_codes:
            return 0.5

        return 0.0


class BillVerificationEngine:
    def __init__(self):
        self._rate_sheets: dict[str, dict[str, float]] = {}

    def load_rate_sheet(self, payer_name: str, rates: dict[str, float]) -> None:
        self._rate_sheets[payer_name.lower()] = rates
        logger.info("rate_sheet_loaded", payer=payer_name, items=len(rates))

    def verify_bill(self, bill: dict) -> dict:
        payer = bill.get("payer", "").lower()
        rate_sheet = self._rate_sheets.get(payer, {})
        line_items = bill.get("line_items", [])

        discrepancies = []
        total_billed = 0.0
        total_expected = 0.0

        for item in line_items:
            code = item.get("procedure_code", "")
            billed_amount = item.get("billed_amount", 0.0)
            quantity = item.get("quantity", 1)

            total_billed += billed_amount

            expected_rate = rate_sheet.get(code)
            if expected_rate is not None:
                expected_total = expected_rate * quantity
                total_expected += expected_total

                variance = billed_amount - expected_total
                variance_pct = (variance / expected_total * 100) if expected_total > 0 else 0

                if abs(variance_pct) > 5.0:
                    discrepancies.append({
                        "procedure_code": code,
                        "description": item.get("description", ""),
                        "billed_amount": billed_amount,
                        "expected_amount": expected_total,
                        "variance": round(variance, 2),
                        "variance_pct": round(variance_pct, 2),
                        "severity": "high" if abs(variance_pct) > 20 else "medium",
                    })
            else:
                total_expected += billed_amount

        savings_opportunity = sum(d["variance"] for d in discrepancies if d["variance"] > 0)

        return {
            "total_billed": round(total_billed, 2),
            "total_expected": round(total_expected, 2),
            "total_variance": round(total_billed - total_expected, 2),
            "savings_opportunity": round(savings_opportunity, 2),
            "discrepancy_count": len(discrepancies),
            "discrepancies": discrepancies,
            "line_items_reviewed": len(line_items),
            "payer": payer,
            "verification_timestamp": datetime.utcnow().isoformat(),
        }


class X12Parser:
    def __init__(self):
        self._segment_separator = "~"
        self._element_separator = "*"
        self._sub_element_separator = ":"

    def parse_837(self, raw_data: str) -> dict:
        segments = self._split_segments(raw_data)

        claim = {
            "transaction_type": "837",
            "claims": [],
            "sender": {},
            "receiver": {},
            "patients": [],
        }

        current_claim = None
        current_patient = None

        for segment in segments:
            elements = segment.split(self._element_separator)
            segment_id = elements[0].strip()

            if segment_id == "ISA" and len(elements) >= 16:
                claim["sender"]["qualifier"] = elements[5] if len(elements) > 5 else ""
                claim["sender"]["id"] = elements[6].strip() if len(elements) > 6 else ""
                claim["receiver"]["qualifier"] = elements[7] if len(elements) > 7 else ""
                claim["receiver"]["id"] = elements[8].strip() if len(elements) > 8 else ""

            elif segment_id == "CLM" and len(elements) >= 3:
                if current_claim:
                    claim["claims"].append(current_claim)
                current_claim = {
                    "claim_id": elements[1] if len(elements) > 1 else "",
                    "total_charge": self._safe_float(elements[2]) if len(elements) > 2 else 0,
                    "service_lines": [],
                    "diagnosis_codes": [],
                }

            elif segment_id == "SV1" and current_claim and len(elements) >= 5:
                procedure_info = elements[1].split(self._sub_element_separator) if len(elements) > 1 else []
                current_claim["service_lines"].append({
                    "procedure_code": procedure_info[1] if len(procedure_info) > 1 else "",
                    "charge": self._safe_float(elements[2]) if len(elements) > 2 else 0,
                    "unit_type": elements[3] if len(elements) > 3 else "",
                    "quantity": self._safe_float(elements[4]) if len(elements) > 4 else 1,
                })

            elif segment_id == "HI" and current_claim:
                for i in range(1, len(elements)):
                    code_parts = elements[i].split(self._sub_element_separator)
                    if len(code_parts) >= 2:
                        current_claim["diagnosis_codes"].append({
                            "qualifier": code_parts[0],
                            "code": code_parts[1],
                        })

            elif segment_id == "NM1" and len(elements) >= 4:
                entity_type = elements[1] if len(elements) > 1 else ""
                name_last = elements[3] if len(elements) > 3 else ""
                name_first = elements[4] if len(elements) > 4 else ""

                if entity_type == "IL":
                    current_patient = {
                        "name": f"{name_first} {name_last}".strip(),
                        "entity_type": "subscriber",
                    }
                    claim["patients"].append(current_patient)

            elif segment_id == "DMG" and current_patient and len(elements) >= 4:
                current_patient["dob"] = elements[2] if len(elements) > 2 else ""
                current_patient["gender"] = elements[3] if len(elements) > 3 else ""

        if current_claim:
            claim["claims"].append(current_claim)

        claim["total_claims"] = len(claim["claims"])
        claim["total_charges"] = sum(c.get("total_charge", 0) for c in claim["claims"])

        return claim

    def parse_835(self, raw_data: str) -> dict:
        segments = self._split_segments(raw_data)

        remittance = {
            "transaction_type": "835",
            "payment_info": {},
            "claims": [],
        }

        current_claim = None

        for segment in segments:
            elements = segment.split(self._element_separator)
            segment_id = elements[0].strip()

            if segment_id == "BPR" and len(elements) >= 3:
                remittance["payment_info"] = {
                    "transaction_type": elements[1] if len(elements) > 1 else "",
                    "total_payment": self._safe_float(elements[2]) if len(elements) > 2 else 0,
                }

            elif segment_id == "CLP" and len(elements) >= 5:
                if current_claim:
                    remittance["claims"].append(current_claim)
                current_claim = {
                    "claim_id": elements[1] if len(elements) > 1 else "",
                    "status": elements[2] if len(elements) > 2 else "",
                    "total_charge": self._safe_float(elements[3]) if len(elements) > 3 else 0,
                    "payment_amount": self._safe_float(elements[4]) if len(elements) > 4 else 0,
                    "adjustments": [],
                }

            elif segment_id == "CAS" and current_claim and len(elements) >= 4:
                current_claim["adjustments"].append({
                    "group_code": elements[1] if len(elements) > 1 else "",
                    "reason_code": elements[2] if len(elements) > 2 else "",
                    "amount": self._safe_float(elements[3]) if len(elements) > 3 else 0,
                })

        if current_claim:
            remittance["claims"].append(current_claim)

        remittance["total_claims"] = len(remittance["claims"])

        return remittance

    def _split_segments(self, data: str) -> list[str]:
        data = data.replace("\n", "").replace("\r", "")
        segments = data.split(self._segment_separator)
        return [s.strip() for s in segments if s.strip()]

    def _safe_float(self, value: str) -> float:
        try:
            return float(value.strip())
        except (ValueError, AttributeError):
            return 0.0


claim_guard = ClaimGuardPredictor()
bill_verifier = BillVerificationEngine()
x12_parser = X12Parser()
