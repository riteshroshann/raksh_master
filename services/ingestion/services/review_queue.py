from datetime import datetime
from typing import Optional
from enum import Enum

import structlog
from supabase import create_client, Client

from config import settings

logger = structlog.get_logger()


def _get_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ReviewPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewQueueService:
    CONFIDENCE_THRESHOLDS = {
        "critical": 0.40,
        "high": 0.55,
        "medium": 0.70,
        "low": 0.85,
    }

    def __init__(self):
        self._client: Client = _get_client()

    def queue_for_review(
        self,
        ingest_id: str,
        document_id: Optional[str],
        member_id: str,
        extraction: dict,
        reason: str,
    ) -> dict:
        confidence = extraction.get("confidence", 0.0)
        priority = self._assess_priority(confidence, extraction)

        review_item = {
            "ingest_id": ingest_id,
            "document_id": document_id,
            "member_id": member_id,
            "parameter_name": extraction.get("name", "unknown"),
            "extracted_value": extraction.get("value"),
            "extracted_value_numeric": extraction.get("value_numeric"),
            "unit": extraction.get("unit"),
            "confidence": confidence,
            "extraction_model": extraction.get("extraction_model"),
            "raw_ocr_output": extraction.get("raw_ocr_output"),
            "bounding_box": extraction.get("bounding_box"),
            "reason": reason,
            "priority": priority,
            "status": ReviewStatus.PENDING.value,
        }

        try:
            result = self._client.table("review_queue").insert(review_item).execute()
            if result.data:
                review_id = result.data[0].get("id", "unknown")
                logger.info(
                    "queued_for_review",
                    review_id=review_id,
                    ingest_id=ingest_id,
                    parameter=extraction.get("name"),
                    confidence=confidence,
                    priority=priority,
                    reason=reason,
                )
                return result.data[0]
        except Exception as exc:
            logger.error("review_queue_insert_failed", error=str(exc))

        return review_item

    def queue_low_confidence_extractions(
        self,
        ingest_id: str,
        document_id: Optional[str],
        member_id: str,
        extractions: list[dict],
        threshold: float = 0.70,
    ) -> list[dict]:
        queued = []
        for extraction in extractions:
            confidence = extraction.get("confidence", 0.0)
            if confidence < threshold:
                reason = f"Confidence {confidence:.2f} below threshold {threshold:.2f}"
                item = self.queue_for_review(
                    ingest_id, document_id, member_id, extraction, reason
                )
                queued.append(item)

        if queued:
            logger.warning(
                "low_confidence_extractions_queued",
                ingest_id=ingest_id,
                count=len(queued),
                parameters=[q.get("parameter_name") for q in queued],
            )

        return queued

    def get_pending_reviews(
        self,
        page: int = 1,
        page_size: int = 50,
        priority: Optional[str] = None,
        member_id: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        try:
            query = (
                self._client.table("review_queue")
                .select("*", count="exact")
                .eq("status", ReviewStatus.PENDING.value)
                .order("created_at", desc=True)
                .range((page - 1) * page_size, page * page_size - 1)
            )

            if priority:
                query = query.eq("priority", priority)
            if member_id:
                query = query.eq("member_id", member_id)

            result = query.execute()
            total = result.count if result.count is not None else len(result.data)
            return result.data, total
        except Exception as exc:
            logger.error("review_queue_fetch_failed", error=str(exc))
            return [], 0

    def approve_review(self, review_id: str, reviewer_id: str) -> Optional[dict]:
        return self._update_status(review_id, ReviewStatus.APPROVED, reviewer_id)

    def correct_review(
        self,
        review_id: str,
        reviewer_id: str,
        corrected_value: str,
        corrected_value_numeric: Optional[float] = None,
    ) -> Optional[dict]:
        try:
            result = (
                self._client.table("review_queue")
                .update({
                    "status": ReviewStatus.CORRECTED.value,
                    "reviewer_id": reviewer_id,
                    "reviewed_at": datetime.utcnow().isoformat(),
                    "corrected_value": corrected_value,
                    "corrected_value_numeric": corrected_value_numeric,
                })
                .eq("id", review_id)
                .execute()
            )

            if result.data:
                logger.info(
                    "review_corrected",
                    review_id=review_id,
                    reviewer=reviewer_id,
                    original=result.data[0].get("extracted_value"),
                    corrected=corrected_value,
                )
                return result.data[0]
        except Exception as exc:
            logger.error("review_correction_failed", error=str(exc))

        return None

    def reject_review(self, review_id: str, reviewer_id: str, reason: str = "") -> Optional[dict]:
        try:
            result = (
                self._client.table("review_queue")
                .update({
                    "status": ReviewStatus.REJECTED.value,
                    "reviewer_id": reviewer_id,
                    "reviewed_at": datetime.utcnow().isoformat(),
                    "rejection_reason": reason,
                })
                .eq("id", review_id)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as exc:
            logger.error("review_rejection_failed", error=str(exc))
            return None

    def get_review_stats(self) -> dict:
        try:
            pending_r = (
                self._client.table("review_queue")
                .select("id", count="exact")
                .eq("status", ReviewStatus.PENDING.value)
                .limit(0)
                .execute()
            )
            approved_r = (
                self._client.table("review_queue")
                .select("id", count="exact")
                .eq("status", ReviewStatus.APPROVED.value)
                .limit(0)
                .execute()
            )
            corrected_r = (
                self._client.table("review_queue")
                .select("id", count="exact")
                .eq("status", ReviewStatus.CORRECTED.value)
                .limit(0)
                .execute()
            )
            rejected_r = (
                self._client.table("review_queue")
                .select("id", count="exact")
                .eq("status", ReviewStatus.REJECTED.value)
                .limit(0)
                .execute()
            )

            return {
                "pending": pending_r.count or 0,
                "approved": approved_r.count or 0,
                "corrected": corrected_r.count or 0,
                "rejected": rejected_r.count or 0,
                "correction_rate": round(
                    (corrected_r.count or 0) / max((approved_r.count or 0) + (corrected_r.count or 0), 1) * 100, 2
                ),
            }
        except Exception as exc:
            logger.error("review_stats_failed", error=str(exc))
            return {"pending": 0, "approved": 0, "corrected": 0, "rejected": 0, "correction_rate": 0.0}

    def _assess_priority(self, confidence: float, extraction: dict) -> str:
        name = extraction.get("name", "").lower()

        high_risk_fields = {"insulin", "warfarin", "digoxin", "methotrexate", "lithium", "dosage", "medication_name"}
        if name in high_risk_fields:
            return ReviewPriority.CRITICAL.value

        if confidence < self.CONFIDENCE_THRESHOLDS["critical"]:
            return ReviewPriority.CRITICAL.value
        if confidence < self.CONFIDENCE_THRESHOLDS["high"]:
            return ReviewPriority.HIGH.value
        if confidence < self.CONFIDENCE_THRESHOLDS["medium"]:
            return ReviewPriority.MEDIUM.value
        return ReviewPriority.LOW.value

    def _update_status(self, review_id: str, status: ReviewStatus, reviewer_id: str) -> Optional[dict]:
        try:
            result = (
                self._client.table("review_queue")
                .update({
                    "status": status.value,
                    "reviewer_id": reviewer_id,
                    "reviewed_at": datetime.utcnow().isoformat(),
                })
                .eq("id", review_id)
                .execute()
            )
            if result.data:
                logger.info("review_status_updated", review_id=review_id, status=status.value, reviewer=reviewer_id)
                return result.data[0]
        except Exception as exc:
            logger.error("review_status_update_failed", error=str(exc))
        return None


review_queue = ReviewQueueService()
