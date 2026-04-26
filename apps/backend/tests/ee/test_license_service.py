"""Tests for LicenseService (OSS/offline/online modes) and FeatureFlags."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

from dilithium_py.ml_dsa import ML_DSA_65

from ee.license.feature_flags import FeatureFlags
from ee.license.license_service import LicenseService
from ee.license.license_types import ENTERPRISE_FEATURES, OSS_FEATURES

# ---------------------------------------------------------------------------
# Helpers — build a valid signed offline key using ML-DSA-65
# ---------------------------------------------------------------------------


def _make_key_pair() -> tuple[bytes, str]:
    """Return (secret_key_bytes, public_key_b64)."""
    pk, sk = ML_DSA_65.keygen()
    return sk, base64.b64encode(pk).decode()


def _build_offline_key(sk: bytes, plan: str, expires_at: datetime) -> str:
    license_dict = {
        "plan": plan,
        "tenant_id": "test",
        "expires_at": expires_at.isoformat(),
    }
    license_json = json.dumps(license_dict, separators=(",", ":"), sort_keys=True)
    sig_bytes = ML_DSA_65.sign(sk, license_json.encode())
    payload = json.dumps({"license": license_json, "signature": sig_bytes.hex()})
    return base64.b64encode(payload.encode()).decode()


# ---------------------------------------------------------------------------
# OSS mode
# ---------------------------------------------------------------------------


def test_oss_mode_returns_oss_features():
    service = LicenseService()
    assert service.get_plan() == OSS_FEATURES
    assert service.get_plan("tenant-1") == OSS_FEATURES


# ---------------------------------------------------------------------------
# Offline mode — valid license
# ---------------------------------------------------------------------------


def test_offline_mode_valid_license_returns_features():
    sk, pk_b64 = _make_key_pair()
    expires_at = datetime.now(UTC) + timedelta(days=365)
    offline_key = _build_offline_key(sk, "enterprise", expires_at)

    service = LicenseService(
        license_key_offline=offline_key,
        public_key_b64=pk_b64,
    )
    service._offline_features = service._validate_offline_license()

    features = service.get_plan()
    assert features == ENTERPRISE_FEATURES


# ---------------------------------------------------------------------------
# Offline mode — expired license degrades to OSS
# ---------------------------------------------------------------------------


def test_offline_mode_expired_license_returns_oss():
    sk, pk_b64 = _make_key_pair()
    expired_at = datetime.now(UTC) - timedelta(days=1)
    offline_key = _build_offline_key(sk, "enterprise", expired_at)

    service = LicenseService(
        license_key_offline=offline_key,
        public_key_b64=pk_b64,
    )
    service._offline_features = service._validate_offline_license()

    assert service.get_plan() == OSS_FEATURES


# ---------------------------------------------------------------------------
# Offline mode — bad signature degrades to OSS
# ---------------------------------------------------------------------------


def test_offline_mode_invalid_signature_returns_oss():
    sk, pk_b64 = _make_key_pair()
    expires_at = datetime.now(UTC) + timedelta(days=365)
    offline_key = _build_offline_key(sk, "enterprise", expires_at)

    payload = json.loads(base64.b64decode(offline_key))
    payload["signature"] = "00" * 3309  # corrupt — correct length, garbage bytes
    tampered_key = base64.b64encode(json.dumps(payload).encode()).decode()

    service = LicenseService(
        license_key_offline=tampered_key,
        public_key_b64=pk_b64,
    )
    service._offline_features = service._validate_offline_license()

    assert service.get_plan() == OSS_FEATURES


# ---------------------------------------------------------------------------
# FeatureFlags
# ---------------------------------------------------------------------------


def test_feature_flags_is_enabled_true():
    sk, pk_b64 = _make_key_pair()
    expires_at = datetime.now(UTC) + timedelta(days=365)
    offline_key = _build_offline_key(sk, "enterprise", expires_at)

    service = LicenseService(license_key_offline=offline_key, public_key_b64=pk_b64)
    service._offline_features = service._validate_offline_license()

    flags = FeatureFlags(service)
    assert flags.is_enabled("notifications") is True


def test_feature_flags_is_enabled_false():
    service = LicenseService()
    flags = FeatureFlags(service)
    assert flags.is_enabled("notifications") is False


def test_feature_flags_unknown_feature_returns_false():
    service = LicenseService()
    flags = FeatureFlags(service)
    assert flags.is_enabled("turbo_boost_mode") is False
