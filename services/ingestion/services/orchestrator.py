import time
import asyncio
from typing import Optional
from datetime import datetime

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class PipelineOrchestrator:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def record_pipeline_start(
        self,
        ingest_id: str,
        channel: str,
        file_size_bytes: int,
        file_type: str,
    ) -> Optional[str]:
        run_data = {
            "ingest_id": ingest_id,
            "channel": channel,
            "status": "started",
            "started_at": datetime.utcnow().isoformat(),
            "file_size_bytes": file_size_bytes,
            "file_type": file_type,
            "steps": [],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                json=run_data,
            )

            if response.status_code in (200, 201):
                record = response.json()[0]
                return record["id"]

            logger.error("pipeline_run_start_failed", status=response.status_code)
            return None

    async def record_step(
        self,
        run_id: str,
        step_name: str,
        status: str,
        duration_ms: float,
        details: Optional[dict] = None,
    ) -> None:
        step = {
            "step": step_name,
            "status": status,
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            current = await client.get(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                params={"id": f"eq.{run_id}", "select": "steps"},
            )

            if current.status_code == 200:
                rows = current.json()
                if rows:
                    existing_steps = rows[0].get("steps", [])
                    existing_steps.append(step)

                    await client.patch(
                        f"{self._base_url}/pipeline_runs",
                        headers=self._headers,
                        params={"id": f"eq.{run_id}"},
                        json={"steps": existing_steps},
                    )

    async def record_pipeline_complete(
        self,
        run_id: str,
        document_id: Optional[str],
        classification_result: Optional[str],
        classification_confidence: Optional[float],
        extraction_model: Optional[str],
        extraction_field_count: int,
        confidence_above: int,
        confidence_below: int,
        image_quality: Optional[str],
        total_duration_ms: float,
    ) -> None:
        update_data = {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": round(total_duration_ms, 2),
            "document_id": document_id,
            "classification_result": classification_result,
            "classification_confidence": classification_confidence,
            "extraction_model": extraction_model,
            "extraction_field_count": extraction_field_count,
            "confidence_above_threshold": confidence_above,
            "confidence_below_threshold": confidence_below,
            "image_quality": image_quality,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.patch(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                params={"id": f"eq.{run_id}"},
                json=update_data,
            )

        logger.info(
            "pipeline_completed",
            run_id=run_id,
            duration_ms=round(total_duration_ms, 2),
            fields_extracted=extraction_field_count,
            above_threshold=confidence_above,
            below_threshold=confidence_below,
        )

    async def record_pipeline_failure(
        self,
        run_id: str,
        error_step: str,
        error_message: str,
        total_duration_ms: float,
    ) -> None:
        update_data = {
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "duration_ms": round(total_duration_ms, 2),
            "error_step": error_step,
            "error_message": error_message,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.patch(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                params={"id": f"eq.{run_id}"},
                json=update_data,
            )

        logger.error(
            "pipeline_failed",
            run_id=run_id,
            error_step=error_step,
            error_message=error_message,
            duration_ms=round(total_duration_ms, 2),
        )

    async def get_pipeline_run(self, run_id: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                params={"id": f"eq.{run_id}", "limit": "1"},
            )

            if response.status_code == 200:
                rows = response.json()
                return rows[0] if rows else None
            return None

    async def get_runs_for_document(self, document_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                params={"document_id": f"eq.{document_id}", "order": "created_at.desc"},
            )

            if response.status_code == 200:
                return response.json()
            return []

    async def get_recent_failures(self, limit: int = 20) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                params={
                    "status": "eq.failed",
                    "order": "created_at.desc",
                    "limit": str(limit),
                },
            )

            if response.status_code == 200:
                return response.json()
            return []

    async def get_performance_summary(self, hours: int = 24) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/pipeline_runs",
                headers=self._headers,
                params={
                    "select": "status,duration_ms,channel,classification_result,extraction_field_count,confidence_above_threshold,confidence_below_threshold",
                    "order": "created_at.desc",
                    "limit": "1000",
                },
            )

            if response.status_code != 200:
                return {}

            runs = response.json()

            total = len(runs)
            completed = sum(1 for r in runs if r.get("status") == "completed")
            failed = sum(1 for r in runs if r.get("status") == "failed")

            durations = [r["duration_ms"] for r in runs if r.get("duration_ms") is not None]
            avg_duration = sum(durations) / len(durations) if durations else 0

            p50_duration = sorted(durations)[len(durations) // 2] if durations else 0
            p95_duration = sorted(durations)[int(len(durations) * 0.95)] if durations else 0
            p99_duration = sorted(durations)[int(len(durations) * 0.99)] if durations else 0

            channel_counts = {}
            for r in runs:
                ch = r.get("channel", "unknown")
                channel_counts[ch] = channel_counts.get(ch, 0) + 1

            doc_type_counts = {}
            for r in runs:
                dt = r.get("classification_result", "unknown")
                if dt:
                    doc_type_counts[dt] = doc_type_counts.get(dt, 0) + 1

            total_above = sum(r.get("confidence_above_threshold", 0) for r in runs if r.get("confidence_above_threshold"))
            total_below = sum(r.get("confidence_below_threshold", 0) for r in runs if r.get("confidence_below_threshold"))
            auto_rate = (total_above / (total_above + total_below) * 100) if (total_above + total_below) > 0 else 0

            return {
                "total_runs": total,
                "completed": completed,
                "failed": failed,
                "success_rate": round((completed / total * 100) if total > 0 else 0, 1),
                "avg_duration_ms": round(avg_duration, 2),
                "p50_duration_ms": round(p50_duration, 2),
                "p95_duration_ms": round(p95_duration, 2),
                "p99_duration_ms": round(p99_duration, 2),
                "by_channel": channel_counts,
                "by_doc_type": doc_type_counts,
                "auto_extraction_rate": round(auto_rate, 1),
            }


class NotificationService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
        }

    async def get_preferences(self, account_id: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/notification_preferences",
                headers=self._headers,
                params={"account_id": f"eq.{account_id}", "limit": "1"},
            )

            if response.status_code == 200:
                rows = response.json()
                return rows[0] if rows else None
            return None

    async def update_preferences(self, account_id: str, preferences: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            existing = await self.get_preferences(account_id)

            if existing:
                response = await client.patch(
                    f"{self._base_url}/notification_preferences",
                    headers={**self._headers, "Prefer": "return=representation"},
                    params={"account_id": f"eq.{account_id}"},
                    json={**preferences, "updated_at": datetime.utcnow().isoformat()},
                )
            else:
                response = await client.post(
                    f"{self._base_url}/notification_preferences",
                    headers={**self._headers, "Prefer": "return=representation"},
                    json={"account_id": account_id, **preferences},
                )

            if response.status_code in (200, 201):
                return response.json()[0]
            return {}

    async def notify_critical_value(
        self,
        account_id: str,
        parameter_name: str,
        value: float,
        flag: str,
        member_name: str,
    ) -> bool:
        prefs = await self.get_preferences(account_id)

        if not prefs or not prefs.get("notify_on_critical", True):
            return False

        logger.info(
            "critical_value_notification",
            account_id=account_id,
            parameter=parameter_name,
            value=value,
            flag=flag,
            member_name=member_name,
        )

        return True

    async def notify_extraction_complete(
        self,
        account_id: str,
        document_id: str,
        doc_type: str,
        field_count: int,
        requires_review: int,
    ) -> bool:
        prefs = await self.get_preferences(account_id)

        if not prefs or not prefs.get("notify_on_extraction", True):
            return False

        logger.info(
            "extraction_notification",
            account_id=account_id,
            document_id=document_id,
            doc_type=doc_type,
            field_count=field_count,
            requires_review=requires_review,
        )

        return True

    async def notify_edit_rate_alert(
        self,
        account_id: str,
        edit_rate: float,
        threshold: float,
    ) -> bool:
        prefs = await self.get_preferences(account_id)

        if not prefs or not prefs.get("notify_on_edit_rate_alert", True):
            return False

        logger.warning(
            "edit_rate_alert_notification",
            account_id=account_id,
            edit_rate=edit_rate,
            threshold=threshold,
        )

        return True
