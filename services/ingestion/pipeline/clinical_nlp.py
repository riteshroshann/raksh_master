import re
from typing import Optional

import structlog

logger = structlog.get_logger()


NEGATION_TRIGGERS = [
    "no", "not", "without", "deny", "denies", "denied",
    "negative", "absent", "never", "none", "nor",
    "no evidence of", "not consistent with", "rules out",
    "ruled out", "no sign of", "no signs of", "unremarkable",
    "no history of", "no complaint of", "no complaints of",
    "not found", "not seen", "not detected", "not identified",
    "free from", "resolved", "cleared", "normal",
]

UNCERTAINTY_TRIGGERS = [
    "possible", "possibly", "probable", "probably",
    "suspected", "suspect", "suspicious", "equivocal",
    "questionable", "likely", "unlikely", "may have",
    "could be", "appears to be", "suggestive of",
    "consistent with", "cannot rule out", "differential includes",
    "pending", "preliminary", "provisional",
    "borderline", "indeterminate", "uncertain",
]

FAMILY_HISTORY_TRIGGERS = [
    "family history of", "family hx of", "fhx of",
    "mother had", "father had", "sibling had",
    "maternal", "paternal", "familial",
    "runs in family", "genetic predisposition",
]

HYPOTHETICAL_TRIGGERS = [
    "if", "should", "would", "could",
    "in case of", "unless", "might",
    "consider", "recommend", "advise",
    "plan to", "will", "to be done",
]

MEDICAL_ABBREVIATION_MAP = {
    "hb": "hemoglobin",
    "hgb": "hemoglobin",
    "plt": "platelets",
    "wbc": "white blood cells",
    "rbc": "red blood cells",
    "esr": "erythrocyte sedimentation rate",
    "crp": "c-reactive protein",
    "sgpt": "alanine transaminase",
    "alt": "alanine transaminase",
    "sgot": "aspartate transaminase",
    "ast": "aspartate transaminase",
    "alp": "alkaline phosphatase",
    "ggt": "gamma-glutamyl transferase",
    "ldh": "lactate dehydrogenase",
    "cpk": "creatine phosphokinase",
    "bnp": "brain natriuretic peptide",
    "tsh": "thyroid stimulating hormone",
    "ft3": "free triiodothyronine",
    "ft4": "free thyroxine",
    "t3": "triiodothyronine",
    "t4": "thyroxine",
    "hba1c": "glycated hemoglobin",
    "fpg": "fasting plasma glucose",
    "ppg": "postprandial glucose",
    "ogtt": "oral glucose tolerance test",
    "bun": "blood urea nitrogen",
    "egfr": "estimated glomerular filtration rate",
    "acr": "albumin creatinine ratio",
    "ua": "uric acid",
    "ldl": "low density lipoprotein",
    "hdl": "high density lipoprotein",
    "vldl": "very low density lipoprotein",
    "tc": "total cholesterol",
    "tg": "triglycerides",
    "inr": "international normalized ratio",
    "pt": "prothrombin time",
    "aptt": "activated partial thromboplastin time",
    "psa": "prostate specific antigen",
    "cea": "carcinoembryonic antigen",
    "afp": "alpha fetoprotein",
    "ca125": "cancer antigen 125",
    "ca199": "cancer antigen 19-9",
    "mcv": "mean corpuscular volume",
    "mch": "mean corpuscular hemoglobin",
    "mchc": "mean corpuscular hemoglobin concentration",
    "rdw": "red cell distribution width",
    "mpv": "mean platelet volume",
    "ana": "antinuclear antibody",
    "aso": "anti-streptolysin o",
    "ra": "rheumatoid factor",
    "ecg": "electrocardiogram",
    "eeg": "electroencephalogram",
    "emg": "electromyography",
    "usg": "ultrasonography",
    "ct": "computed tomography",
    "mri": "magnetic resonance imaging",
    "pet": "positron emission tomography",
    "cbc": "complete blood count",
    "lft": "liver function test",
    "kft": "kidney function test",
    "rft": "renal function test",
    "tfts": "thyroid function tests",
    "cmp": "comprehensive metabolic panel",
    "bmp": "basic metabolic panel",
    "abg": "arterial blood gas",
    "d/c": "discharge",
    "dx": "diagnosis",
    "hx": "history",
    "rx": "prescription",
    "tx": "treatment",
    "sx": "symptoms",
    "fx": "fracture",
    "bx": "biopsy",
    "od": "once daily",
    "bd": "twice daily",
    "tid": "three times daily",
    "qid": "four times daily",
    "hs": "at bedtime",
    "prn": "as needed",
    "ac": "before meals",
    "pc": "after meals",
    "po": "by mouth",
    "iv": "intravenous",
    "im": "intramuscular",
    "sc": "subcutaneous",
    "sl": "sublingual",
    "stat": "immediately",
    "tab": "tablet",
    "cap": "capsule",
    "inj": "injection",
    "syp": "syrup",
    "oint": "ointment",
    "susp": "suspension",
    "gtt": "drops",
    "neb": "nebulization",
    "inh": "inhaler",
}

