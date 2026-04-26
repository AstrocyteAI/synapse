"""License types: FeatureSet and PlanTier."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class FeatureSet:
    """Boolean feature flags per license tier."""

    # Team+ features — EE platform
    notifications: bool = False
    audit_logs: bool = False
    # Team+ features — Memory UI
    mip_rule_editor: bool = False
    wiki_graph: bool = False
    # Team+ features — Knowledge Base
    object_storage: bool = False
    document_ingestion: bool = False
    # Business+ features
    advanced_rbac: bool = False
    multi_tenancy: bool = False
    saml_sso: bool = False
    admin_api: bool = False
    compliance: bool = False
    # Enterprise+ features
    scim: bool = False
    audit_log_streaming: bool = False
    cross_tenant_analytics: bool = False
    air_gapped_license: bool = False


class PlanTier(StrEnum):
    oss = "oss"
    team = "team"
    business = "business"
    enterprise = "enterprise"
    unlimited = "unlimited"


# ---------------------------------------------------------------------------
# Pre-built FeatureSets per tier
# ---------------------------------------------------------------------------

OSS_FEATURES = FeatureSet()

TEAM_FEATURES = FeatureSet(
    notifications=True,
    audit_logs=True,
    mip_rule_editor=True,
    wiki_graph=True,
    object_storage=True,
    document_ingestion=True,
)

BUSINESS_FEATURES = FeatureSet(
    # Team features
    notifications=True,
    audit_logs=True,
    mip_rule_editor=True,
    wiki_graph=True,
    object_storage=True,
    document_ingestion=True,
    # Business features
    advanced_rbac=True,
    multi_tenancy=True,
    saml_sso=True,
    admin_api=True,
    compliance=True,
)

ENTERPRISE_FEATURES = FeatureSet(
    # Team features
    notifications=True,
    audit_logs=True,
    mip_rule_editor=True,
    wiki_graph=True,
    object_storage=True,
    document_ingestion=True,
    # Business features
    advanced_rbac=True,
    multi_tenancy=True,
    saml_sso=True,
    admin_api=True,
    compliance=True,
    # Enterprise features
    scim=True,
    audit_log_streaming=True,
    cross_tenant_analytics=True,
    air_gapped_license=True,
)

UNLIMITED_FEATURES = FeatureSet(
    notifications=True,
    audit_logs=True,
    mip_rule_editor=True,
    wiki_graph=True,
    object_storage=True,
    document_ingestion=True,
    advanced_rbac=True,
    multi_tenancy=True,
    saml_sso=True,
    admin_api=True,
    compliance=True,
    scim=True,
    audit_log_streaming=True,
    cross_tenant_analytics=True,
    air_gapped_license=True,
)
