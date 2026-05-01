"""GET /v1/info — backend deployment metadata.

Public (no auth) endpoint that lets clients discover what kind of backend
they are talking to: Synapse single-tenant or Cerebro multi-tenant, plus
which features are licensed.

Web and mobile clients call this once at startup to:
- Pick the right login flow (multi-tenant clients show a tenant selector)
- Hide UI for unlicensed features
- Display the backend version in diagnostics

Response shape MUST stay identical between Synapse and Cerebro — this is the
foundational X-2 contract that lets clients be backend-agnostic.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["info"])


# ---------------------------------------------------------------------------
# Response schema — must match Cerebro's InfoController
# ---------------------------------------------------------------------------


class FeatureFlagsOut(BaseModel):
    notifications: bool
    audit_log: bool
    saml_sso: bool
    scim: bool
    compliance_ui: bool
    quotas: bool
    tenant_admin: bool


class BackendInfo(BaseModel):
    backend: str  # "synapse" | "cerebro"
    version: str
    contract_version: str  # "v1"
    multi_tenant: bool
    billing: bool
    features: FeatureFlagsOut


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def _read_feature(ff: Any, key: str) -> bool:
    """Safely query the feature_flags object — works with both NullFeatureFlags and EE FeatureFlags."""
    try:
        return bool(ff.is_enabled(key))
    except Exception:
        return False


@router.get(
    "/info",
    response_model=BackendInfo,
    summary="Backend deployment metadata (public)",
)
async def get_info(request: Request) -> BackendInfo:
    ff = getattr(request.app.state, "feature_flags", None)
    return BackendInfo(
        backend="synapse",
        version="0.1.0",
        contract_version="v1",
        # Synapse is single-tenant by design — always false.
        # See docs/_design/multi-tenancy.md for rationale.
        multi_tenant=False,
        billing=False,
        features=FeatureFlagsOut(
            notifications=_read_feature(ff, "notifications"),
            audit_log=_read_feature(ff, "audit_logs"),
            saml_sso=_read_feature(ff, "saml_sso"),
            scim=_read_feature(ff, "scim"),
            compliance_ui=_read_feature(ff, "compliance"),
            # Synapse never enforces quotas or runs a tenant admin panel —
            # those are Cerebro features. Reported as false unconditionally.
            quotas=False,
            tenant_admin=False,
        ),
    )