DOSAGE_HAZARD_PATTERNS = [
    (r"\b(\d+)\s*[uU]\b", "insulin_unit_ambiguity"),
    (r"\b(\d+)\s*(?:units?|u)\s*(?:of\s+)?(?:insulin|humulin|novolin|lantus|humalog|actrapid|mixtard)", "insulin_high_risk"),
    (r"\b(\d+)\s*(?:mg|mcg)\s*(?:of\s+)?(?:warfarin|coumadin)", "warfarin_dose"),
    (r"\b(\d+)\s*(?:mg|mcg)\s*(?:of\s+)?(?:digoxin|lanoxin)", "digoxin_dose"),
    (r"\b(\d+)\s*(?:mg|mcg)\s*(?:of\s+)?(?:methotrexate|trexall)", "methotrexate_dose"),
    (r"\b(\d+)\s*(?:mg)\s*(?:of\s+)?(?:phenytoin|dilantin)", "phenytoin_dose"),
    (r"\b(\d+)\s*(?:mg)\s*(?:of\s+)?(?:lithium|eskalith)", "lithium_dose"),
    (r"\b(\d+)\s*(?:mg)\s*(?:of\s+)?(?:theophylline)", "theophylline_dose"),
    (r"\b(\d+)\s*(?:mcg)\s*(?:of\s+)?(?:levothyroxine|synthroid|thyronorm)", "levothyroxine_dose"),
    (r"\b0\.?\d*\s*(?:mg)\s*(?:of\s+)?(?:clonidine)", "clonidine_dose"),
]

LOINC_PARTIAL_MAP = {
    "hemoglobin": "718-7",
    "hematocrit": "4544-3",
    "platelets": "777-3",
    "wbc": "6690-2",
    "rbc": "789-8",
    "glucose": "2345-7",
    "fasting_glucose": "1558-6",
    "hba1c": "4548-4",
    "creatinine": "2160-0",
    "blood_urea": "3094-0",
    "uric_acid": "3084-1",
    "total_cholesterol": "2093-3",
    "ldl_cholesterol": "2089-1",
    "hdl_cholesterol": "2085-9",
    "triglycerides": "2571-8",
    "sgpt_alt": "1742-6",
    "sgot_ast": "1920-8",
    "alkaline_phosphatase": "6768-6",
    "total_bilirubin": "1975-2",
    "albumin": "1751-7",
    "total_protein": "2885-2",
    "tsh": "3016-3",
    "free_t3": "3051-0",
    "free_t4": "3024-7",
    "sodium": "2951-2",
    "potassium": "2823-3",
    "calcium": "17861-6",
    "vitamin_d": "1989-3",
    "vitamin_b12": "2132-9",
    "ferritin": "2276-4",
    "iron": "2498-4",
    "crp": "1988-5",
    "esr": "4537-7",
    "psa": "2857-1",
    "inr": "6301-6",
}

