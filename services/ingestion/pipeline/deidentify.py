import structlog

logger = structlog.get_logger()

PHI_ENTITIES = [
    "PERSON",
    "DATE_TIME",
    "PHONE_NUMBER",
    "EMAIL_ADDRESS",
    "LOCATION",
    "IN_PAN",
    "IN_AADHAAR",
    "MEDICAL_LICENSE",
]


class DeidentificationService:
    def __init__(self):
        self._analyzer = None
        self._anonymizer = None
        self._initialized = False

    def _initialize(self):
        if self._initialized:
            return
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._initialized = True
            logger.info("deidentification_engine_initialized")
        except ImportError:
            logger.warning(
                "presidio_not_available",
                detail="Install presidio-analyzer and presidio-anonymizer for PHI de-identification",
            )
            self._initialized = False

    def deidentify_text(self, text: str) -> tuple[str, list]:
        self._initialize()

        if not self._initialized or not self._analyzer or not self._anonymizer:
            logger.warning("deidentification_skipped", reason="engine_not_available")
            return text, []

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=PHI_ENTITIES,
        )

        redacted = self._anonymizer.anonymize(text=text, analyzer_results=results)

        logger.info(
            "deidentification_completed",
            entities_found=len(results),
            entity_types=[r.entity_type for r in results],
        )

        return redacted.text, results

    def contains_phi(self, text: str) -> bool:
        self._initialize()

        if not self._initialized or not self._analyzer:
            return False

        results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=PHI_ENTITIES,
        )

        return len(results) > 0


deidentification_service = DeidentificationService()
