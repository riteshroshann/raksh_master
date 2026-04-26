import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.rcm import (
    ClaimGuardPredictor,
    BillVerificationEngine,
    X12Parser,
    ClaimStatus,
    DenialReason,
)


class TestClaimGuardPredictor:
    def setup_method(self):
        self.predictor = ClaimGuardPredictor()

    def test_low_risk_claim(self):
        claim = {
            "claim_id": "CLM001",
            "prior_auth_number": "AUTH123",
            "out_of_network": False,
            "procedure_codes": ["99213"],
            "service_date": "2024-01-15",
            "potential_duplicate": False,
            "modifier_required": False,
            "diagnosis_codes": ["E11.9"],
            "eligibility_unverified": False,
            "total_charge": 150.00,
            "average_charge_for_procedure": 145.00,
        }
        result = self.predictor.predict_denial_risk(claim)
        assert result["risk_level"] == "low"
        assert result["denial_probability"] < 0.25

    def test_high_risk_missing_auth(self):
        claim = {
            "claim_id": "CLM002",
            "out_of_network": True,
            "procedure_codes": ["27447", "27486", "27487", "27488", "20930", "20680"],
            "service_date": "2024-01-15",
            "potential_duplicate": False,
            "modifier_required": True,
            "modifiers": [],
            "diagnosis_codes": ["M17.11"],
            "eligibility_unverified": True,
            "total_charge": 45000.00,
            "average_charge_for_procedure": 35000.00,
        }
        result = self.predictor.predict_denial_risk(claim)
        assert result["risk_level"] in ("high", "critical")
        assert result["denial_probability"] > 0.50
        assert len(result["risk_factors"]) >= 3

    def test_duplicate_claim_detection(self):
        claim = {
            "claim_id": "CLM003",
            "prior_auth_number": "AUTH456",
            "potential_duplicate": True,
            "procedure_codes": ["99213"],
            "service_date": "2024-01-15",
        }
        result = self.predictor.predict_denial_risk(claim)
        assert any(f["factor"] == "duplicate_window_match" for f in result["risk_factors"])

    def test_recommendation_low_risk(self):
        claim = {
            "claim_id": "CLM_LOW",
            "prior_auth_number": "A",
            "procedure_codes": ["99213"],
            "service_date": "2024-01-15",
            "payer_historical_denial_rate": 0.02,
        }
        result = self.predictor.predict_denial_risk(claim)
        assert "Low" in result["recommendation"] or "Proceed" in result["recommendation"] or "Moderate" in result["recommendation"]

    def test_recommendation_critical_risk(self):
        claim = {
            "claim_id": "CLM_CRIT",
            "out_of_network": True,
            "procedure_codes": ["27447", "27486", "27487", "27488", "20930", "20680"],
            "potential_duplicate": True,
            "modifier_required": True,
            "modifiers": [],
            "eligibility_unverified": True,
            "total_charge": 100000.00,
            "average_charge_for_procedure": 35000.00,
        }
        result = self.predictor.predict_denial_risk(claim)
        assert "DO NOT submit" in result["recommendation"] or "Critical" in result["recommendation"]

    def test_batch_predict(self):
        claims = [
            {"claim_id": "A", "prior_auth_number": "X", "procedure_codes": ["99213"]},
            {"claim_id": "B", "out_of_network": True, "eligibility_unverified": True},
        ]
        results = self.predictor.batch_predict(claims)
        assert len(results) == 2
        assert results[0]["denial_probability"] < results[1]["denial_probability"]

    def test_probability_bounded_zero_one(self):
        extreme_claim = {
            "out_of_network": True,
            "potential_duplicate": True,
            "modifier_required": True,
            "modifiers": [],
            "eligibility_unverified": True,
            "total_charge": 999999.00,
            "average_charge_for_procedure": 100.00,
            "payer_historical_denial_rate": 0.99,
        }
        result = self.predictor.predict_denial_risk(extreme_claim)
        assert 0.0 <= result["denial_probability"] <= 1.0


