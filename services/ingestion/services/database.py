from datetime import datetime
from typing import Optional

import httpx
import structlog

from config import settings
from models.schemas import ConfirmationPayload, MetricsData

logger = structlog.get_logger()


class DatabaseService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def find_by_content_hash(self, content_hash: str, member_id: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/documents",
                headers=self._headers,
                params={
                    "content_hash": f"eq.{content_hash}",
                    "member_id": f"eq.{member_id}",
                    "select": "id,content_hash",
                    "limit": "1",
                },
            )

            if response.status_code != 200:
                logger.error("hash_lookup_failed", status=response.status_code)
                return None

            results = response.json()
            return results[0] if results else None

    async def write_confirmed_document(self, payload: ConfirmationPayload) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            doc_data = {
                "member_id": str(payload.member_id),
                "ingest_channel": payload.ingest_channel.value,
                "file_path": payload.storage_path,
                "doc_type": payload.doc_type.value,
                "doc_date": payload.doc_date.isoformat() if payload.doc_date else None,
                "lab_name": payload.lab_name,
                "doctor_name": payload.doctor_name,
                "content_hash": payload.content_hash,
                "confirmed_at": datetime.utcnow().isoformat(),
            }

            doc_response = await client.post(
                f"{self._base_url}/documents",
                headers=self._headers,
                json=doc_data,
            )

            if doc_response.status_code not in (200, 201):
                logger.error(
                    "document_insert_failed",
                    status=doc_response.status_code,
                    detail=doc_response.text,
                )
                raise RuntimeError(f"Document insert failed: {doc_response.status_code}")

            document = doc_response.json()[0]
            document_id = document["id"]

            for param in payload.parameters:
                param_data = {
                    "document_id": document_id,
                    "member_id": str(payload.member_id),
                    "parameter_name": param.parameter_name,
                    "value_numeric": param.value_numeric,
                    "value_text": param.value_text,
                    "unit": param.unit,
                    "lab_range_low": param.lab_range_low,
                    "lab_range_high": param.lab_range_high,
                    "indian_range_low": param.indian_range_low,
                    "indian_range_high": param.indian_range_high,
                    "flag": param.flag.value,
                    "confidence": param.confidence,
                    "fasting_status": param.fasting_status.value,
                    "test_date": param.test_date.isoformat(),
                }

                param_response = await client.post(
                    f"{self._base_url}/report_parameters",
                    headers=self._headers,
                    json=param_data,
                )

                if param_response.status_code not in (200, 201):
                    logger.error(
                        "parameter_insert_failed",
                        status=param_response.status_code,
                        parameter_name=param.parameter_name,
                    )
                    continue

                parameter_record = param_response.json()[0]
                parameter_id = parameter_record["id"]

                lineage_data = {
                    "parameter_id": parameter_id,
                    "document_id": document_id,
                    "extraction_model": param.extraction_model or "manual",
                    "raw_ocr_output": param.raw_ocr_output,
                    "bounding_box": param.bounding_box,
                    "confidence_raw": param.confidence,
                    "patient_edited": param.patient_edited,
                    "original_value": param.original_value,
                }

                await client.post(
                    f"{self._base_url}/extraction_lineage",
                    headers=self._headers,
                    json=lineage_data,
                )

            audit_data = {
                "event": "DOCUMENT_CONFIRMED",
                "account_id": None,
                "details": {
                    "document_id": document_id,
                    "member_id": str(payload.member_id),
                    "doc_type": payload.doc_type.value,
                    "channel": payload.ingest_channel.value,
                    "parameters_count": len(payload.parameters),
                },
            }

            await client.post(
                f"{self._base_url}/audit_log",
                headers=self._headers,
                json=audit_data,
            )

            logger.info(
                "document_saved",
                document_id=document_id,
                member_id=str(payload.member_id),
                parameters_saved=len(payload.parameters),
            )

            return document_id

    async def get_pipeline_metrics(self) -> MetricsData:
        async with httpx.AsyncClient(timeout=30.0) as client:
            count_headers = {**self._headers, "Prefer": "count=exact"}

            doc_response = await client.get(
                f"{self._base_url}/documents",
                headers=count_headers,
                params={"select": "id", "limit": "0"},
            )
            total_docs = 0
            if "content-range" in doc_response.headers:
                range_header = doc_response.headers["content-range"]
                parts = range_header.split("/")
                if len(parts) == 2 and parts[1] != "*":
                    total_docs = int(parts[1])

            confirmed_response = await client.get(
                f"{self._base_url}/documents",
                headers=count_headers,
                params={"select": "id", "confirmed_at": "not.is.null", "limit": "0"},
            )
            total_confirmed = 0
            if "content-range" in confirmed_response.headers:
                range_header = confirmed_response.headers["content-range"]
                parts = range_header.split("/")
                if len(parts) == 2 and parts[1] != "*":
                    total_confirmed = int(parts[1])

            lineage_response = await client.get(
                f"{self._base_url}/extraction_lineage",
                headers=count_headers,
                params={"select": "id", "patient_edited": "eq.true", "limit": "0"},
            )
            total_edits = 0
            if "content-range" in lineage_response.headers:
                range_header = lineage_response.headers["content-range"]
                parts = range_header.split("/")
                if len(parts) == 2 and parts[1] != "*":
                    total_edits = int(parts[1])

            total_params_response = await client.get(
                f"{self._base_url}/extraction_lineage",
                headers=count_headers,
                params={"select": "id", "limit": "0"},
            )
            total_params = 0
            if "content-range" in total_params_response.headers:
                range_header = total_params_response.headers["content-range"]
                parts = range_header.split("/")
                if len(parts) == 2 and parts[1] != "*":
                    total_params = int(parts[1])

            edit_rate = (total_edits / total_params * 100) if total_params > 0 else 0.0

            return MetricsData(
                total_ingestions=total_docs,
                total_confirmations=total_confirmed,
                average_confidence=0.0,
                patient_edit_rate=edit_rate,
            )
