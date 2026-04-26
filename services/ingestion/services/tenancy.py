from datetime import datetime
from typing import Optional
from uuid import uuid4
from enum import Enum

import httpx
import structlog

from config import settings

logger = structlog.get_logger()


class TenantIsolation(str, Enum):
    PHYSICAL = "physical"
    LOGICAL = "logical"


class TenantTier(str, Enum):
    FREE = "free"
    CLINIC = "clinic"
    HOSPITAL = "hospital"
    ENTERPRISE = "enterprise"


TIER_LIMITS = {
    TenantTier.FREE: {"members": 5, "documents_per_month": 50, "storage_gb": 1, "api_rpm": 30, "channels": ["upload"]},
    TenantTier.CLINIC: {"members": 50, "documents_per_month": 500, "storage_gb": 10, "api_rpm": 120, "channels": ["upload", "email", "folder_watch"]},
    TenantTier.HOSPITAL: {"members": 500, "documents_per_month": 10000, "storage_gb": 100, "api_rpm": 600, "channels": ["upload", "email", "folder_watch", "fax", "emr_ehr", "hl7"]},
    TenantTier.ENTERPRISE: {"members": -1, "documents_per_month": -1, "storage_gb": -1, "api_rpm": -1, "channels": ["upload", "email", "folder_watch", "fax", "scanner", "emr_ehr", "pacs", "hl7", "abdm"]},
}


class TenantContext:
    __slots__ = ("tenant_id", "account_id", "tier", "isolation", "display_name", "region", "created_at", "_limits")

    def __init__(self, tenant_id: str, account_id: str, tier: TenantTier, isolation: TenantIsolation, display_name: str, region: str = "ap-south-1"):
        self.tenant_id = tenant_id
        self.account_id = account_id
        self.tier = tier
        self.isolation = isolation
        self.display_name = display_name
        self.region = region
        self.created_at = datetime.utcnow()
        self._limits = TIER_LIMITS[tier]

    @property
    def max_members(self) -> int:
        return self._limits["members"]

    @property
    def max_documents_per_month(self) -> int:
        return self._limits["documents_per_month"]

    @property
    def storage_limit_gb(self) -> int:
        return self._limits["storage_gb"]

    @property
    def api_rate_limit(self) -> int:
        return self._limits["api_rpm"]

    @property
    def allowed_channels(self) -> list[str]:
        return self._limits["channels"]

    def can_use_channel(self, channel: str) -> bool:
        if self._limits["members"] == -1:
            return True
        return channel in self._limits["channels"]

    def is_within_member_limit(self, current_count: int) -> bool:
        if self._limits["members"] == -1:
            return True
        return current_count < self._limits["members"]

    def is_within_document_limit(self, current_count: int) -> bool:
        if self._limits["documents_per_month"] == -1:
            return True
        return current_count < self._limits["documents_per_month"]


class TenantRegistry:
    def __init__(self):
        self._base_url = f"{settings.supabase_url}/rest/v1"
        self._headers = {
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "apikey": settings.supabase_service_role_key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._cache: dict[str, TenantContext] = {}

    async def resolve_tenant(self, account_id: str) -> Optional[TenantContext]:
        if account_id in self._cache:
            return self._cache[account_id]

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self._base_url}/tenants",
                headers=self._headers,
                params={"account_id": f"eq.{account_id}", "limit": "1"},
            )

            if response.status_code == 200:
                rows = response.json()
                if rows:
                    row = rows[0]
                    ctx = TenantContext(
                        tenant_id=row["id"],
                        account_id=account_id,
                        tier=TenantTier(row.get("tier", "free")),
                        isolation=TenantIsolation(row.get("isolation", "logical")),
                        display_name=row.get("display_name", ""),
                        region=row.get("region", "ap-south-1"),
                    )
                    self._cache[account_id] = ctx
                    return ctx

        return self._create_default_tenant(account_id)

    def _create_default_tenant(self, account_id: str) -> TenantContext:
        ctx = TenantContext(
            tenant_id=str(uuid4()),
            account_id=account_id,
            tier=TenantTier.FREE,
            isolation=TenantIsolation.LOGICAL,
            display_name="Personal",
        )
        self._cache[account_id] = ctx
        return ctx

    async def upgrade_tier(self, tenant_id: str, new_tier: TenantTier) -> bool:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.patch(
                f"{self._base_url}/tenants",
                headers=self._headers,
                params={"id": f"eq.{tenant_id}"},
                json={"tier": new_tier.value, "updated_at": datetime.utcnow().isoformat()},
            )

            if response.status_code == 200:
                for key, ctx in self._cache.items():
                    if ctx.tenant_id == tenant_id:
                        del self._cache[key]
                        break
                return True

        return False

    async def get_usage(self, tenant_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            members_resp = await client.get(
                f"{self._base_url}/family_members",
                headers={**self._headers, "Prefer": "count=exact"},
                params={"account_id": f"eq.{tenant_id}", "select": "id", "limit": "0"},
            )

            docs_resp = await client.get(
                f"{self._base_url}/documents",
                headers={**self._headers, "Prefer": "count=exact"},
                params={"select": "id", "limit": "0"},
            )

            member_count = 0
            doc_count = 0

            if members_resp.status_code == 200:
                content_range = members_resp.headers.get("content-range", "")
                if "/" in content_range:
                    member_count = int(content_range.split("/")[1])

            if docs_resp.status_code == 200:
                content_range = docs_resp.headers.get("content-range", "")
                if "/" in content_range:
                    doc_count = int(content_range.split("/")[1])

            return {
                "tenant_id": tenant_id,
                "member_count": member_count,
                "document_count_this_month": doc_count,
                "timestamp": datetime.utcnow().isoformat(),
            }

    def invalidate_cache(self, account_id: str) -> None:
        self._cache.pop(account_id, None)

    def clear_cache(self) -> None:
        self._cache.clear()


class PermissionService:
    ROLE_HIERARCHY = {
        "owner": 100,
        "admin": 80,
        "doctor": 60,
        "nurse": 40,
        "receptionist": 20,
        "patient": 10,
        "viewer": 5,
    }

    PERMISSION_MATRIX = {
        "ingest_document": {"owner", "admin", "doctor", "nurse", "receptionist", "patient"},
        "view_document": {"owner", "admin", "doctor", "nurse", "receptionist", "patient", "viewer"},
        "confirm_extraction": {"owner", "admin", "doctor", "patient"},
        "edit_parameters": {"owner", "admin", "doctor", "patient"},
        "delete_document": {"owner", "admin"},
        "manage_members": {"owner", "admin", "receptionist"},
        "view_audit_log": {"owner", "admin"},
        "manage_consent": {"owner", "patient"},
        "execute_erasure": {"owner"},
        "manage_billing": {"owner", "admin"},
        "configure_channels": {"owner", "admin"},
        "view_metrics": {"owner", "admin", "doctor"},
        "export_fhir": {"owner", "admin", "doctor"},
        "link_abdm": {"owner", "admin", "patient"},
    }

    def has_permission(self, role: str, action: str) -> bool:
        allowed_roles = self.PERMISSION_MATRIX.get(action, set())
        return role in allowed_roles

    def get_permissions(self, role: str) -> list[str]:
        return [action for action, roles in self.PERMISSION_MATRIX.items() if role in roles]

    def get_role_level(self, role: str) -> int:
        return self.ROLE_HIERARCHY.get(role, 0)

    def can_escalate(self, current_role: str, target_role: str) -> bool:
        return self.get_role_level(current_role) > self.get_role_level(target_role)


tenant_registry = TenantRegistry()
permission_service = PermissionService()
