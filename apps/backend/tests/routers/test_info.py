"""Tests for GET /v1/info — X-2 backend metadata endpoint."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from synapse.main import create_app
from tests.conftest import TEST_SETTINGS


def test_info_is_public_no_auth_required():
    app = create_app()
    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        resp = client.get("/v1/info")
    assert resp.status_code == 200


def test_info_reports_synapse_backend_single_tenant():
    """Synapse must always report backend=synapse, multi_tenant=false."""
    app = create_app()
    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        body = client.get("/v1/info").json()

    assert body["backend"] == "synapse"
    assert body["multi_tenant"] is False
    assert body["billing"] is False
    assert body["contract_version"] == "v1"


def test_info_reports_feature_flags():
    """Feature flags reflect what the deployment's license enables.

    With NullFeatureFlags (OSS), every flag must be false.
    quotas and tenant_admin are always false in Synapse — they're Cerebro features.
    """
    app = create_app()
    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        body = client.get("/v1/info").json()

    features = body["features"]
    expected_keys = {
        "notifications",
        "audit_log",
        "saml_sso",
        "scim",
        "compliance_ui",
        "quotas",
        "tenant_admin",
    }
    assert set(features.keys()) == expected_keys
    # Synapse never reports these as enabled — they're Cerebro features
    assert features["quotas"] is False
    assert features["tenant_admin"] is False


def test_info_response_shape_matches_contract():
    """Response shape must match the BackendInfo schema in the OpenAPI contract."""
    from synapse.openapi_contract import load_contract

    contract = load_contract()
    schema = contract["components"]["schemas"]["BackendInfo"]
    required = set(schema["required"])

    app = create_app()
    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        body = client.get("/v1/info").json()

    assert required <= set(body.keys()), (
        f"Response missing required fields: {required - set(body.keys())}"
    )
