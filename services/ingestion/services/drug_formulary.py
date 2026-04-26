import re
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger()


class DrugSchedule(str, Enum):
    OTC = "otc"
    H = "H"
    H1 = "H1"
    X = "X"
    G = "G"
    J = "J"


class DosageForm(str, Enum):
    TABLET = "tablet"
    CAPSULE = "capsule"
    SYRUP = "syrup"
    INJECTION = "injection"
    INHALER = "inhaler"
    DROPS = "drops"
    OINTMENT = "ointment"
    CREAM = "cream"
    GEL = "gel"
    SUSPENSION = "suspension"
    POWDER = "powder"
    PATCH = "patch"
    SUPPOSITORY = "suppository"
    NEBULIZER = "nebulizer"


THERAPEUTIC_RANGES = {
    "metformin": {"min_mg": 250, "max_mg": 2550, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "glimepiride": {"min_mg": 1, "max_mg": 8, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "atorvastatin": {"min_mg": 10, "max_mg": 80, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "rosuvastatin": {"min_mg": 5, "max_mg": 40, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "amlodipine": {"min_mg": 2.5, "max_mg": 10, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "telmisartan": {"min_mg": 20, "max_mg": 80, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "losartan": {"min_mg": 25, "max_mg": 100, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "ramipril": {"min_mg": 1.25, "max_mg": 10, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "aspirin": {"min_mg": 75, "max_mg": 325, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.OTC},
    "clopidogrel": {"min_mg": 75, "max_mg": 300, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "warfarin": {"min_mg": 1, "max_mg": 10, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "enoxaparin": {"min_mg": 20, "max_mg": 150, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "metoprolol": {"min_mg": 25, "max_mg": 200, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "atenolol": {"min_mg": 25, "max_mg": 100, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "furosemide": {"min_mg": 20, "max_mg": 80, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "hydrochlorothiazide": {"min_mg": 12.5, "max_mg": 50, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "omeprazole": {"min_mg": 20, "max_mg": 40, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "pantoprazole": {"min_mg": 20, "max_mg": 80, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "levothyroxine": {"min_mg": 0.025, "max_mg": 0.3, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "azithromycin": {"min_mg": 250, "max_mg": 500, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H1},
    "amoxicillin": {"min_mg": 250, "max_mg": 1000, "unit": "mg", "frequency": "per_dose", "schedule": DrugSchedule.H},
    "ciprofloxacin": {"min_mg": 250, "max_mg": 750, "unit": "mg", "frequency": "per_dose", "schedule": DrugSchedule.H},
    "paracetamol": {"min_mg": 325, "max_mg": 1000, "unit": "mg", "frequency": "per_dose", "schedule": DrugSchedule.OTC},
    "ibuprofen": {"min_mg": 200, "max_mg": 800, "unit": "mg", "frequency": "per_dose", "schedule": DrugSchedule.OTC},
    "diclofenac": {"min_mg": 25, "max_mg": 75, "unit": "mg", "frequency": "per_dose", "schedule": DrugSchedule.H},
    "prednisolone": {"min_mg": 5, "max_mg": 60, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "dexamethasone": {"min_mg": 0.5, "max_mg": 16, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "insulin_glargine": {"min_mg": 10, "max_mg": 80, "unit": "units", "frequency": "daily", "schedule": DrugSchedule.H},
    "insulin_regular": {"min_mg": 2, "max_mg": 100, "unit": "units", "frequency": "per_dose", "schedule": DrugSchedule.H},
    "methotrexate": {"min_mg": 7.5, "max_mg": 25, "unit": "mg", "frequency": "weekly", "schedule": DrugSchedule.H},
    "digoxin": {"min_mg": 0.0625, "max_mg": 0.25, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "phenytoin": {"min_mg": 100, "max_mg": 600, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "lithium": {"min_mg": 300, "max_mg": 1800, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "sitagliptin": {"min_mg": 25, "max_mg": 100, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "empagliflozin": {"min_mg": 10, "max_mg": 25, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "pioglitazone": {"min_mg": 15, "max_mg": 45, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "carvedilol": {"min_mg": 3.125, "max_mg": 50, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "spironolactone": {"min_mg": 25, "max_mg": 100, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "montelukast": {"min_mg": 4, "max_mg": 10, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.H},
    "salbutamol": {"min_mg": 2, "max_mg": 8, "unit": "mg", "frequency": "per_dose", "schedule": DrugSchedule.H},
    "cetirizine": {"min_mg": 5, "max_mg": 10, "unit": "mg", "frequency": "daily", "schedule": DrugSchedule.OTC},
}


CRITICAL_INTERACTIONS = {
    frozenset({"warfarin", "aspirin"}): {
        "severity": "high",
        "effect": "Increased bleeding risk",
        "action": "Monitor INR closely, consider dose adjustment",
    },
    frozenset({"warfarin", "metronidazole"}): {
        "severity": "critical",
        "effect": "Dramatically increased INR and bleeding risk",
        "action": "Avoid combination or reduce warfarin dose by 25-50%",
    },
    frozenset({"metformin", "contrast_dye"}): {
        "severity": "high",
        "effect": "Risk of lactic acidosis",
        "action": "Hold metformin 48h before and after contrast administration",
    },
    frozenset({"lithium", "ibuprofen"}): {
        "severity": "high",
        "effect": "Increased lithium levels — toxicity risk",
        "action": "Avoid NSAIDs; use paracetamol instead",
    },
    frozenset({"lithium", "diclofenac"}): {
        "severity": "high",
        "effect": "Increased lithium levels — toxicity risk",
        "action": "Avoid NSAIDs; use paracetamol instead",
    },
    frozenset({"methotrexate", "ibuprofen"}): {
        "severity": "critical",
        "effect": "Decreased methotrexate clearance — pancytopenia risk",
        "action": "Avoid concurrent NSAID use with methotrexate",
    },
    frozenset({"digoxin", "amiodarone"}): {
        "severity": "high",
        "effect": "Increased digoxin levels",
        "action": "Reduce digoxin dose by 50% when adding amiodarone",
    },
    frozenset({"ramipril", "spironolactone"}): {
        "severity": "moderate",
        "effect": "Hyperkalemia risk",
        "action": "Monitor potassium levels regularly",
    },
    frozenset({"ciprofloxacin", "methotrexate"}): {
        "severity": "high",
        "effect": "Increased methotrexate toxicity",
        "action": "Avoid combination; use alternative antibiotic",
    },
    frozenset({"amlodipine", "simvastatin"}): {
        "severity": "moderate",
        "effect": "Increased simvastatin levels — myopathy risk",
        "action": "Limit simvastatin to 20mg when combined with amlodipine",
    },
}


DOSE_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(mg|mcg|ug|g|ml|units?|iu)\b",
    re.IGNORECASE,
)


class DrugFormulary:
    def __init__(self):
        self._registry: dict[str, dict] = dict(THERAPEUTIC_RANGES)

    def lookup(self, drug_name: str) -> Optional[dict]:
        normalized = self._normalize_name(drug_name)
        return self._registry.get(normalized)

    def validate_dose(self, drug_name: str, dose_mg: float) -> dict:
        normalized = self._normalize_name(drug_name)
        drug_info = self._registry.get(normalized)

        if not drug_info:
            return {
                "drug": drug_name,
                "normalized": normalized,
                "dose_mg": dose_mg,
                "status": "unknown_drug",
                "message": f"Drug '{normalized}' not found in formulary",
            }

        min_dose = drug_info["min_mg"]
        max_dose = drug_info["max_mg"]
        frequency = drug_info["frequency"]

        if dose_mg > max_dose:
            severity = "critical" if dose_mg > max_dose * 2 else "warning"
            return {
                "drug": normalized,
                "dose_mg": dose_mg,
                "status": "exceeds_maximum",
                "severity": severity,
                "therapeutic_range": f"{min_dose}-{max_dose} {drug_info['unit']}",
                "frequency": frequency,
                "message": f"Dose {dose_mg}{drug_info['unit']} exceeds maximum {max_dose}{drug_info['unit']} ({frequency})",
            }

        if dose_mg < min_dose:
            return {
                "drug": normalized,
                "dose_mg": dose_mg,
                "status": "below_minimum",
                "severity": "info",
                "therapeutic_range": f"{min_dose}-{max_dose} {drug_info['unit']}",
                "frequency": frequency,
                "message": f"Dose {dose_mg}{drug_info['unit']} below minimum therapeutic dose {min_dose}{drug_info['unit']}",
            }

        return {
            "drug": normalized,
            "dose_mg": dose_mg,
            "status": "within_range",
            "severity": "ok",
            "therapeutic_range": f"{min_dose}-{max_dose} {drug_info['unit']}",
            "frequency": frequency,
        }

    def check_interactions(self, drug_names: list[str]) -> list[dict]:
        normalized = [self._normalize_name(d) for d in drug_names]
        interactions = []

        for i in range(len(normalized)):
            for j in range(i + 1, len(normalized)):
                pair = frozenset({normalized[i], normalized[j]})
                if pair in CRITICAL_INTERACTIONS:
                    interaction = CRITICAL_INTERACTIONS[pair]
                    interactions.append({
                        "drug_a": normalized[i],
                        "drug_b": normalized[j],
                        **interaction,
                    })

        interactions.sort(key=lambda x: {"critical": 0, "high": 1, "moderate": 2}.get(x["severity"], 3))

        return interactions

    def check_schedule(self, drug_name: str) -> dict:
        normalized = self._normalize_name(drug_name)
        drug_info = self._registry.get(normalized)

        if not drug_info:
            return {"drug": normalized, "schedule": "unknown", "requires_prescription": True}

        schedule = drug_info["schedule"]
        requires_prescription = schedule != DrugSchedule.OTC

        return {
            "drug": normalized,
            "schedule": schedule.value,
            "requires_prescription": requires_prescription,
            "controlled": schedule in (DrugSchedule.X, DrugSchedule.H1),
        }

    def parse_medication_text(self, text: str) -> dict:
        text_lower = text.lower().strip()

        dose_match = DOSE_PATTERN.search(text)
        dose_value = float(dose_match.group(1)) if dose_match else None
        dose_unit = dose_match.group(2) if dose_match else None

        drug_name = None
        for name in self._registry:
            if name in text_lower:
                drug_name = name
                break

        if drug_name is None:
            cleaned = re.sub(r"\d+\.?\d*\s*(mg|mcg|ug|g|ml|units?|iu)", "", text_lower)
            cleaned = re.sub(r"\b(tab|cap|inj|syp|od|bd|tid|qid|hs|prn|ac|pc|daily|twice|once)\b", "", cleaned)
            drug_name = cleaned.strip().split()[0] if cleaned.strip() else None

        result = {
            "raw_text": text,
            "drug_name": drug_name,
            "dose_value": dose_value,
            "dose_unit": dose_unit,
        }

        if drug_name and dose_value:
            result["dose_validation"] = self.validate_dose(drug_name, dose_value)

        if drug_name:
            result["schedule"] = self.check_schedule(drug_name)

        return result

    def analyze_prescription(self, medications: list[str]) -> dict:
        parsed_meds = []
        all_drug_names = []
        warnings = []

        for med_text in medications:
            parsed = self.parse_medication_text(med_text)
            parsed_meds.append(parsed)

            if parsed.get("drug_name"):
                all_drug_names.append(parsed["drug_name"])

            dose_val = parsed.get("dose_validation", {})
            if dose_val.get("status") == "exceeds_maximum":
                warnings.append({
                    "type": "dose_exceeds_maximum",
                    "severity": dose_val["severity"],
                    "drug": parsed["drug_name"],
                    "message": dose_val["message"],
                })

            schedule = parsed.get("schedule", {})
            if schedule.get("controlled"):
                warnings.append({
                    "type": "controlled_substance",
                    "severity": "info",
                    "drug": parsed["drug_name"],
                    "message": f"{parsed['drug_name']} is Schedule {schedule['schedule']} — requires prescription",
                })

        interactions = self.check_interactions(all_drug_names)
        for interaction in interactions:
            warnings.append({
                "type": "drug_interaction",
                "severity": interaction["severity"],
                "drug": f"{interaction['drug_a']} + {interaction['drug_b']}",
                "message": f"{interaction['effect']}. {interaction['action']}",
            })

        warnings.sort(key=lambda w: {"critical": 0, "high": 1, "warning": 2, "moderate": 3, "info": 4}.get(w["severity"], 5))

        return {
            "medications": parsed_meds,
            "total_medications": len(parsed_meds),
            "interactions": interactions,
            "warnings": warnings,
            "has_critical_warnings": any(w["severity"] == "critical" for w in warnings),
        }

    def _normalize_name(self, name: str) -> str:
        normalized = name.lower().strip()
        normalized = re.sub(r"\s+", "_", normalized)
        normalized = re.sub(r"[^a-z0-9_]", "", normalized)
        return normalized


drug_formulary = DrugFormulary()
