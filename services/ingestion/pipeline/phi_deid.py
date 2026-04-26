import re
from typing import Optional

import structlog

logger = structlog.get_logger()


AADHAAR_PATTERN = re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b")
PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
INDIAN_PHONE_PATTERN = re.compile(r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
ABHA_PATTERN = re.compile(r"\b\d{2}-\d{4}-\d{4}-\d{4}\b")
PASSPORT_PATTERN = re.compile(r"\b[A-Z]\d{7}\b")
DOB_PATTERN = re.compile(
    r"\b(?:(?:0[1-9]|[12]\d|3[01])[/\-.](?:0[1-9]|1[0-2])[/\-.](?:19|20)\d{2})|"
    r"(?:(?:19|20)\d{2}[/\-.](?:0[1-9]|1[0-2])[/\-.](?:0[1-9]|[12]\d|3[01]))\b"
)
PINCODE_PATTERN = re.compile(r"\b[1-9]\d{5}\b")

ADDRESS_KEYWORDS = [
    "address", "addr", "residence", "residing at", "residing:",
    "house no", "flat no", "apartment", "floor",
    "street", "road", "lane", "nagar", "colony",
    "village", "district", "tehsil", "taluk",
    "mandal", "block", "ward",
]

NAME_PREFIXES = [
    "patient name", "patient:", "name:", "mr.", "mrs.", "ms.",
    "dr.", "shri", "smt.", "kumari", "master",
    "s/o", "d/o", "w/o", "c/o",
]


class PHIEntity:
    __slots__ = ("entity_type", "text", "start", "end", "score")

    def __init__(self, entity_type: str, text: str, start: int, end: int, score: float = 1.0):
        self.entity_type = entity_type
        self.text = text
        self.start = start
        self.end = end
        self.score = score


class DeIdentificationPipeline:
    def __init__(self):
        self._redaction_char = "█"
        self._min_name_length = 3
        self._presidio_available = False

        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._presidio_available = True
            logger.info("phi_deid_presidio_loaded")
        except ImportError:
            logger.warning("phi_deid_presidio_unavailable_using_regex_fallback")

    def scan(self, text: str) -> list[PHIEntity]:
        if self._presidio_available:
            return self._scan_with_presidio(text)
        return self._scan_with_regex(text)

    def deidentify(self, text: str) -> tuple[str, list[PHIEntity]]:
        entities = self.scan(text)

        if not entities:
            return text, []

        entities.sort(key=lambda e: e.start, reverse=True)

        redacted = text
        for entity in entities:
            replacement = self._generate_replacement(entity)
            redacted = redacted[:entity.start] + replacement + redacted[entity.end:]

        logger.info(
            "phi_deidentification_complete",
            entities_found=len(entities),
            types_found=list({e.entity_type for e in entities}),
        )

        return redacted, entities

    def deidentify_structured(self, data: dict) -> tuple[dict, list[PHIEntity]]:
        all_entities = []
        redacted_data = {}

        for key, value in data.items():
            if isinstance(value, str):
                if self._is_sensitive_field(key):
                    redacted_data[key] = self._redact_value(value)
                    all_entities.append(PHIEntity(
                        entity_type=self._classify_field(key),
                        text=value,
                        start=0,
                        end=len(value),
                    ))
                else:
                    redacted_text, entities = self.deidentify(value)
                    redacted_data[key] = redacted_text
                    all_entities.extend(entities)
            elif isinstance(value, dict):
                sub_redacted, sub_entities = self.deidentify_structured(value)
                redacted_data[key] = sub_redacted
                all_entities.extend(sub_entities)
            elif isinstance(value, list):
                redacted_list = []
                for item in value:
                    if isinstance(item, dict):
                        sub_r, sub_e = self.deidentify_structured(item)
                        redacted_list.append(sub_r)
                        all_entities.extend(sub_e)
                    elif isinstance(item, str):
                        r_text, r_ents = self.deidentify(item)
                        redacted_list.append(r_text)
                        all_entities.extend(r_ents)
                    else:
                        redacted_list.append(item)
                redacted_data[key] = redacted_list
            else:
                redacted_data[key] = value

        return redacted_data, all_entities

    def validate_clean(self, text: str) -> dict:
        entities = self.scan(text)

        return {
            "is_clean": len(entities) == 0,
            "residual_phi_count": len(entities),
            "residual_types": [e.entity_type for e in entities],
            "residual_entities": [{"type": e.entity_type, "position": e.start} for e in entities],
        }

    def _scan_with_presidio(self, text: str) -> list[PHIEntity]:
        from presidio_analyzer import AnalyzerEngine

        TYPE_MAP = {
            "PHONE_NUMBER": "PHONE",
            "EMAIL_ADDRESS": "EMAIL",
        }

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=[
                "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
                "LOCATION", "DATE_TIME", "NRP",
                "MEDICAL_LICENSE", "URL",
            ],
        )

        entities = [
            PHIEntity(
                entity_type=TYPE_MAP.get(r.entity_type, r.entity_type),
                text=text[r.start:r.end],
                start=r.start,
                end=r.end,
                score=r.score,
            )
            for r in results
            if r.score >= 0.6
        ]

        entities.extend(self._scan_indian_identifiers(text))
        entities.extend(self._scan_contact_info(text))

        return self._deduplicate_entities(entities)

    def _scan_with_regex(self, text: str) -> list[PHIEntity]:
        entities = []
        entities.extend(self._scan_indian_identifiers(text))
        entities.extend(self._scan_contact_info(text))
        entities.extend(self._scan_names(text))
        entities.extend(self._scan_addresses(text))
        entities.extend(self._scan_dates(text))

        return self._deduplicate_entities(entities)

    def _scan_indian_identifiers(self, text: str) -> list[PHIEntity]:
        entities = []

        for match in AADHAAR_PATTERN.finditer(text):
            digits = re.sub(r"\s", "", match.group())
            if self._is_valid_aadhaar(digits):
                entities.append(PHIEntity("AADHAAR", match.group(), match.start(), match.end()))

        for match in PAN_PATTERN.finditer(text):
            entities.append(PHIEntity("PAN", match.group(), match.start(), match.end()))

        for match in ABHA_PATTERN.finditer(text):
            entities.append(PHIEntity("ABHA", match.group(), match.start(), match.end()))

        for match in PASSPORT_PATTERN.finditer(text):
            entities.append(PHIEntity("PASSPORT", match.group(), match.start(), match.end(), score=0.7))

        return entities

    def _scan_contact_info(self, text: str) -> list[PHIEntity]:
        entities = []

        for match in INDIAN_PHONE_PATTERN.finditer(text):
            entities.append(PHIEntity("PHONE", match.group(), match.start(), match.end()))

        for match in EMAIL_PATTERN.finditer(text):
            entities.append(PHIEntity("EMAIL", match.group(), match.start(), match.end()))

        return entities

    def _scan_names(self, text: str) -> list[PHIEntity]:
        entities = []
        text_lower = text.lower()

        for prefix in NAME_PREFIXES:
            idx = text_lower.find(prefix)
            while idx != -1:
                name_start = idx + len(prefix)
                while name_start < len(text) and text[name_start] in " :,":
                    name_start += 1

                name_end = name_start
                while name_end < len(text) and text[name_end] not in "\n,;|":
                    name_end += 1

                name_text = text[name_start:name_end].strip()
                if len(name_text) >= self._min_name_length:
                    entities.append(PHIEntity("PERSON_NAME", name_text, name_start, name_end, score=0.8))

                idx = text_lower.find(prefix, idx + 1)

        return entities

    def _scan_addresses(self, text: str) -> list[PHIEntity]:
        entities = []
        text_lower = text.lower()

        for keyword in ADDRESS_KEYWORDS[:6]:
            idx = text_lower.find(keyword)
            if idx != -1:
                addr_start = idx
                addr_end = addr_start
                while addr_end < len(text) and text[addr_end] != "\n":
                    addr_end += 1
                addr_text = text[addr_start:addr_end].strip()
                if len(addr_text) > 10:
                    entities.append(PHIEntity("ADDRESS", addr_text, addr_start, addr_end, score=0.7))

        for match in PINCODE_PATTERN.finditer(text):
            entities.append(PHIEntity("PINCODE", match.group(), match.start(), match.end(), score=0.6))

        return entities

    def _scan_dates(self, text: str) -> list[PHIEntity]:
        entities = []
        for match in DOB_PATTERN.finditer(text):
            entities.append(PHIEntity("DATE_OF_BIRTH", match.group(), match.start(), match.end(), score=0.7))
        return entities

    def _is_valid_aadhaar(self, digits: str) -> bool:
        if len(digits) != 12:
            return False
        if digits[0] in ("0", "1"):
            return False
        if len(set(digits)) == 1:
            return False
        return True

    def _is_sensitive_field(self, field_name: str) -> bool:
        sensitive_fields = {
            "patient_name", "name", "full_name", "first_name", "last_name",
            "aadhaar", "aadhaar_number", "pan", "pan_number",
            "abha", "abha_id", "abha_number",
            "phone", "phone_number", "mobile", "mobile_number",
            "email", "email_address",
            "address", "residential_address", "permanent_address",
            "dob", "date_of_birth",
            "father_name", "mother_name", "spouse_name",
            "emergency_contact_name", "emergency_contact_phone",
        }
        return field_name.lower() in sensitive_fields

    def _classify_field(self, field_name: str) -> str:
        field_lower = field_name.lower()
        if "aadhaar" in field_lower:
            return "AADHAAR"
        if "pan" in field_lower:
            return "PAN"
        if "abha" in field_lower:
            return "ABHA"
        if "phone" in field_lower or "mobile" in field_lower:
            return "PHONE"
        if "email" in field_lower:
            return "EMAIL"
        if "address" in field_lower:
            return "ADDRESS"
        if "name" in field_lower:
            return "PERSON_NAME"
        if "dob" in field_lower or "birth" in field_lower:
            return "DATE_OF_BIRTH"
        return "PII"

    def _redact_value(self, value: str) -> str:
        if len(value) <= 4:
            return self._redaction_char * len(value)
        return value[:2] + self._redaction_char * (len(value) - 4) + value[-2:]

    def _generate_replacement(self, entity: PHIEntity) -> str:
        type_tags = {
            "AADHAAR": "[AADHAAR_REDACTED]",
            "PAN": "[PAN_REDACTED]",
            "ABHA": "[ABHA_REDACTED]",
            "PHONE": "[PHONE_REDACTED]",
            "EMAIL": "[EMAIL_REDACTED]",
            "PERSON_NAME": "[NAME_REDACTED]",
            "PERSON": "[NAME_REDACTED]",
            "ADDRESS": "[ADDRESS_REDACTED]",
            "PINCODE": "[PINCODE_REDACTED]",
            "DATE_OF_BIRTH": "[DOB_REDACTED]",
            "PASSPORT": "[PASSPORT_REDACTED]",
            "DATE_TIME": "[DATE_REDACTED]",
            "LOCATION": "[LOCATION_REDACTED]",
            "EMAIL_ADDRESS": "[EMAIL_REDACTED]",
            "PHONE_NUMBER": "[PHONE_REDACTED]",
        }
        return type_tags.get(entity.entity_type, f"[{entity.entity_type}_REDACTED]")

    def _deduplicate_entities(self, entities: list[PHIEntity]) -> list[PHIEntity]:
        if not entities:
            return []

        entities.sort(key=lambda e: (e.start, -(e.end - e.start)))

        deduplicated = [entities[0]]
        for entity in entities[1:]:
            last = deduplicated[-1]
            if entity.start >= last.end:
                deduplicated.append(entity)
            elif (entity.end - entity.start) > (last.end - last.start):
                deduplicated[-1] = entity

        return deduplicated


deid_pipeline = DeIdentificationPipeline()
