from datetime import datetime
from typing import Optional

import structlog
from supabase import create_client, Client

from config import settings
from models.schemas import ConfirmationPayload, MetricsData

logger = structlog.get_logger()


def _get_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class DatabaseService:
    def __init__(self):
        self._client: Client = _get_client()

    async def health_ping(self) -> bool:
        """Lightweight connectivity check. Raises on failure."""
        self._client.table("documents").select("id").limit(1).execute()
        return True

    async def find_by_content_hash(self, content_hash: str, member_id: str) -> Optional[dict]:
        try:
            result = (
                self._client.table("documents")
                .select("id,content_hash")
                .eq("content_hash", content_hash)
                .eq("member_id", member_id)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as exc:
            logger.error("find_by_hash_failed", error=str(exc), content_hash=content_hash[:16])
            return None

    async def write_confirmed_document(self, payload: ConfirmationPayload) -> str:
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

        doc_result = self._client.table("documents").insert(doc_data).execute()

        if not doc_result.data:
            raise RuntimeError(f"Document insert failed: no data returned")

        document_id = doc_result.data[0]["id"]

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

            try:
                param_result = self._client.table("report_parameters").insert(param_data).execute()
            except Exception as exc:
                logger.error("parameter_insert_failed", error=str(exc), parameter_name=param.parameter_name)
                continue

            if param_result.data:
                parameter_id = param_result.data[0]["id"]

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

                try:
                    self._client.table("extraction_lineage").insert(lineage_data).execute()
                except Exception as exc:
                    logger.error("lineage_insert_failed", error=str(exc), parameter_id=parameter_id)

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

        try:
            self._client.table("audit_log").insert(audit_data).execute()
        except Exception as exc:
            logger.error("audit_insert_failed", error=str(exc))

        logger.info("document_saved", document_id=document_id, member_id=str(payload.member_id), parameters_saved=len(payload.parameters))
        return document_id

    async def list_documents(self, member_id: str, page: int = 1, page_size: int = 20, doc_type: Optional[str] = None) -> tuple[list[dict], int]:
        query = (
            self._client.table("documents")
            .select("*", count="exact")
            .eq("member_id", member_id)
            .order("created_at", desc=True)
            .range((page - 1) * page_size, page * page_size - 1)
        )

        if doc_type:
            query = query.eq("doc_type", doc_type)

        result = query.execute()
        total = result.count if result.count is not None else len(result.data)
        return result.data, total

    async def get_document(self, document_id: str) -> Optional[dict]:
        result = (
            self._client.table("documents")
            .select("*")
            .eq("id", document_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_member(self, member_id: str) -> Optional[dict]:
        result = (
            self._client.table("family_members")
            .select("*")
            .eq("id", member_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_parameters_for_document(self, document_id: str) -> list[dict]:
        result = (
            self._client.table("report_parameters")
            .select("*")
            .eq("document_id", document_id)
            .order("parameter_name")
            .execute()
        )
        return result.data

    async def get_parameter_trend(self, member_id: str, parameter_name: str, limit: int = 50) -> dict:
        result = (
            self._client.table("report_parameters")
            .select("value_numeric,value_text,unit,test_date,flag,confidence,indian_range_low,indian_range_high")
            .eq("member_id", member_id)
            .eq("parameter_name", parameter_name)
            .order("test_date")
            .limit(limit)
            .execute()
        )

        data_points = []
        indian_low = None
        indian_high = None
        unit = None

        for row in result.data:
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
        query = (
            self._client.table("report_parameters")
            .select("*")
            .eq("member_id", member_id)
            .order("test_date", desc=True)
        )

        if parameter_name:
            query = query.eq("parameter_name", parameter_name)

        result = query.execute()
        return result.data

    async def get_pipeline_metrics(self) -> MetricsData:
        total_docs_r = self._client.table("documents").select("id", count="exact").limit(0).execute()
        total_docs = total_docs_r.count or 0

        confirmed_r = self._client.table("documents").select("id", count="exact").not_.is_("confirmed_at", "null").limit(0).execute()
        total_confirmed = confirmed_r.count or 0

        lineage_r = self._client.table("extraction_lineage").select("id", count="exact").limit(0).execute()
        total_params = lineage_r.count or 0

        edits_r = self._client.table("extraction_lineage").select("id", count="exact").eq("patient_edited", True).limit(0).execute()
        total_edits = edits_r.count or 0

        edit_rate = (total_edits / total_params * 100) if total_params > 0 else 0.0

        doc_type_result = self._client.table("documents").select("doc_type").limit(5000).execute()
        doc_type_counts: dict[str, int] = {}
        for row in doc_type_result.data:
            key = row.get("doc_type", "unknown")
            doc_type_counts[key] = doc_type_counts.get(key, 0) + 1

        channel_result = self._client.table("documents").select("ingest_channel").limit(5000).execute()
        channel_counts: dict[str, int] = {}
        for row in channel_result.data:
            key = row.get("ingest_channel", "unknown")
            channel_counts[key] = channel_counts.get(key, 0) + 1

        confidence_result = (
            self._client.table("extraction_lineage")
            .select("confidence_raw")
            .order("created_at", desc=True)
            .limit(1000)
            .execute()
        )

        avg_confidence = 0.0
        confidence_dist = {}
        confidences = [r["confidence_raw"] for r in confidence_result.data if r.get("confidence_raw") is not None]
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
