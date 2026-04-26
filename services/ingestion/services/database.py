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
                params={"content_hash": f"eq.{content_hash}", "member_id": f"eq.{member_id}", "select": "id,content_hash", "limit": "1"},
            )
            if response.status_code != 200:
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

            doc_response = await client.post(f"{self._base_url}/documents", headers=self._headers, json=doc_data)
            if doc_response.status_code not in (200, 201):
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

                param_response = await client.post(f"{self._base_url}/report_parameters", headers=self._headers, json=param_data)
                if param_response.status_code not in (200, 201):
                    logger.error("parameter_insert_failed", status=param_response.status_code, parameter_name=param.parameter_name)
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

                await client.post(f"{self._base_url}/extraction_lineage", headers=self._headers, json=lineage_data)

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
            await client.post(f"{self._base_url}/audit_log", headers=self._headers, json=audit_data)

            logger.info("document_saved", document_id=document_id, member_id=str(payload.member_id), parameters_saved=len(payload.parameters))
            return document_id

    async def list_documents(self, member_id: str, page: int = 1, page_size: int = 20, doc_type: Optional[str] = None) -> tuple[list[dict], int]:
        params: dict = {
            "member_id": f"eq.{member_id}",
            "order": "created_at.desc",
            "limit": str(page_size),
            "offset": str((page - 1) * page_size),
        }
        if doc_type:
            params["doc_type"] = f"eq.{doc_type}"

        count_headers = {**self._headers, "Prefer": "count=exact"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self._base_url}/documents", headers=count_headers, params=params)

            total = 0
            if "content-range" in response.headers:
                parts = response.headers["content-range"].split("/")
                if len(parts) == 2 and parts[1] != "*":
                    total = int(parts[1])

            if response.status_code == 200:
                return response.json(), total
            return [], 0

    async def get_document(self, document_id: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/documents",
                headers=self._headers,
                params={"id": f"eq.{document_id}", "limit": "1"},
            )
            if response.status_code == 200:
                results = response.json()
                return results[0] if results else None
            return None

    async def get_member(self, member_id: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/family_members",
                headers=self._headers,
                params={"id": f"eq.{member_id}", "limit": "1"},
            )
            if response.status_code == 200:
                results = response.json()
                return results[0] if results else None
            return None

    async def get_parameters_for_document(self, document_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/report_parameters",
                headers=self._headers,
                params={"document_id": f"eq.{document_id}", "order": "parameter_name"},
            )
            if response.status_code == 200:
                return response.json()
            return []

    async def get_parameter_trend(self, member_id: str, parameter_name: str, limit: int = 50) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/report_parameters",
                headers=self._headers,
                params={
                    "member_id": f"eq.{member_id}",
                    "parameter_name": f"eq.{parameter_name}",
                    "order": "test_date.asc",
                    "limit": str(limit),
                    "select": "value_numeric,value_text,unit,test_date,flag,confidence,indian_range_low,indian_range_high",
                },
            )

            data_points = []
            indian_low = None
            indian_high = None
            unit = None

            if response.status_code == 200:
                rows = response.json()
                for row in rows:
                    data_points.append({
                        "date": row.get("test_date"),
                        "value": row.get("value_numeric"),
                        "value_text": row.get("value_text"),
                        "flag": row.get("flag"),
                        "confidence": row.get("confidence"),
                    })
                    if row.get("indian_range_low") is not None:
                        indian_low = row["indian_range_low"]
                    if row.get("indian_range_high") is not None:
                        indian_high = row["indian_range_high"]
                    if row.get("unit"):
                        unit = row["unit"]

            return {
                "parameter_name": parameter_name,
                "unit": unit,
                "data_points": data_points,
                "indian_range_low": indian_low,
                "indian_range_high": indian_high,
            }

    async def get_parameters_by_member(self, member_id: str, parameter_name: Optional[str] = None) -> list[dict]:
        params: dict = {"member_id": f"eq.{member_id}", "order": "test_date.desc"}
        if parameter_name:
            params["parameter_name"] = f"eq.{parameter_name}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self._base_url}/report_parameters", headers=self._headers, params=params)
            if response.status_code == 200:
                return response.json()
            return []

    async def get_pipeline_metrics(self) -> MetricsData:
        async with httpx.AsyncClient(timeout=30.0) as client:
            count_headers = {**self._headers, "Prefer": "count=exact"}

            total_docs = await self._count_table(client, count_headers, "documents")
            total_confirmed = await self._count_table(client, count_headers, "documents", {"confirmed_at": "not.is.null"})

            total_params = await self._count_table(client, count_headers, "extraction_lineage")
            total_edits = await self._count_table(client, count_headers, "extraction_lineage", {"patient_edited": "eq.true"})

            edit_rate = (total_edits / total_params * 100) if total_params > 0 else 0.0

            doc_type_counts = await self._group_count(client, "documents", "doc_type")
            channel_counts = await self._group_count(client, "documents", "ingest_channel")

            confidence_response = await client.get(
                f"{self._base_url}/extraction_lineage",
                headers=self._headers,
                params={"select": "confidence_raw", "limit": "1000", "order": "created_at.desc"},
            )

            avg_confidence = 0.0
            confidence_dist = {}
            if confidence_response.status_code == 200:
                rows = confidence_response.json()
                confidences = [r["confidence_raw"] for r in rows if r.get("confidence_raw") is not None]
                if confidences:
                    avg_confidence = sum(confidences) / len(confidences)
                    buckets = {"0.0-0.5": 0, "0.5-0.7": 0, "0.7-0.85": 0, "0.85-0.95": 0, "0.95-1.0": 0}
                    for c in confidences:
                        if c < 0.5:
                            buckets["0.0-0.5"] += 1
                        elif c < 0.7:
                            buckets["0.5-0.7"] += 1
                        elif c < 0.85:
                            buckets["0.7-0.85"] += 1
                        elif c < 0.95:
                            buckets["0.85-0.95"] += 1
                        else:
                            buckets["0.95-1.0"] += 1
                    total_c = len(confidences)
                    confidence_dist = {k: round(v / total_c * 100, 1) for k, v in buckets.items()}

            return MetricsData(
                total_ingestions=total_docs,
                total_confirmations=total_confirmed,
                average_confidence=round(avg_confidence, 4),
                patient_edit_rate=round(edit_rate, 2),
                extractions_by_doc_type=doc_type_counts,
                extractions_by_channel=channel_counts,
                confidence_distribution=confidence_dist,
            )

    async def _count_table(self, client: httpx.AsyncClient, headers: dict, table: str, extra_params: Optional[dict] = None) -> int:
        params = {"select": "id", "limit": "0"}
        if extra_params:
            params.update(extra_params)

        response = await client.get(f"{self._base_url}/{table}", headers=headers, params=params)

        if "content-range" in response.headers:
            parts = response.headers["content-range"].split("/")
            if len(parts) == 2 and parts[1] != "*":
                return int(parts[1])
        return 0

    async def _group_count(self, client: httpx.AsyncClient, table: str, group_field: str) -> dict[str, int]:
        response = await client.get(
            f"{self._base_url}/{table}",
            headers=self._headers,
            params={"select": group_field, "limit": "5000"},
        )

        counts: dict[str, int] = {}
        if response.status_code == 200:
            for row in response.json():
                key = row.get(group_field, "unknown")
                counts[key] = counts.get(key, 0) + 1

        return counts
