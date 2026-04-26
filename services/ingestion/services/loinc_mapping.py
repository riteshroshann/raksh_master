from typing import Optional

import structlog
from supabase import create_client, Client

from config import settings

logger = structlog.get_logger()


def _get_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


CORE_LOINC_MAP = {
    "hemoglobin": {"loinc_code": "718-7", "loinc_name": "Hemoglobin [Mass/volume] in Blood", "component": "Hemoglobin", "system": "Blood", "unit": "g/dL"},
    "hb": {"loinc_code": "718-7", "loinc_name": "Hemoglobin [Mass/volume] in Blood", "component": "Hemoglobin", "system": "Blood", "unit": "g/dL"},
    "hematocrit": {"loinc_code": "4544-3", "loinc_name": "Hematocrit [Volume Fraction] of Blood", "component": "Hematocrit", "system": "Blood", "unit": "%"},
    "wbc": {"loinc_code": "6690-2", "loinc_name": "Leukocytes [#/volume] in Blood", "component": "Leukocytes", "system": "Blood", "unit": "10^3/uL"},
    "rbc": {"loinc_code": "789-8", "loinc_name": "Erythrocytes [#/volume] in Blood", "component": "Erythrocytes", "system": "Blood", "unit": "10^6/uL"},
    "platelet_count": {"loinc_code": "777-3", "loinc_name": "Platelets [#/volume] in Blood", "component": "Platelets", "system": "Blood", "unit": "10^3/uL"},
    "platelets": {"loinc_code": "777-3", "loinc_name": "Platelets [#/volume] in Blood", "component": "Platelets", "system": "Blood", "unit": "10^3/uL"},
    "mcv": {"loinc_code": "787-2", "loinc_name": "Erythrocyte mean corpuscular volume [Entitic volume]", "component": "MCV", "system": "RBC", "unit": "fL"},
    "mch": {"loinc_code": "785-6", "loinc_name": "Erythrocyte mean corpuscular hemoglobin [Entitic mass]", "component": "MCH", "system": "RBC", "unit": "pg"},
    "mchc": {"loinc_code": "786-4", "loinc_name": "Erythrocyte mean corpuscular hemoglobin concentration [Mass/volume]", "component": "MCHC", "system": "RBC", "unit": "g/dL"},
    "rdw": {"loinc_code": "788-0", "loinc_name": "Erythrocyte distribution width [Ratio]", "component": "RDW", "system": "RBC", "unit": "%"},
    "esr": {"loinc_code": "4537-7", "loinc_name": "Erythrocyte sedimentation rate", "component": "ESR", "system": "Blood", "unit": "mm/hr"},

    "fasting_plasma_glucose": {"loinc_code": "1558-6", "loinc_name": "Fasting glucose [Mass/volume] in Serum or Plasma", "component": "Glucose", "system": "Serum/Plasma", "unit": "mg/dL"},
    "fasting_blood_sugar": {"loinc_code": "1558-6", "loinc_name": "Fasting glucose [Mass/volume] in Serum or Plasma", "component": "Glucose", "system": "Serum/Plasma", "unit": "mg/dL"},
    "fbs": {"loinc_code": "1558-6", "loinc_name": "Fasting glucose [Mass/volume] in Serum or Plasma", "component": "Glucose", "system": "Serum/Plasma", "unit": "mg/dL"},
    "postprandial_glucose": {"loinc_code": "1521-4", "loinc_name": "Glucose [Mass/volume] in Serum or Plasma --2 hours post meal", "component": "Glucose post meal", "system": "Serum/Plasma", "unit": "mg/dL"},
    "ppg": {"loinc_code": "1521-4", "loinc_name": "Glucose [Mass/volume] in Serum or Plasma --2 hours post meal", "component": "Glucose post meal", "system": "Serum/Plasma", "unit": "mg/dL"},
    "glycated_hemoglobin": {"loinc_code": "4548-4", "loinc_name": "Hemoglobin A1c/Hemoglobin.total in Blood", "component": "HbA1c", "system": "Blood", "unit": "%"},
    "hba1c": {"loinc_code": "4548-4", "loinc_name": "Hemoglobin A1c/Hemoglobin.total in Blood", "component": "HbA1c", "system": "Blood", "unit": "%"},
    "random_blood_sugar": {"loinc_code": "2339-0", "loinc_name": "Glucose [Mass/volume] in Blood", "component": "Glucose", "system": "Blood", "unit": "mg/dL"},
    "rbs": {"loinc_code": "2339-0", "loinc_name": "Glucose [Mass/volume] in Blood", "component": "Glucose", "system": "Blood", "unit": "mg/dL"},

    "creatinine": {"loinc_code": "2160-0", "loinc_name": "Creatinine [Mass/volume] in Serum or Plasma", "component": "Creatinine", "system": "Serum/Plasma", "unit": "mg/dL"},
    "blood_urea_nitrogen": {"loinc_code": "3094-0", "loinc_name": "Urea nitrogen [Mass/volume] in Serum or Plasma", "component": "Urea nitrogen", "system": "Serum/Plasma", "unit": "mg/dL"},
    "bun": {"loinc_code": "3094-0", "loinc_name": "Urea nitrogen [Mass/volume] in Serum or Plasma", "component": "Urea nitrogen", "system": "Serum/Plasma", "unit": "mg/dL"},
    "urea": {"loinc_code": "3091-6", "loinc_name": "Urea [Mass/volume] in Serum or Plasma", "component": "Urea", "system": "Serum/Plasma", "unit": "mg/dL"},
    "uric_acid": {"loinc_code": "3084-1", "loinc_name": "Urate [Mass/volume] in Serum or Plasma", "component": "Urate", "system": "Serum/Plasma", "unit": "mg/dL"},
    "estimated_glomerular_filtration_rate": {"loinc_code": "33914-3", "loinc_name": "eGFR [Volume Rate/Area] in Serum or Plasma", "component": "eGFR", "system": "Serum/Plasma", "unit": "mL/min/1.73m2"},
    "egfr": {"loinc_code": "33914-3", "loinc_name": "eGFR [Volume Rate/Area] in Serum or Plasma", "component": "eGFR", "system": "Serum/Plasma", "unit": "mL/min/1.73m2"},
    "albumin_creatinine_ratio": {"loinc_code": "9318-7", "loinc_name": "Albumin/Creatinine [Mass Ratio] in Urine", "component": "Albumin/Creatinine", "system": "Urine", "unit": "mg/g"},

    "total_cholesterol": {"loinc_code": "2093-3", "loinc_name": "Cholesterol [Mass/volume] in Serum or Plasma", "component": "Cholesterol", "system": "Serum/Plasma", "unit": "mg/dL"},
    "hdl_cholesterol": {"loinc_code": "2085-9", "loinc_name": "Cholesterol in HDL [Mass/volume] in Serum or Plasma", "component": "HDL Cholesterol", "system": "Serum/Plasma", "unit": "mg/dL"},
    "ldl_cholesterol": {"loinc_code": "2089-1", "loinc_name": "Cholesterol in LDL [Mass/volume] in Serum or Plasma", "component": "LDL Cholesterol", "system": "Serum/Plasma", "unit": "mg/dL"},
    "triglycerides": {"loinc_code": "2571-8", "loinc_name": "Triglyceride [Mass/volume] in Serum or Plasma", "component": "Triglyceride", "system": "Serum/Plasma", "unit": "mg/dL"},
    "vldl_cholesterol": {"loinc_code": "13458-5", "loinc_name": "Cholesterol in VLDL [Mass/volume] in Serum or Plasma", "component": "VLDL Cholesterol", "system": "Serum/Plasma", "unit": "mg/dL"},

    "alanine_transaminase": {"loinc_code": "1742-6", "loinc_name": "ALT [Enzymatic activity/volume] in Serum or Plasma", "component": "ALT", "system": "Serum/Plasma", "unit": "U/L"},
    "alt": {"loinc_code": "1742-6", "loinc_name": "ALT [Enzymatic activity/volume] in Serum or Plasma", "component": "ALT", "system": "Serum/Plasma", "unit": "U/L"},
    "sgpt": {"loinc_code": "1742-6", "loinc_name": "ALT [Enzymatic activity/volume] in Serum or Plasma", "component": "ALT", "system": "Serum/Plasma", "unit": "U/L"},
    "aspartate_transaminase": {"loinc_code": "1920-8", "loinc_name": "AST [Enzymatic activity/volume] in Serum or Plasma", "component": "AST", "system": "Serum/Plasma", "unit": "U/L"},
    "ast": {"loinc_code": "1920-8", "loinc_name": "AST [Enzymatic activity/volume] in Serum or Plasma", "component": "AST", "system": "Serum/Plasma", "unit": "U/L"},
    "sgot": {"loinc_code": "1920-8", "loinc_name": "AST [Enzymatic activity/volume] in Serum or Plasma", "component": "AST", "system": "Serum/Plasma", "unit": "U/L"},
    "alkaline_phosphatase": {"loinc_code": "6768-6", "loinc_name": "ALP [Enzymatic activity/volume] in Serum or Plasma", "component": "ALP", "system": "Serum/Plasma", "unit": "U/L"},
    "alp": {"loinc_code": "6768-6", "loinc_name": "ALP [Enzymatic activity/volume] in Serum or Plasma", "component": "ALP", "system": "Serum/Plasma", "unit": "U/L"},
    "total_bilirubin": {"loinc_code": "1975-2", "loinc_name": "Bilirubin.total [Mass/volume] in Serum or Plasma", "component": "Bilirubin.total", "system": "Serum/Plasma", "unit": "mg/dL"},
    "direct_bilirubin": {"loinc_code": "1968-7", "loinc_name": "Bilirubin.direct [Mass/volume] in Serum or Plasma", "component": "Bilirubin.direct", "system": "Serum/Plasma", "unit": "mg/dL"},
    "gamma_glutamyl_transferase": {"loinc_code": "2324-2", "loinc_name": "GGT [Enzymatic activity/volume] in Serum or Plasma", "component": "GGT", "system": "Serum/Plasma", "unit": "U/L"},
    "ggt": {"loinc_code": "2324-2", "loinc_name": "GGT [Enzymatic activity/volume] in Serum or Plasma", "component": "GGT", "system": "Serum/Plasma", "unit": "U/L"},
    "albumin": {"loinc_code": "1751-7", "loinc_name": "Albumin [Mass/volume] in Serum or Plasma", "component": "Albumin", "system": "Serum/Plasma", "unit": "g/dL"},
    "total_protein": {"loinc_code": "2885-2", "loinc_name": "Protein [Mass/volume] in Serum or Plasma", "component": "Protein", "system": "Serum/Plasma", "unit": "g/dL"},

    "thyroid_stimulating_hormone": {"loinc_code": "3016-3", "loinc_name": "TSH [Units/volume] in Serum or Plasma", "component": "TSH", "system": "Serum/Plasma", "unit": "mIU/L"},
    "tsh": {"loinc_code": "3016-3", "loinc_name": "TSH [Units/volume] in Serum or Plasma", "component": "TSH", "system": "Serum/Plasma", "unit": "mIU/L"},
    "free_thyroxine": {"loinc_code": "3024-7", "loinc_name": "Free T4 [Mass/volume] in Serum or Plasma", "component": "Free T4", "system": "Serum/Plasma", "unit": "ng/dL"},
    "ft4": {"loinc_code": "3024-7", "loinc_name": "Free T4 [Mass/volume] in Serum or Plasma", "component": "Free T4", "system": "Serum/Plasma", "unit": "ng/dL"},
    "free_triiodothyronine": {"loinc_code": "3051-0", "loinc_name": "Free T3 [Mass/volume] in Serum or Plasma", "component": "Free T3", "system": "Serum/Plasma", "unit": "pg/mL"},
    "ft3": {"loinc_code": "3051-0", "loinc_name": "Free T3 [Mass/volume] in Serum or Plasma", "component": "Free T3", "system": "Serum/Plasma", "unit": "pg/mL"},

    "sodium": {"loinc_code": "2951-2", "loinc_name": "Sodium [Moles/volume] in Serum or Plasma", "component": "Sodium", "system": "Serum/Plasma", "unit": "mEq/L"},
    "potassium": {"loinc_code": "2823-3", "loinc_name": "Potassium [Moles/volume] in Serum or Plasma", "component": "Potassium", "system": "Serum/Plasma", "unit": "mEq/L"},
    "chloride": {"loinc_code": "2075-0", "loinc_name": "Chloride [Moles/volume] in Serum or Plasma", "component": "Chloride", "system": "Serum/Plasma", "unit": "mEq/L"},
    "calcium": {"loinc_code": "17861-6", "loinc_name": "Calcium [Mass/volume] in Serum or Plasma", "component": "Calcium", "system": "Serum/Plasma", "unit": "mg/dL"},
    "phosphorus": {"loinc_code": "2777-1", "loinc_name": "Phosphate [Mass/volume] in Serum or Plasma", "component": "Phosphate", "system": "Serum/Plasma", "unit": "mg/dL"},
    "magnesium": {"loinc_code": "19123-9", "loinc_name": "Magnesium [Mass/volume] in Serum or Plasma", "component": "Magnesium", "system": "Serum/Plasma", "unit": "mg/dL"},
    "iron": {"loinc_code": "2498-4", "loinc_name": "Iron [Mass/volume] in Serum or Plasma", "component": "Iron", "system": "Serum/Plasma", "unit": "mcg/dL"},
    "ferritin": {"loinc_code": "2276-4", "loinc_name": "Ferritin [Mass/volume] in Serum or Plasma", "component": "Ferritin", "system": "Serum/Plasma", "unit": "ng/mL"},
    "total_iron_binding_capacity": {"loinc_code": "2500-7", "loinc_name": "TIBC [Mass/volume] in Serum or Plasma", "component": "TIBC", "system": "Serum/Plasma", "unit": "mcg/dL"},
    "tibc": {"loinc_code": "2500-7", "loinc_name": "TIBC [Mass/volume] in Serum or Plasma", "component": "TIBC", "system": "Serum/Plasma", "unit": "mcg/dL"},
    "vitamin_b12": {"loinc_code": "2132-9", "loinc_name": "Cobalamin [Mass/volume] in Serum or Plasma", "component": "Cobalamin", "system": "Serum/Plasma", "unit": "pg/mL"},
    "folate": {"loinc_code": "2284-8", "loinc_name": "Folate [Mass/volume] in Serum or Plasma", "component": "Folate", "system": "Serum/Plasma", "unit": "ng/mL"},
    "vitamin_d": {"loinc_code": "1989-3", "loinc_name": "25-hydroxyvitamin D3 [Mass/volume] in Serum or Plasma", "component": "25(OH)D", "system": "Serum/Plasma", "unit": "ng/mL"},

    "troponin_i": {"loinc_code": "10839-9", "loinc_name": "Troponin I.cardiac [Mass/volume] in Serum or Plasma", "component": "Troponin I", "system": "Serum/Plasma", "unit": "ng/mL"},
    "troponin_t": {"loinc_code": "6598-7", "loinc_name": "Troponin T.cardiac [Mass/volume] in Serum or Plasma", "component": "Troponin T", "system": "Serum/Plasma", "unit": "ng/mL"},
    "brain_natriuretic_peptide": {"loinc_code": "30934-4", "loinc_name": "BNP [Mass/volume] in Serum or Plasma", "component": "BNP", "system": "Serum/Plasma", "unit": "pg/mL"},
    "bnp": {"loinc_code": "30934-4", "loinc_name": "BNP [Mass/volume] in Serum or Plasma", "component": "BNP", "system": "Serum/Plasma", "unit": "pg/mL"},
    "creatine_phosphokinase": {"loinc_code": "2157-6", "loinc_name": "CK [Enzymatic activity/volume] in Serum or Plasma", "component": "CK", "system": "Serum/Plasma", "unit": "U/L"},
    "cpk": {"loinc_code": "2157-6", "loinc_name": "CK [Enzymatic activity/volume] in Serum or Plasma", "component": "CK", "system": "Serum/Plasma", "unit": "U/L"},
    "ldh": {"loinc_code": "2532-0", "loinc_name": "LDH [Enzymatic activity/volume] in Serum or Plasma", "component": "LDH", "system": "Serum/Plasma", "unit": "U/L"},

    "international_normalized_ratio": {"loinc_code": "6301-6", "loinc_name": "INR in Platelet poor plasma by Coagulation assay", "component": "INR", "system": "PPP", "unit": ""},
    "inr": {"loinc_code": "6301-6", "loinc_name": "INR in Platelet poor plasma by Coagulation assay", "component": "INR", "system": "PPP", "unit": ""},
    "prothrombin_time": {"loinc_code": "5902-2", "loinc_name": "Prothrombin time (PT)", "component": "PT", "system": "PPP", "unit": "seconds"},
    "activated_partial_thromboplastin_time": {"loinc_code": "3173-2", "loinc_name": "aPTT in Platelet poor plasma by Coagulation assay", "component": "aPTT", "system": "PPP", "unit": "seconds"},
    "aptt": {"loinc_code": "3173-2", "loinc_name": "aPTT in Platelet poor plasma by Coagulation assay", "component": "aPTT", "system": "PPP", "unit": "seconds"},

    "c_reactive_protein": {"loinc_code": "1988-5", "loinc_name": "C reactive protein [Mass/volume] in Serum or Plasma", "component": "CRP", "system": "Serum/Plasma", "unit": "mg/L"},
    "crp": {"loinc_code": "1988-5", "loinc_name": "C reactive protein [Mass/volume] in Serum or Plasma", "component": "CRP", "system": "Serum/Plasma", "unit": "mg/L"},
    "procalcitonin": {"loinc_code": "33959-8", "loinc_name": "Procalcitonin [Mass/volume] in Serum or Plasma", "component": "Procalcitonin", "system": "Serum/Plasma", "unit": "ng/mL"},

    "psa": {"loinc_code": "2857-1", "loinc_name": "PSA [Mass/volume] in Serum or Plasma", "component": "PSA", "system": "Serum/Plasma", "unit": "ng/mL"},
    "prostate_specific_antigen": {"loinc_code": "2857-1", "loinc_name": "PSA [Mass/volume] in Serum or Plasma", "component": "PSA", "system": "Serum/Plasma", "unit": "ng/mL"},
    "ca_125": {"loinc_code": "10334-1", "loinc_name": "Cancer Ag 125 [Units/volume] in Serum or Plasma", "component": "CA 125", "system": "Serum/Plasma", "unit": "U/mL"},
}


