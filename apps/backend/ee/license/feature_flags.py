"""FeatureFlags — thin wrapper that checks feature names against the active plan."""

from __future__ import annotations

from ee.license.license_service import LicenseService


class FeatureFlags:
    """Check whether a named EE feature is enabled for a tenant."""

    def __init__(self, license_service: LicenseService) -> None:
        self._service = license_service

    def is_enabled(self, feature: str, tenant_id: str | None = None) -> bool:
        """Return True if the feature is enabled for this tenant."""
        features = self._service.get_plan(tenant_id)
        return getattr(features, feature, False)
