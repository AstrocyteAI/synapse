"""Pure functions for license key detection, verification, and feature mapping."""

from __future__ import annotations

import base64
import json

from ee.license.license_types import (
    BUSINESS_FEATURES,
    ENTERPRISE_FEATURES,
    OSS_FEATURES,
    TEAM_FEATURES,
    UNLIMITED_FEATURES,
    FeatureSet,
)


def is_offline_license_key(key: str) -> bool:
    """Return True if the key is a base64-encoded JSON with 'license' and 'signature' fields."""
    try:
        decoded = base64.b64decode(key).decode()
        parsed = json.loads(decoded)
        return "signature" in parsed and "license" in parsed
    except Exception:
        return False


def verify_offline_license(
    license_json: str,
    signature_hex: str,
    public_key_b64: str,
) -> bool:
    """Verify ML-DSA-65 (CRYSTALS-Dilithium3, FIPS 204 Level 3) signature.

    signature_hex  — hex-encoded raw ML-DSA-65 signature bytes.
    public_key_b64 — base64-encoded raw ML-DSA-65 public key bytes (1952 bytes).
    Returns True if valid, False on any error.
    """
    try:
        from dilithium_py.ml_dsa import ML_DSA_65

        public_key = base64.b64decode(public_key_b64)
        signature_bytes = bytes.fromhex(signature_hex)
        return ML_DSA_65.verify(public_key, license_json.encode(), signature_bytes)
    except Exception:
        return False


def get_features_for_plan(plan: str) -> FeatureSet:
    """Map plan string to FeatureSet. Unknown plan falls back to OSS_FEATURES."""
    mapping: dict[str, FeatureSet] = {
        "team": TEAM_FEATURES,
        "business": BUSINESS_FEATURES,
        "enterprise": ENTERPRISE_FEATURES,
        "unlimited": UNLIMITED_FEATURES,
        "oss": OSS_FEATURES,
    }
    return mapping.get(plan, OSS_FEATURES)


def get_default_features() -> FeatureSet:
    """Return OSS_FEATURES — all False. Used when no license key is set."""
    return OSS_FEATURES


# ---------------------------------------------------------------------------
# Offline license parsing helpers
# ---------------------------------------------------------------------------


def features_from_license_dict(license_dict: dict) -> FeatureSet:
    """Build a FeatureSet from the 'features' list in an offline license dict.

    The license may carry either:
    - a 'plan' key  → map to pre-built tier
    - a 'features' list → map each name to True on the FeatureSet

    Both keys are accepted; 'plan' takes priority when present.
    """
    if "plan" in license_dict:
        return get_features_for_plan(license_dict["plan"])

    feature_names: list[str] = license_dict.get("features", [])
    kwargs = {name: True for name in feature_names if hasattr(FeatureSet, name)}
    return FeatureSet(**kwargs)


__all__ = [
    "features_from_license_dict",
    "get_default_features",
    "get_features_for_plan",
    "is_offline_license_key",
    "verify_offline_license",
]
