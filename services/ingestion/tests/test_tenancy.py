import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.tenancy import (
    TenantContext,
    TenantTier,
    TenantIsolation,
    PermissionService,
    TIER_LIMITS,
)


class TestTenantContext:
    def test_free_tier_limits(self):
        ctx = TenantContext("t1", "a1", TenantTier.FREE, TenantIsolation.LOGICAL, "Personal")
        assert ctx.max_members == 5
        assert ctx.max_documents_per_month == 50
        assert ctx.storage_limit_gb == 1
        assert ctx.api_rate_limit == 30

    def test_clinic_tier_limits(self):
        ctx = TenantContext("t2", "a2", TenantTier.CLINIC, TenantIsolation.LOGICAL, "Clinic")
        assert ctx.max_members == 50
        assert ctx.max_documents_per_month == 500
        assert ctx.storage_limit_gb == 10

    def test_hospital_tier_limits(self):
        ctx = TenantContext("t3", "a3", TenantTier.HOSPITAL, TenantIsolation.LOGICAL, "Hospital")
        assert ctx.max_members == 500
        assert ctx.max_documents_per_month == 10000

    def test_enterprise_tier_unlimited(self):
        ctx = TenantContext("t4", "a4", TenantTier.ENTERPRISE, TenantIsolation.PHYSICAL, "Enterprise")
        assert ctx.max_members == -1
        assert ctx.max_documents_per_month == -1
        assert ctx.is_within_member_limit(999999) is True
        assert ctx.is_within_document_limit(999999) is True

    def test_free_tier_channel_restriction(self):
        ctx = TenantContext("t1", "a1", TenantTier.FREE, TenantIsolation.LOGICAL, "Personal")
        assert ctx.can_use_channel("upload") is True
        assert ctx.can_use_channel("pacs") is False
        assert ctx.can_use_channel("abdm") is False

    def test_enterprise_all_channels(self):
        ctx = TenantContext("t4", "a4", TenantTier.ENTERPRISE, TenantIsolation.PHYSICAL, "Enterprise")
        all_channels = ["upload", "email", "folder_watch", "fax", "scanner", "emr_ehr", "pacs", "hl7", "abdm"]
        for channel in all_channels:
            assert ctx.can_use_channel(channel) is True

    def test_clinic_partial_channels(self):
        ctx = TenantContext("t2", "a2", TenantTier.CLINIC, TenantIsolation.LOGICAL, "Clinic")
        assert ctx.can_use_channel("upload") is True
        assert ctx.can_use_channel("email") is True
        assert ctx.can_use_channel("folder_watch") is True
        assert ctx.can_use_channel("pacs") is False
        assert ctx.can_use_channel("hl7") is False

    def test_member_limit_boundary(self):
        ctx = TenantContext("t1", "a1", TenantTier.FREE, TenantIsolation.LOGICAL, "Personal")
        assert ctx.is_within_member_limit(4) is True
        assert ctx.is_within_member_limit(5) is False
        assert ctx.is_within_member_limit(6) is False

    def test_document_limit_boundary(self):
        ctx = TenantContext("t1", "a1", TenantTier.FREE, TenantIsolation.LOGICAL, "Personal")
        assert ctx.is_within_document_limit(49) is True
        assert ctx.is_within_document_limit(50) is False

    def test_uses_slots(self):
        ctx = TenantContext("t1", "a1", TenantTier.FREE, TenantIsolation.LOGICAL, "Personal")
        assert hasattr(ctx, "__slots__")
        import pytest
        with pytest.raises(AttributeError):
            ctx.arbitrary_attribute = "should_fail"


class TestPermissionService:
    def setup_method(self):
        self.service = PermissionService()

    def test_owner_has_all_permissions(self):
        all_actions = list(PermissionService.PERMISSION_MATRIX.keys())
        for action in all_actions:
            assert self.service.has_permission("owner", action) is True

    def test_viewer_limited(self):
        assert self.service.has_permission("viewer", "view_document") is True
        assert self.service.has_permission("viewer", "delete_document") is False
        assert self.service.has_permission("viewer", "execute_erasure") is False

    def test_patient_permissions(self):
        assert self.service.has_permission("patient", "ingest_document") is True
        assert self.service.has_permission("patient", "confirm_extraction") is True
        assert self.service.has_permission("patient", "manage_consent") is True
        assert self.service.has_permission("patient", "delete_document") is False

    def test_doctor_permissions(self):
        assert self.service.has_permission("doctor", "confirm_extraction") is True
        assert self.service.has_permission("doctor", "export_fhir") is True
        assert self.service.has_permission("doctor", "execute_erasure") is False

    def test_receptionist_permissions(self):
        assert self.service.has_permission("receptionist", "manage_members") is True
        assert self.service.has_permission("receptionist", "ingest_document") is True
        assert self.service.has_permission("receptionist", "delete_document") is False

    def test_get_permissions_for_role(self):
        viewer_perms = self.service.get_permissions("viewer")
        assert "view_document" in viewer_perms
        assert "delete_document" not in viewer_perms

    def test_role_hierarchy(self):
        assert self.service.get_role_level("owner") > self.service.get_role_level("admin")
        assert self.service.get_role_level("admin") > self.service.get_role_level("doctor")
        assert self.service.get_role_level("doctor") > self.service.get_role_level("nurse")
        assert self.service.get_role_level("nurse") > self.service.get_role_level("receptionist")
        assert self.service.get_role_level("receptionist") > self.service.get_role_level("patient")
        assert self.service.get_role_level("patient") > self.service.get_role_level("viewer")

    def test_escalation_allowed(self):
        assert self.service.can_escalate("owner", "admin") is True
        assert self.service.can_escalate("admin", "doctor") is True

    def test_escalation_denied(self):
        assert self.service.can_escalate("viewer", "owner") is False
        assert self.service.can_escalate("patient", "doctor") is False

    def test_same_level_escalation_denied(self):
        assert self.service.can_escalate("doctor", "doctor") is False

    def test_unknown_role(self):
        assert self.service.get_role_level("hacker") == 0
        assert self.service.has_permission("hacker", "view_document") is False

    def test_unknown_action(self):
        assert self.service.has_permission("owner", "launch_missiles") is False


class TestTierLimitsConsistency:
    def test_tiers_are_monotonically_increasing(self):
        tiers = [TenantTier.FREE, TenantTier.CLINIC, TenantTier.HOSPITAL, TenantTier.ENTERPRISE]
        for i in range(len(tiers) - 1):
            current = TIER_LIMITS[tiers[i]]
            next_tier = TIER_LIMITS[tiers[i + 1]]

            if current["members"] != -1 and next_tier["members"] != -1:
                assert next_tier["members"] >= current["members"]
            if current["documents_per_month"] != -1 and next_tier["documents_per_month"] != -1:
                assert next_tier["documents_per_month"] >= current["documents_per_month"]
            if current["storage_gb"] != -1 and next_tier["storage_gb"] != -1:
                assert next_tier["storage_gb"] >= current["storage_gb"]

    def test_channels_are_superset(self):
        tiers = [TenantTier.FREE, TenantTier.CLINIC, TenantTier.HOSPITAL, TenantTier.ENTERPRISE]
        for i in range(len(tiers) - 1):
            current_channels = set(TIER_LIMITS[tiers[i]]["channels"])
            next_channels = set(TIER_LIMITS[tiers[i + 1]]["channels"])
            assert current_channels.issubset(next_channels), f"{tiers[i]} channels not subset of {tiers[i+1]}"
