"""Tests for FeatureSet pre-built tier constants and PlanTier enum."""

from __future__ import annotations

from dataclasses import fields

import pytest

from ee.license.license_types import (
    BUSINESS_FEATURES,
    ENTERPRISE_FEATURES,
    OSS_FEATURES,
    TEAM_FEATURES,
    UNLIMITED_FEATURES,
    FeatureSet,
    PlanTier,
)


def _all_feature_names() -> list[str]:
    return [f.name for f in fields(FeatureSet)]


def test_oss_features_all_false():
    for name in _all_feature_names():
        assert getattr(OSS_FEATURES, name) is False, f"{name} should be False in OSS tier"


def test_team_features_notifications_true():
    assert TEAM_FEATURES.notifications is True


def test_business_features_includes_team():
    team_flags = {name for name in _all_feature_names() if getattr(TEAM_FEATURES, name)}
    for flag in team_flags:
        assert getattr(BUSINESS_FEATURES, flag) is True, (
            f"BUSINESS_FEATURES missing Team flag: {flag}"
        )
    # Business-only flags
    assert BUSINESS_FEATURES.advanced_rbac is True
    assert BUSINESS_FEATURES.saml_sso is True


def test_enterprise_features_includes_business():
    business_flags = {name for name in _all_feature_names() if getattr(BUSINESS_FEATURES, name)}
    for flag in business_flags:
        assert getattr(ENTERPRISE_FEATURES, flag) is True, (
            f"ENTERPRISE_FEATURES missing Business flag: {flag}"
        )
    # Enterprise-only flags
    assert ENTERPRISE_FEATURES.scim is True
    assert ENTERPRISE_FEATURES.air_gapped_license is True


def test_unlimited_features_all_true():
    for name in _all_feature_names():
        assert getattr(UNLIMITED_FEATURES, name) is True, f"{name} should be True in Unlimited tier"


@pytest.mark.parametrize("tier", list(PlanTier))
def test_plan_tier_values_are_strings(tier):
    assert isinstance(tier.value, str)