class TestBillVerificationEngine:
    def setup_method(self):
        self.verifier = BillVerificationEngine()
        self.verifier.load_rate_sheet("test_payer", {
            "99213": 150.00,
            "99214": 225.00,
            "36415": 12.00,
            "80053": 45.00,
        })

    def test_no_discrepancies(self):
        bill = {
            "payer": "test_payer",
            "line_items": [
                {"procedure_code": "99213", "billed_amount": 150.00, "quantity": 1},
                {"procedure_code": "36415", "billed_amount": 12.00, "quantity": 1},
            ],
        }
        result = self.verifier.verify_bill(bill)
        assert result["discrepancy_count"] == 0
        assert result["savings_opportunity"] == 0

    def test_overcharge_detected(self):
        bill = {
            "payer": "test_payer",
            "line_items": [
                {"procedure_code": "99213", "billed_amount": 300.00, "quantity": 1, "description": "Office Visit"},
            ],
        }
        result = self.verifier.verify_bill(bill)
        assert result["discrepancy_count"] == 1
        assert result["discrepancies"][0]["variance"] == 150.00
        assert result["savings_opportunity"] == 150.00

    def test_multiple_discrepancies(self):
        bill = {
            "payer": "test_payer",
            "line_items": [
                {"procedure_code": "99213", "billed_amount": 300.00, "quantity": 1},
                {"procedure_code": "99214", "billed_amount": 500.00, "quantity": 1},
            ],
        }
        result = self.verifier.verify_bill(bill)
        assert result["discrepancy_count"] == 2

    def test_unknown_payer(self):
        bill = {
            "payer": "unknown_payer",
            "line_items": [
                {"procedure_code": "99213", "billed_amount": 300.00, "quantity": 1},
            ],
        }
        result = self.verifier.verify_bill(bill)
        assert result["discrepancy_count"] == 0

    def test_quantity_multiplication(self):
        bill = {
            "payer": "test_payer",
            "line_items": [
                {"procedure_code": "80053", "billed_amount": 135.00, "quantity": 3},
            ],
        }
        result = self.verifier.verify_bill(bill)
        assert result["discrepancy_count"] == 0

    def test_within_tolerance(self):
        bill = {
            "payer": "test_payer",
            "line_items": [
                {"procedure_code": "99213", "billed_amount": 153.00, "quantity": 1},
            ],
        }
        result = self.verifier.verify_bill(bill)
        assert result["discrepancy_count"] == 0


class TestX12Parser:
    def setup_method(self):
        self.parser = X12Parser()

    def test_parse_837_basic(self):
        raw = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       *240115*1200*^*00501*000000001*0*P*:~"
            "CLM*CLM001*250.00*11:B:1~"
            "SV1*HC:99213*150.00*UN*1~"
            "SV1*HC:36415*12.00*UN*1~"
            "HI*ABK:E11.9*ABF:I10~"
        )
        result = self.parser.parse_837(raw)

        assert result["transaction_type"] == "837"
        assert result["total_claims"] == 1
        assert result["claims"][0]["claim_id"] == "CLM001"
        assert result["claims"][0]["total_charge"] == 250.00
        assert len(result["claims"][0]["service_lines"]) == 2
        assert result["claims"][0]["service_lines"][0]["procedure_code"] == "99213"

    def test_parse_837_multiple_claims(self):
        raw = (
            "ISA*00*          *00*          *ZZ*SENDER         *ZZ*RECEIVER       ~"
            "CLM*CLM001*100.00~"
            "SV1*HC:99213*100.00*UN*1~"
            "CLM*CLM002*200.00~"
            "SV1*HC:99214*200.00*UN*1~"
        )
        result = self.parser.parse_837(raw)
        assert result["total_claims"] == 2
        assert result["total_charges"] == 300.00

    def test_parse_835_basic(self):
        raw = (
            "ISA*00*          ~"
            "BPR*I*1000.00~"
            "CLP*CLM001*1*500.00*450.00~"
            "CAS*CO*45*50.00~"
            "CLP*CLM002*1*500.00*500.00~"
        )
        result = self.parser.parse_835(raw)

        assert result["transaction_type"] == "835"
        assert result["payment_info"]["total_payment"] == 1000.00
        assert result["total_claims"] == 2
        assert result["claims"][0]["claim_id"] == "CLM001"
        assert result["claims"][0]["payment_amount"] == 450.00
        assert len(result["claims"][0]["adjustments"]) == 1

    def test_parse_empty_data(self):
        result = self.parser.parse_837("")
        assert result["total_claims"] == 0

    def test_parse_835_no_adjustments(self):
        raw = "BPR*I*500.00~CLP*CLM001*1*500.00*500.00~"
        result = self.parser.parse_835(raw)
        assert result["claims"][0]["adjustments"] == []


class TestClaimStatusEnum:
    def test_all_statuses(self):
        expected = {"pending", "submitted", "accepted", "denied", "appealed", "paid", "partial", "voided"}
        actual = {s.value for s in ClaimStatus}
        assert actual == expected

    def test_denial_reasons(self):
        assert len(DenialReason) >= 10
