import re
import json
from datetime import datetime
from typing import Any, Optional

import structlog

logger = structlog.get_logger()


class WhistleTransformEngine:
    def __init__(self):
        self._mappings: dict[str, dict] = {}
        self._builtin_functions = {
            "$ParseFloat": self._parse_float,
            "$ParseInt": self._parse_int,
            "$ParseDate": self._parse_date,
            "$ToUpper": lambda x: str(x).upper() if x else "",
            "$ToLower": lambda x: str(x).lower() if x else "",
            "$Trim": lambda x: str(x).strip() if x else "",
            "$Hash": lambda x: str(hash(x)) if x else "",
            "$UUID": lambda _: str(__import__("uuid").uuid4()),
            "$Now": lambda _: datetime.utcnow().isoformat() + "Z",
            "$StrJoin": self._str_join,
            "$Split": self._split,
            "$First": lambda x: x[0] if isinstance(x, list) and x else x,
            "$Last": lambda x: x[-1] if isinstance(x, list) and x else x,
            "$Length": lambda x: len(x) if x else 0,
            "$IsNull": lambda x: x is None or x == "",
            "$Default": self._default,
            "$MapCode": self._map_code,
        }
        self._code_mappings = {}

    def register_mapping(self, name: str, mapping_def: dict) -> None:
        self._mappings[name] = mapping_def
        logger.info("whistle_mapping_registered", name=name)

    def register_code_mapping(self, source_system: str, target_system: str, mappings: dict[str, str]) -> None:
        key = f"{source_system}:{target_system}"
        self._code_mappings[key] = mappings

    def transform(self, mapping_name: str, source: dict) -> dict:
        mapping_def = self._mappings.get(mapping_name)
        if not mapping_def:
            raise ValueError(f"Unknown mapping: {mapping_name}")

        return self._apply_mapping(mapping_def, source)

    def transform_batch(self, mapping_name: str, sources: list[dict]) -> list[dict]:
        return [self.transform(mapping_name, source) for source in sources]

    def _apply_mapping(self, mapping_def: dict, source: dict) -> dict:
        result = {}

        for target_field, source_spec in mapping_def.items():
            if isinstance(source_spec, str):
                if source_spec.startswith("$"):
                    func_name, args = self._parse_function_call(source_spec, source)
                    result[target_field] = self._builtin_functions[func_name](args)
                elif source_spec.startswith("@"):
                    result[target_field] = source_spec[1:]
                else:
                    result[target_field] = self._resolve_path(source, source_spec)

            elif isinstance(source_spec, dict):
                if "__array__" in source_spec:
                    array_source = self._resolve_path(source, source_spec["__array__"])
                    item_mapping = source_spec.get("__item__", {})
                    if isinstance(array_source, list):
                        result[target_field] = [
                            self._apply_mapping(item_mapping, item)
                            for item in array_source
                        ]
                    else:
                        result[target_field] = []
                elif "__conditional__" in source_spec:
                    condition_field = source_spec["__conditional__"]
                    condition_value = self._resolve_path(source, condition_field)
                    branches = source_spec.get("__branches__", {})
                    default = source_spec.get("__default__", {})
                    branch = branches.get(str(condition_value), default)
                    if isinstance(branch, dict):
                        result[target_field] = self._apply_mapping(branch, source)
                    else:
                        result[target_field] = branch
                else:
                    result[target_field] = self._apply_mapping(source_spec, source)

            elif isinstance(source_spec, list):
                result[target_field] = source_spec

            else:
                result[target_field] = source_spec

        return result

    def _resolve_path(self, source: dict, path: str) -> Any:
        if not path:
            return None

        parts = path.split(".")
        current = source

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return None
            else:
                return None

            if current is None:
                return None

        return current

    def _parse_function_call(self, spec: str, source: dict) -> tuple[str, Any]:
        match = re.match(r"(\$\w+)\((.+)\)", spec)
        if match:
            func_name = match.group(1)
            arg_str = match.group(2)

            if arg_str.startswith('"') and arg_str.endswith('"'):
                return func_name, arg_str[1:-1]
            elif arg_str.startswith("'") and arg_str.endswith("'"):
                return func_name, arg_str[1:-1]
            else:
                return func_name, self._resolve_path(source, arg_str)

        if spec in self._builtin_functions:
            return spec, None

        return spec, None

    def _parse_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            cleaned = str(value).replace(",", "").strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    def _parse_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (ValueError, TypeError):
            return None

    def _parse_date(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        date_str = str(value).strip()

        formats = [
            "%Y%m%d", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
            "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d%H%M%S",
            "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return date_str

    def _str_join(self, args: Any) -> str:
        if isinstance(args, list):
            return " ".join(str(a) for a in args if a)
        return str(args) if args else ""

    def _split(self, args: Any) -> list:
        if isinstance(args, str):
            return args.split()
        return [args] if args else []

    def _default(self, args: Any) -> Any:
        if isinstance(args, tuple) and len(args) == 2:
            return args[0] if args[0] is not None else args[1]
        return args

    def _map_code(self, args: Any) -> Optional[str]:
        if isinstance(args, dict):
            source_sys = args.get("source_system", "")
            target_sys = args.get("target_system", "")
            code = args.get("code", "")
            key = f"{source_sys}:{target_sys}"
            mappings = self._code_mappings.get(key, {})
            return mappings.get(code, code)
        return None


HL7_TO_FHIR_OBSERVATION = {
    "resourceType": "@Observation",
    "id": "$UUID()",
    "status": "@final",
    "code": {
        "coding": [{
            "__array__": "observations",
            "__item__": {},
        }],
        "text": "identifier_text",
    },
    "subject": {
        "reference": "patient_reference",
    },
    "valueQuantity": {
        "value": "$ParseFloat(value)",
        "unit": "units",
    },
}

HL7_TO_FHIR_PATIENT = {
    "resourceType": "@Patient",
    "id": "patient.id",
    "name": [{
        "use": "@official",
        "text": "patient.name",
    }],
    "birthDate": "$ParseDate(patient.dob)",
    "gender": "patient.sex",
}

CSV_LAB_TO_FHIR = {
    "resourceType": "@Observation",
    "status": "@final",
    "code": {
        "coding": [{
            "system": "@http://loinc.org",
            "display": "test_name",
        }],
    },
    "valueQuantity": {
        "value": "$ParseFloat(result_value)",
        "unit": "unit",
    },
    "referenceRange": [{
        "low": {"value": "$ParseFloat(range_low)"},
        "high": {"value": "$ParseFloat(range_high)"},
    }],
    "effectiveDateTime": "$ParseDate(test_date)",
}


def build_default_engine() -> WhistleTransformEngine:
    engine = WhistleTransformEngine()

    engine.register_mapping("hl7_to_fhir_patient", HL7_TO_FHIR_PATIENT)
    engine.register_mapping("csv_lab_to_fhir_observation", CSV_LAB_TO_FHIR)

    engine.register_code_mapping("local", "loinc", {
        "hemoglobin": "718-7",
        "hematocrit": "4544-3",
        "glucose": "2345-7",
        "creatinine": "2160-0",
        "tsh": "3016-3",
        "cholesterol": "2093-3",
    })

    sex_mapping = {"M": "male", "F": "female", "O": "other", "U": "unknown"}
    engine.register_code_mapping("hl7", "fhir", sex_mapping)

    return engine


whistle_engine = build_default_engine()
