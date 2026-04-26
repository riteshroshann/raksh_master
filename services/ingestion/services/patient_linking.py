from datetime import date, datetime
from typing import Optional
from uuid import UUID

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class PatientLinkingService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def find_matching_members(
        self,
        patient_name: Optional[str] = None,
        patient_dob: Optional[date] = None,
        doctor_name: Optional[str] = None,
        doc_date: Optional[date] = None,
        doc_type: Optional[str] = None,
        mrn: Optional[str] = None,
    ) -> list[dict]:
        candidates = []

        if mrn:
            mrn_matches = await self._match_by_mrn(mrn)
            for match in mrn_matches:
                candidates.append({
                    "member_id": match["id"],
                    "name": match["name"],
                    "dob": match["dob"],
                    "match_score": 1.0,
                    "match_signals": ["mrn_exact_match"],
                })
            if candidates:
                return candidates

        if patient_name and patient_dob:
            name_dob_matches = await self._match_by_name_and_dob(patient_name, patient_dob)
            for match in name_dob_matches:
                score = self._compute_name_similarity(patient_name, match["name"])
                if score >= 0.7:
                    candidates.append({
                        "member_id": match["id"],
                        "name": match["name"],
                        "dob": match["dob"],
                        "match_score": score,
                        "match_signals": ["name_match", "dob_match"],
                    })

        if doctor_name and doc_date and doc_type and not candidates:
            contextual_matches = await self._match_by_context(doctor_name, doc_date, doc_type)
            for match in contextual_matches:
                candidates.append({
                    "member_id": match["member_id"],
                    "name": match.get("member_name", "Unknown"),
                    "dob": match.get("member_dob", "1900-01-01"),
                    "match_score": 0.5,
                    "match_signals": ["doctor_name_match", "date_proximity", "doc_type_match"],
                })

        candidates.sort(key=lambda c: c["match_score"], reverse=True)

        return candidates

    async def _match_by_mrn(self, mrn: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/family_members",
                headers=self._headers,
                params={"id": f"eq.{mrn}", "select": "id,name,dob"},
            )
            if response.status_code == 200:
                return response.json()
            return []

    async def _match_by_name_and_dob(self, name: str, dob: date) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/family_members",
                headers=self._headers,
                params={
                    "dob": f"eq.{dob.isoformat()}",
                    "select": "id,name,dob",
                },
            )
            if response.status_code == 200:
                return response.json()
            return []

    async def _match_by_context(
        self, doctor_name: str, doc_date: date, doc_type: str
    ) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/documents",
                headers=self._headers,
                params={
                    "doctor_name": f"ilike.%{doctor_name}%",
                    "doc_type": f"eq.{doc_type}",
                    "select": "member_id,member:family_members(name,dob)",
                    "limit": "5",
                },
            )
            if response.status_code == 200:
                results = response.json()
                flattened = []
                for r in results:
                    member = r.get("member", {})
                    if member:
                        flattened.append({
                            "member_id": r["member_id"],
                            "member_name": member.get("name", ""),
                            "member_dob": member.get("dob", ""),
                        })
                return flattened
            return []

    def _compute_name_similarity(self, name_a: str, name_b: str) -> float:
        a_tokens = set(name_a.lower().strip().split())
        b_tokens = set(name_b.lower().strip().split())

        if not a_tokens or not b_tokens:
            return 0.0

        intersection = a_tokens & b_tokens
        union = a_tokens | b_tokens

        jaccard = len(intersection) / len(union) if union else 0.0

        a_sorted = " ".join(sorted(a_tokens))
        b_sorted = " ".join(sorted(b_tokens))

        if a_sorted == b_sorted:
            return 1.0

        max_len = max(len(a_sorted), len(b_sorted))
        if max_len == 0:
            return 0.0

        distance = self._levenshtein_distance(a_sorted, b_sorted)
        levenshtein_similarity = 1.0 - (distance / max_len)

        return max(jaccard, levenshtein_similarity)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)

        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]


class UnlinkedQueueService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._queue: list[dict] = []

    async def add_to_queue(
        self,
        ingest_id: str,
        storage_path: str,
        doc_type: str,
        extractions: list[dict],
        ingest_channel: str,
        content_hash: str,
    ) -> None:
        entry = {
            "ingest_id": ingest_id,
            "storage_path": storage_path,
            "doc_type": doc_type,
            "extractions": extractions,
            "ingest_channel": ingest_channel,
            "content_hash": content_hash,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._queue.append(entry)

        logger.info(
            "added_to_unlinked_queue",
            ingest_id=ingest_id,
            doc_type=doc_type,
            queue_size=len(self._queue),
        )

    async def get_queue(self) -> list[dict]:
        return list(self._queue)

    async def remove_from_queue(self, ingest_id: str) -> Optional[dict]:
        for i, entry in enumerate(self._queue):
            if entry["ingest_id"] == ingest_id:
                removed = self._queue.pop(i)
                logger.info("removed_from_unlinked_queue", ingest_id=ingest_id)
                return removed
        return None

    async def link_document(self, ingest_id: str, member_id: UUID) -> Optional[str]:
        entry = await self.remove_from_queue(ingest_id)
        if not entry:
            logger.warning("link_failed_not_in_queue", ingest_id=ingest_id)
            return None

        logger.info(
            "document_linked_from_queue",
            ingest_id=ingest_id,
            member_id=str(member_id),
        )

        return ingest_id

    async def get_queue_size(self) -> int:
        return len(self._queue)
