"""Tests for license_fns — key detection, signature verification, feature mapping."""

from __future__ import annotations

import base64
import json

import pytest
from dilithium_py.ml_dsa import ML_DSA_65

from ee.license.license_fns import (
    get_default_features,
    get_features_for_plan,
    is_offline_license_key,
    verify_offline_license,
)
from ee.license.license_types import (
    BUSINESS_FEATURES,
    ENTERPRISE_FEATURES,
    OSS_FEATURES,
    TEAM_FEATURES,
    UNLIMITED_FEATURES,
)

# ---------------------------------------------------------------------------
# ML-DSA-65 key pair fixture — generated once per session
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ml_dsa_key_pair():
    """Generate a fresh ML-DSA-65 key pair for the test session."""
    pk, sk = ML_DSA_65.keygen()
    pk_b64 = base64.b64encode(pk).decode()
    return sk, pk_b64


@pytest.fixture(scope="session")
def signed_license(ml_dsa_key_pair):
    """Return (license_json, signature_hex, public_key_b64) for a valid test license."""
    sk, pk_b64 = ml_dsa_key_pair
    license_dict = {"plan": "enterprise", "tenant_id": "test"}
    license_json = json.dumps(license_dict, separators=(",", ":"), sort_keys=True)
    sig_bytes = ML_DSA_65.sign(sk, license_json.encode())
    return license_json, sig_bytes.hex(), pk_b64


# ---------------------------------------------------------------------------
# is_offline_license_key
# ---------------------------------------------------------------------------


def test_is_offline_license_key_valid():
    payload = json.dumps({"license": '{"plan":"team"}', "signature": "deadbeef"})
    key = base64.b64encode(payload.encode()).decode()
    assert is_offline_license_key(key) is True


def test_is_offline_license_key_invalid_not_base64():
    assert is_offline_license_key("not-base64!!!") is False


def test_is_offline_license_key_invalid_missing_fields():
    payload = json.dumps({"only_license": "value"})
    key = base64.b64encode(payload.encode()).decode()
    assert is_offline_license_key(key) is False


# ---------------------------------------------------------------------------
# verify_offline_license
# ---------------------------------------------------------------------------


def test_verify_offline_license_valid_signature(signed_license):
    license_json, signature_hex, pk_b64 = signed_license
    assert verify_offline_license(license_json, signature_hex, pk_b64) is True


def test_verify_offline_license_invalid_signature(signed_license):
    license_json, _, pk_b64 = signed_license
    bad_signature = "00" * 3309  # correct length but garbage bytes
    assert verify_offline_license(license_json, bad_signature, pk_b64) is False


# ---------------------------------------------------------------------------
# get_features_for_plan
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "plan,expected",
    [
        ("oss", OSS_FEATURES),
        ("team", TEAM_FEATURES),
        ("business", BUSINESS_FEATURES),
        ("enterprise", ENTERPRISE_FEATURES),
        ("unlimited", UNLIMITED_FEATURES),
    ],
)
def test_get_features_for_plan_known_plans(plan, expected):
    assert get_features_for_plan(plan) == expected


def test_get_features_for_plan_unknown_returns_oss():
    assert get_features_for_plan("galaxy_brain") == OSS_FEATURES


# ---------------------------------------------------------------------------
# get_default_features
# ---------------------------------------------------------------------------


def test_get_default_features_returns_oss():
    assert get_default_features() == OSS_FEATURES
