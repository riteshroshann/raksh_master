from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class ConsentService:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def grant_consent(self, account_id: UUID, purpose: str) -> dict:
        existing = await self._get_active_consent(account_id, purpose)
        if existing:
            return existing

        consent_data = {
            "account_id": str(account_id),
            "purpose": purpose,
            "granted_at": datetime.utcnow().isoformat(),
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/consent_records",
                headers=self._headers,
                json=consent_data,
            )
            if response.status_code not in (200, 201):
                raise RuntimeError(f"Consent grant failed: {response.status_code}")

            record = response.json()[0]
            await self._audit_log("CONSENT_GRANTED", account_id, {"purpose": purpose, "consent_id": record["id"]})
            return record

    async def withdraw_consent(self, account_id: UUID, purpose: str, withdrawal_method: str) -> Optional[dict]:
        active = await self._get_active_consent(account_id, purpose)
        if not active:
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.patch(
                f"{self._base_url}/consent_records",
                headers=self._headers,
                params={"id": f"eq.{active['id']}"},
                json={"withdrawn_at": datetime.utcnow().isoformat(), "withdrawal_method": withdrawal_method},
            )
            if response.status_code not in (200, 204):
                raise RuntimeError(f"Consent withdrawal failed: {response.status_code}")

            await self._audit_log("CONSENT_WITHDRAWN", account_id, {"purpose": purpose, "consent_id": active["id"], "withdrawal_method": withdrawal_method})
            return active

    async def get_consents(self, account_id: UUID) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/consent_records",
                headers=self._headers,
                params={"account_id": f"eq.{str(account_id)}", "order": "created_at.desc"},
            )
            if response.status_code == 200:
                return response.json()
            return []

    async def has_active_consent(self, account_id: UUID, purpose: str) -> bool:
        return (await self._get_active_consent(account_id, purpose)) is not None

    async def execute_erasure(self, account_id: UUID) -> dict:
        await self._audit_log("RIGHT_TO_ERASURE_INITIATED", account_id, {"initiated_at": datetime.utcnow().isoformat()})

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._base_url}/rpc/execute_right_to_erasure",
                headers=self._headers,
                json={"p_account_id": str(account_id)},
            )
            if response.status_code not in (200, 204):
                raise RuntimeError(f"Erasure execution failed: {response.status_code}")

        logger.info("right_to_erasure_executed", account_id=str(account_id))
        return {"status": "completed", "account_id": str(account_id), "erased_at": datetime.utcnow().isoformat()}

    async def _get_active_consent(self, account_id: UUID, purpose: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/consent_records",
                headers=self._headers,
                params={"account_id": f"eq.{str(account_id)}", "purpose": f"eq.{purpose}", "withdrawn_at": "is.null", "limit": "1"},
            )
            if response.status_code == 200:
                results = response.json()
                return results[0] if results else None
            return None

    async def _audit_log(self, event: str, account_id: UUID, details: Optional[dict] = None) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{self._base_url}/audit_log",
                headers=self._headers,
                json={"event": event, "account_id": str(account_id), "details": details},
            )
