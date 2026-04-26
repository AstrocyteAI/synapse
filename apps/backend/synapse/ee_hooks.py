"""EE integration hooks for the OSS distribution.

When the ee/ package is absent (OSS build), NullFeatureFlags is used so that
all is_enabled() calls return False without raising ImportError.

Rule: synapse/ code must never import from ee/ directly.  Always use the
objects obtained from app.state (feature_flags, license_service) that are
wired up in main.py's lifespan.
"""

from __future__ import annotations


class NullFeatureFlags:
    """Fallback used when the EE package is not installed.

    All feature checks return False — core council engine stays fully
    functional; EE features are simply unavailable.
    """

    def is_enabled(self, feature: str, tenant_id: str | None = None) -> bool:  # noqa: ARG002
        return False
