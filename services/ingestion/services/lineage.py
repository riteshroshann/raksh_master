import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class LineageService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def record_lineage(
        self,
        parameter_id: str,
        document_id: str,
        extraction_model: str,
        raw_ocr_output: str | None = None,
        bounding_box: dict | None = None,
        confidence_raw: float | None = None,
        patient_edited: bool = False,
        original_value: str | None = None,
    ) -> str:
        lineage_data = {
            "parameter_id": parameter_id,
            "document_id": document_id,
            "extraction_model": extraction_model,
            "raw_ocr_output": raw_ocr_output,
            "bounding_box": bounding_box,
            "confidence_raw": confidence_raw,
            "patient_edited": patient_edited,
            "original_value": original_value,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/extraction_lineage",
                headers=self._headers,
                json=lineage_data,
            )

            if response.status_code not in (200, 201):
                logger.error(
                    "lineage_insert_failed",
                    status=response.status_code,
                    parameter_id=parameter_id,
                )
                raise RuntimeError(f"Lineage insert failed: {response.status_code}")

            record = response.json()[0]
            lineage_id = record["id"]

            logger.info(
                "lineage_recorded",
                lineage_id=lineage_id,
                parameter_id=parameter_id,
                document_id=document_id,
                extraction_model=extraction_model,
                patient_edited=patient_edited,
            )

            return lineage_id

    async def get_lineage_for_parameter(self, parameter_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/extraction_lineage",
                headers=self._headers,
                params={
                    "parameter_id": f"eq.{parameter_id}",
                    "order": "created_at.desc",
                },
            )

            if response.status_code != 200:
                logger.error("lineage_lookup_failed", status=response.status_code)
                return []

            return response.json()

    async def get_lineage_for_document(self, document_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/extraction_lineage",
                headers=self._headers,
                params={
                    "document_id": f"eq.{document_id}",
                    "order": "created_at.desc",
                },
            )

            if response.status_code != 200:
                logger.error("lineage_lookup_failed", status=response.status_code)
                return []

            return response.json()
