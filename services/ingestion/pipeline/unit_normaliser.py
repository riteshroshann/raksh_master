"""
Unit normalisation for clinical lab values.

Indian labs variably report in SI (mmol/L, µmol/L) or conventional (mg/dL) units.
This module normalises all values to conventional units for consistent storage,
comparison, and trend display. Original values and units are preserved.
"""

import re
from typing import Optional

import structlog

logger = structlog.get_logger()

CONVERSION_TABLE: dict[str, dict[str, tuple[str, float]]] = {
    # glucose: mmol/L -> mg/dL (multiply by 18.016)
    "glucose": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},
    "fasting_plasma_glucose": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},
    "fasting_blood_sugar": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},
    "postprandial_glucose": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},
    "random_blood_sugar": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},
    "fbs": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},
    "rbs": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},
    "ppg": {"mmol/l": ("mg/dL", 18.016), "mmol/L": ("mg/dL", 18.016)},

    # cholesterol: mmol/L -> mg/dL (multiply by 38.67)
    "total_cholesterol": {"mmol/l": ("mg/dL", 38.67), "mmol/L": ("mg/dL", 38.67)},
    "hdl_cholesterol": {"mmol/l": ("mg/dL", 38.67), "mmol/L": ("mg/dL", 38.67)},
    "ldl_cholesterol": {"mmol/l": ("mg/dL", 38.67), "mmol/L": ("mg/dL", 38.67)},
    "vldl_cholesterol": {"mmol/l": ("mg/dL", 38.67), "mmol/L": ("mg/dL", 38.67)},

    # triglycerides: mmol/L -> mg/dL (multiply by 88.57)
    "triglycerides": {"mmol/l": ("mg/dL", 88.57), "mmol/L": ("mg/dL", 88.57)},

    # creatinine: µmol/L -> mg/dL (divide by 88.4)
    "creatinine": {
        "µmol/l": ("mg/dL", 1.0 / 88.4),
        "µmol/L": ("mg/dL", 1.0 / 88.4),
        "umol/l": ("mg/dL", 1.0 / 88.4),
        "umol/L": ("mg/dL", 1.0 / 88.4),
        "micromol/l": ("mg/dL", 1.0 / 88.4),
        "micromol/L": ("mg/dL", 1.0 / 88.4),
    },

    # urea/bun: mmol/L -> mg/dL (multiply by 2.8)
    "blood_urea_nitrogen": {"mmol/l": ("mg/dL", 2.8), "mmol/L": ("mg/dL", 2.8)},
    "bun": {"mmol/l": ("mg/dL", 2.8), "mmol/L": ("mg/dL", 2.8)},
    "urea": {"mmol/l": ("mg/dL", 6.006), "mmol/L": ("mg/dL", 6.006)},

    # uric acid: µmol/L -> mg/dL (divide by 59.48)
    "uric_acid": {
        "µmol/l": ("mg/dL", 1.0 / 59.48),
        "µmol/L": ("mg/dL", 1.0 / 59.48),
        "umol/l": ("mg/dL", 1.0 / 59.48),
        "umol/L": ("mg/dL", 1.0 / 59.48),
    },

    # bilirubin: µmol/L -> mg/dL (divide by 17.1)
    "total_bilirubin": {
        "µmol/l": ("mg/dL", 1.0 / 17.1),
        "µmol/L": ("mg/dL", 1.0 / 17.1),
        "umol/l": ("mg/dL", 1.0 / 17.1),
        "umol/L": ("mg/dL", 1.0 / 17.1),
    },
    "direct_bilirubin": {
        "µmol/l": ("mg/dL", 1.0 / 17.1),
        "µmol/L": ("mg/dL", 1.0 / 17.1),
        "umol/l": ("mg/dL", 1.0 / 17.1),
        "umol/L": ("mg/dL", 1.0 / 17.1),
    },

    # calcium: mmol/L -> mg/dL (multiply by 4.0)
    "calcium": {"mmol/l": ("mg/dL", 4.0), "mmol/L": ("mg/dL", 4.0)},

    # phosphorus: mmol/L -> mg/dL (multiply by 3.1)
    "phosphorus": {"mmol/l": ("mg/dL", 3.1), "mmol/L": ("mg/dL", 3.1)},

    # magnesium: mmol/L -> mg/dL (multiply by 2.43)
    "magnesium": {"mmol/l": ("mg/dL", 2.43), "mmol/L": ("mg/dL", 2.43)},

    # iron: µmol/L -> mcg/dL (multiply by 5.585)
    "iron": {
        "µmol/l": ("mcg/dL", 5.585),
        "µmol/L": ("mcg/dL", 5.585),
        "umol/l": ("mcg/dL", 5.585),
        "umol/L": ("mcg/dL", 5.585),
    },

    # albumin: g/L -> g/dL (divide by 10)
    "albumin": {"g/l": ("g/dL", 0.1), "g/L": ("g/dL", 0.1)},
    "total_protein": {"g/l": ("g/dL", 0.1), "g/L": ("g/dL", 0.1)},

    # hemoglobin: g/L -> g/dL (divide by 10), mmol/L -> g/dL (multiply by 1.611)
    "hemoglobin": {
        "g/l": ("g/dL", 0.1),
        "g/L": ("g/dL", 0.1),
        "mmol/l": ("g/dL", 1.611),
        "mmol/L": ("g/dL", 1.611),
    },
}


def _normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", name.lower().strip().replace(" ", "_"))


def normalise_unit(
    parameter_name: str,
    value: float,
    unit: str,
) -> dict:
    """
    Returns a dict with normalised value and unit, plus originals.
    If no conversion is needed, returns the input unchanged.
    """
    normalized_name = _normalize_name(parameter_name)
    conversions = CONVERSION_TABLE.get(normalized_name, {})

    if unit in conversions:
        target_unit, factor = conversions[unit]
        converted_value = round(value * factor, 2)

        logger.info(
            "unit_normalised",
            parameter=parameter_name,
            original_value=value,
            original_unit=unit,
            converted_value=converted_value,
            converted_unit=target_unit,
            factor=round(factor, 6),
        )

        return {
            "value": converted_value,
            "unit": target_unit,
            "original_value": value,
            "original_unit": unit,
            "was_converted": True,
        }

    return {
        "value": value,
        "unit": unit,
        "original_value": value,
        "original_unit": unit,
        "was_converted": False,
    }


def normalise_extraction(extraction: dict) -> dict:
    """
    Normalise units on a single extraction dict in place.
    Preserves original_value and original_unit if conversion happens.
    """
    name = extraction.get("name", extraction.get("parameter_name", ""))
    value = extraction.get("value_numeric")
    unit = extraction.get("unit", "")

    if value is None or not unit or not name:
        return extraction

    result = normalise_unit(name, float(value), unit)

    if result["was_converted"]:
        extraction["value_numeric"] = result["value"]
        extraction["unit"] = result["unit"]
        extraction["original_value"] = result["original_value"]
        extraction["original_unit"] = result["original_unit"]
        extraction["unit_converted"] = True

        if extraction.get("value"):
            extraction["value"] = str(result["value"])

    return extraction


def normalise_batch(extractions: list[dict]) -> list[dict]:
    """Normalise units across a list of extractions."""
    converted = 0
    for extraction in extractions:
        before = extraction.get("unit")
        normalise_extraction(extraction)
        if extraction.get("unit_converted"):
            converted += 1

    if converted > 0:
        logger.info("unit_batch_normalised", converted=converted, total=len(extractions))

    return extractions