SNOMED_PARTIAL_MAP = {
    "diabetes": "73211009",
    "hypertension": "38341003",
    "asthma": "195967001",
    "pneumonia": "233604007",
    "tuberculosis": "56717001",
    "anemia": "271737000",
    "thyroid": "14304000",
    "malaria": "248437004",
    "dengue": "38362002",
    "covid": "840539006",
    "fracture": "125605004",
    "myocardial_infarction": "22298006",
    "stroke": "230690007",
    "kidney_disease": "90708001",
    "liver_disease": "235856003",
    "cancer": "363346000",
}


class ConTextEngine:
    def __init__(self):
        self._negation_window = 6
        self._uncertainty_window = 5

    def detect_negation(self, text: str, target_span: tuple[int, int]) -> bool:
        text_lower = text.lower()
        target_start, target_end = target_span

        for trigger in NEGATION_TRIGGERS:
            pattern = re.compile(r"\b" + re.escape(trigger) + r"\b", re.IGNORECASE)
            for match in pattern.finditer(text_lower):
                trigger_end = match.end()
                trigger_start = match.start()

                if trigger_end <= target_start:
                    words_between = text[trigger_end:target_start].split()
                    if len(words_between) <= self._negation_window:
                        if not self._has_scope_break(text[trigger_end:target_start]):
                            return True

                if target_end <= trigger_start:
                    words_between = text[target_end:trigger_start].split()
                    if len(words_between) <= 3:
                        return True

        return False

    def detect_uncertainty(self, text: str, target_span: tuple[int, int]) -> bool:
        text_lower = text.lower()
        target_start, _ = target_span

        for trigger in UNCERTAINTY_TRIGGERS:
            pattern = re.compile(r"\b" + re.escape(trigger) + r"\b", re.IGNORECASE)
            for match in pattern.finditer(text_lower):
                trigger_end = match.end()

                if trigger_end <= target_start:
                    words_between = text[trigger_end:target_start].split()
                    if len(words_between) <= self._uncertainty_window:
                        if not self._has_scope_break(text[trigger_end:target_start]):
                            return True

        return False

    def detect_family_history(self, text: str, target_span: tuple[int, int]) -> bool:
        text_lower = text.lower()
        target_start, _ = target_span

        for trigger in FAMILY_HISTORY_TRIGGERS:
            idx = text_lower.find(trigger)
            if idx != -1 and idx < target_start:
                words_between = text[idx + len(trigger):target_start].split()
                if len(words_between) <= 8:
                    return True

        return False

    def detect_hypothetical(self, text: str, target_span: tuple[int, int]) -> bool:
        text_lower = text.lower()
        target_start, _ = target_span

        for trigger in HYPOTHETICAL_TRIGGERS:
            pattern = re.compile(r"\b" + re.escape(trigger) + r"\b", re.IGNORECASE)
            for match in pattern.finditer(text_lower):
                trigger_end = match.end()
                if trigger_end <= target_start:
                    words_between = text[trigger_end:target_start].split()
                    if len(words_between) <= 4:
                        return True

        return False

    def classify_assertion(self, text: str, target_span: tuple[int, int]) -> str:
        if self.detect_negation(text, target_span):
            return "negated"
        if self.detect_family_history(text, target_span):
            return "family_history"
        if self.detect_hypothetical(text, target_span):
            return "hypothetical"
        if self.detect_uncertainty(text, target_span):
            return "uncertain"
        return "affirmed"

    def _has_scope_break(self, text: str) -> bool:
        scope_breakers = [
            "but", "however", "although", "except", "yet",
            ".", ";", ":", "\n",
        ]
        text_lower = text.lower()
        for breaker in scope_breakers:
            if breaker in text_lower:
                return True
        return False


class DosageHazardDetector:
    def scan(self, text: str) -> list[dict]:
        hazards = []

        for pattern, hazard_type in DOSAGE_HAZARD_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                value = match.group(1)
                try:
                    numeric_value = float(value)
                except ValueError:
                    continue

                severity = self._assess_severity(hazard_type, numeric_value)

                hazards.append({
                    "type": hazard_type,
                    "matched_text": match.group(0),
                    "value": numeric_value,
                    "position": match.start(),
                    "severity": severity,
                })

        return hazards

    def _assess_severity(self, hazard_type: str, value: float) -> str:
        if hazard_type == "insulin_unit_ambiguity":
            return "critical"

        if hazard_type == "insulin_high_risk":
            if value > 100:
                return "critical"
            elif value > 50:
                return "high"
            return "medium"

        if hazard_type == "warfarin_dose":
            if value > 10:
                return "critical"
            return "medium"

        if hazard_type == "digoxin_dose":
            if value > 0.5:
                return "high"
            return "medium"

        if hazard_type == "methotrexate_dose":
            if value > 25:
                return "critical"
            return "medium"

        return "medium"


