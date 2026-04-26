from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class AuditService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def log_event(
        self,
        event: str,
        account_id: Optional[UUID] = None,
        details: Optional[dict] = None,
    ) -> str:
        entry = {
            "event": event,
            "account_id": str(account_id) if account_id else None,
            "details": details,
            "executed_at": datetime.utcnow().isoformat(),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/audit_log",
                headers=self._headers,
                json=entry,
            )

            if response.status_code not in (200, 201):
                logger.error("audit_log_failed", status=response.status_code, event=event)
                raise RuntimeError(f"Audit log insert failed: {response.status_code}")

            record = response.json()[0]
            logger.info("audit_event_logged", event=event, audit_id=record["id"])
            return record["id"]

    async def log_document_upload(self, ingest_id: str, channel: str, member_id: Optional[str] = None) -> str:
        return await self.log_event(
            "DOCUMENT_UPLOADED",
            details={"ingest_id": ingest_id, "channel": channel, "member_id": member_id},
        )

    async def log_extraction(self, ingest_id: str, doc_type: str, model: str, field_count: int) -> str:
        return await self.log_event(
            "EXTRACTION_COMPLETED",
            details={"ingest_id": ingest_id, "doc_type": doc_type, "model": model, "field_count": field_count},
        )

    async def log_confirmation(self, document_id: str, member_id: str, param_count: int) -> str:
        return await self.log_event(
            "DOCUMENT_CONFIRMED",
            details={"document_id": document_id, "member_id": member_id, "parameters_count": param_count},
        )

    async def log_duplicate_detected(self, content_hash: str, member_id: str) -> str:
        return await self.log_event(
            "DUPLICATE_DETECTED",
            details={"content_hash": content_hash, "member_id": member_id},
        )

    async def log_classification_failure(self, ingest_id: str, reason: str) -> str:
        return await self.log_event(
            "CLASSIFICATION_FAILED",
            details={"ingest_id": ingest_id, "reason": reason},
        )

    async def log_extraction_failure(self, ingest_id: str, model: str, error: str) -> str:
        return await self.log_event(
            "EXTRACTION_FAILED",
            details={"ingest_id": ingest_id, "model": model, "error": error},
        )

    async def log_patient_link(self, ingest_id: str, member_id: str, match_score: float, signals: list[str]) -> str:
        return await self.log_event(
            "PATIENT_LINKED",
            details={"ingest_id": ingest_id, "member_id": member_id, "match_score": match_score, "signals": signals},
        )

    async def log_unlinked_queued(self, ingest_id: str, doc_type: str) -> str:
        return await self.log_event(
            "UNLINKED_QUEUED",
            details={"ingest_id": ingest_id, "doc_type": doc_type},
        )

    async def log_abbreviation_hazard(self, ingest_id: str, field: str, matches: list[str]) -> str:
        return await self.log_event(
            "ABBREVIATION_HAZARD_DETECTED",
            details={"ingest_id": ingest_id, "field": field, "matches": matches},
        )

    async def log_corrupted_file(self, ingest_id: str, filename: str, error_type: str) -> str:
        return await self.log_event(
            "CORRUPTED_FILE_DETECTED",
            details={"ingest_id": ingest_id, "filename": filename, "error_type": error_type},
        )

    async def get_entries(
        self,
        event_filter: Optional[str] = None,
        account_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[dict], int]:
        params: dict = {"order": "executed_at.desc", "limit": str(page_size), "offset": str((page - 1) * page_size)}

        if event_filter:
            params["event"] = f"eq.{event_filter}"
        if account_id:
            params["account_id"] = f"eq.{str(account_id)}"

        count_headers = {**self._headers, "Prefer": "count=exact"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/audit_log",
                headers=count_headers,
                params=params,
            )

            total = 0
            if "content-range" in response.headers:
                range_header = response.headers["content-range"]
                parts = range_header.split("/")
                if len(parts) == 2 and parts[1] != "*":
                    total = int(parts[1])

            if response.status_code == 200:
                return response.json(), total
            return [], 0
