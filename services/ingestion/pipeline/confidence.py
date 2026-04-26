import structlog

logger = structlog.get_logger()

FIELD_THRESHOLDS = {
    "medication_name": 0.92,
    "dosage": 0.92,
    "hb": 0.85,
    "hemoglobin": 0.85,
    "tsh": 0.85,
    "insulin": 0.99,
    "warfarin": 0.99,
    "digoxin": 0.99,
    "date": 0.80,
    "lab_name": 0.75,
    "doctor_name": 0.75,
}

DEFAULT_THRESHOLD = 0.85


def score_confidence(extractions: list[dict]) -> list[dict]:
    result = []
    for field in extractions:
        field_name = field.get("name", "").lower()
        threshold = FIELD_THRESHOLDS.get(field_name, DEFAULT_THRESHOLD)
        confidence = field.get("confidence", 0.0)

        if confidence < threshold:
            scored_field = {
                **field,
                "value": None,
                "value_numeric": None,
                "requires_manual_entry": True,
            }
            logger.info(
                "field_below_threshold",
                field_name=field_name,
                confidence=confidence,
                threshold=threshold,
            )
        else:
            scored_field = {**field, "requires_manual_entry": False}

        result.append(scored_field)

    return result