class EntityLinker:
    def link_to_loinc(self, parameter_name: str) -> Optional[str]:
        normalized = parameter_name.lower().strip().replace(" ", "_")
        return LOINC_PARTIAL_MAP.get(normalized)

    def link_to_snomed(self, condition: str) -> Optional[str]:
        normalized = condition.lower().strip().replace(" ", "_")
        return SNOMED_PARTIAL_MAP.get(normalized)

    def expand_abbreviation(self, abbreviation: str) -> Optional[str]:
        normalized = abbreviation.lower().strip().replace(".", "")
        return MEDICAL_ABBREVIATION_MAP.get(normalized)

    def normalize_parameter_name(self, raw_name: str) -> str:
        normalized = raw_name.lower().strip()
        normalized = re.sub(r"[^\w\s]", "", normalized)
        normalized = re.sub(r"\s+", "_", normalized)

        expansion = MEDICAL_ABBREVIATION_MAP.get(normalized)
        if expansion:
            normalized = expansion.lower().replace(" ", "_")

        return normalized

    def enrich_extraction(self, extraction: dict) -> dict:
        name = extraction.get("name", "")

        normalized_name = self.normalize_parameter_name(name)
        extraction["normalized_name"] = normalized_name

        loinc_code = self.link_to_loinc(normalized_name)
        if loinc_code:
            extraction["loinc_code"] = loinc_code

        abbreviation = self.expand_abbreviation(name)
        if abbreviation and abbreviation != name:
            extraction["expanded_name"] = abbreviation

        return extraction

    def batch_enrich(self, extractions: list[dict]) -> list[dict]:
        return [self.enrich_extraction(e) for e in extractions]


class ClinicalTextAnalyzer:
    def __init__(self):
        self._context = ConTextEngine()
        self._hazard_detector = DosageHazardDetector()
        self._linker = EntityLinker()

    def analyze(self, clinical_text: str) -> dict:
        entities = self._extract_entities(clinical_text)

        annotated_entities = []
        for entity in entities:
            span = entity["span"]
            assertion = self._context.classify_assertion(clinical_text, span)

            entity["assertion"] = assertion

            loinc = self._linker.link_to_loinc(entity["text"])
            if loinc:
                entity["loinc_code"] = loinc

            snomed = self._linker.link_to_snomed(entity["text"])
            if snomed:
                entity["snomed_code"] = snomed

            annotated_entities.append(entity)

        hazards = self._hazard_detector.scan(clinical_text)

        return {
            "entities": annotated_entities,
            "hazards": hazards,
            "negated_count": sum(1 for e in annotated_entities if e["assertion"] == "negated"),
            "affirmed_count": sum(1 for e in annotated_entities if e["assertion"] == "affirmed"),
            "uncertain_count": sum(1 for e in annotated_entities if e["assertion"] == "uncertain"),
        }

    def _extract_entities(self, text: str) -> list[dict]:
        entities = []

        all_terms = list(LOINC_PARTIAL_MAP.keys()) + list(SNOMED_PARTIAL_MAP.keys())

        for term in all_terms:
            search_term = term.replace("_", " ")
            pattern = re.compile(r"\b" + re.escape(search_term) + r"\b", re.IGNORECASE)

            for match in pattern.finditer(text):
                entities.append({
                    "text": term,
                    "span": (match.start(), match.end()),
                    "matched_text": match.group(),
                })

        return entities


context_engine = ConTextEngine()
dosage_detector = DosageHazardDetector()
entity_linker = EntityLinker()
clinical_analyzer = ClinicalTextAnalyzer()