class LOINCService:
    def __init__(self):
        self._local_map: dict[str, dict] = dict(CORE_LOINC_MAP)
        self._db_cache: dict[str, Optional[dict]] = {}
        try:
            self._client: Client = _get_client()
        except Exception:
            self._client = None

    def lookup(self, parameter_name: str) -> Optional[dict]:
        normalized = self._normalize(parameter_name)

        if normalized in self._local_map:
            return self._local_map[normalized]

        if normalized in self._db_cache:
            return self._db_cache[normalized]

        db_result = self._lookup_db(normalized)
        self._db_cache[normalized] = db_result
        return db_result

    def get_loinc_code(self, parameter_name: str) -> Optional[str]:
        result = self.lookup(parameter_name)
        return result["loinc_code"] if result else None

    def get_fhir_coding(self, parameter_name: str) -> Optional[dict]:
        result = self.lookup(parameter_name)
        if not result:
            return None

        return {
            "system": "http://loinc.org",
            "code": result["loinc_code"],
            "display": result["loinc_name"],
        }

    def enrich_extraction(self, extraction: dict) -> dict:
        name = extraction.get("name", extraction.get("parameter_name", ""))
        loinc = self.lookup(name)

        if loinc:
            extraction["loinc_code"] = loinc["loinc_code"]
            extraction["loinc_name"] = loinc["loinc_name"]
            extraction["loinc_component"] = loinc.get("component")
            extraction["loinc_system"] = loinc.get("system")

            if not extraction.get("unit") and loinc.get("unit"):
                extraction["unit"] = loinc["unit"]
                logger.info(
                    "loinc_unit_backfilled",
                    parameter=name,
                    unit=loinc["unit"],
                    loinc_code=loinc["loinc_code"],
                )

        return extraction

    def enrich_batch(self, extractions: list[dict]) -> list[dict]:
        enriched_count = 0
        for extraction in extractions:
            before = extraction.get("loinc_code")
            self.enrich_extraction(extraction)
            if extraction.get("loinc_code") and not before:
                enriched_count += 1

        if enriched_count > 0:
            logger.info("loinc_batch_enrichment", enriched=enriched_count, total=len(extractions))

        return extractions

    def coverage_report(self, parameter_names: list[str]) -> dict:
        mapped = []
        unmapped = []

        for name in parameter_names:
            if self.lookup(name):
                mapped.append(name)
            else:
                unmapped.append(name)

        return {
            "total": len(parameter_names),
            "mapped": len(mapped),
            "unmapped": len(unmapped),
            "coverage_percent": round(len(mapped) / max(len(parameter_names), 1) * 100, 1),
            "mapped_parameters": mapped,
            "unmapped_parameters": unmapped,
        }

    def _lookup_db(self, normalized: str) -> Optional[dict]:
        if not self._client:
            return None

        try:
            result = (
                self._client.table("loinc_codes")
                .select("*")
                .eq("parameter_alias", normalized)
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as exc:
            logger.warning("loinc_db_lookup_failed", parameter=normalized, error=str(exc))

        return None

    def _normalize(self, name: str) -> str:
        import re
        return re.sub(r"[^a-z0-9_]", "", name.lower().strip().replace(" ", "_"))


loinc_service = LOINCService()
