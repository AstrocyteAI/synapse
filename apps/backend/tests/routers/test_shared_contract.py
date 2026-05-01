"""Shared backend contract tests for Synapse EE."""

from __future__ import annotations

from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from synapse.main import create_app
from synapse.openapi_contract import load_contract
from tests.conftest import TEST_SETTINGS, make_jwt


def test_openapi_json_serves_canonical_contract():
    app = create_app()

    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json() == load_contract()


def test_shared_socket_token_endpoint_returns_centrifugo_descriptor():
    app = create_app()
    token = make_jwt(sub="user-1", tenant_id="tenant-test")

    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as client,
    ):
        response = client.get("/v1/socket/token", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["transport"] == "centrifugo"
    assert body["url"] == TEST_SETTINGS.centrifugo_ws_url
    assert body["expires_in"] == TEST_SETTINGS.centrifugo_token_ttl_seconds
    assert body["topics"] == {
        "council": "council:<council_id>",
        "thread": "thread:<thread_id>",
    }

    claims = jwt.decode(
        body["token"],
        TEST_SETTINGS.centrifugo_token_secret,
        algorithms=["HS256"],
    )
    assert claims["sub"] == "user-1"


def test_shared_contract_paths_are_present():
    paths = load_contract()["paths"]

    assert set(paths) >= {
        "/v1/councils",
        "/v1/councils/{id}/start",
        "/v1/socket/token",
        "/v1/memory/recall",
        "/v1/audit_logs",
        "/v1/mcp",
    }


def test_contract_declares_post_b10_endpoints():
    """Drift guard — every endpoint added in B10/B11/W9 must be declared.

    When you add a new public endpoint, append it here so the contract stays
    in sync with the implementation.
    """
    paths = load_contract()["paths"]

    expected = {
        # X-2 — backend metadata (public)
        "/v1/info",
        # B10 — notification preferences + devices (EE Team+)
        "/v1/notifications/preferences",
        "/v1/notifications/devices",
        "/v1/notifications/devices/{token_id}",
        # W9 — notification feed (free tier)
        "/v1/notifications/feed",
        # B11 — audit log (admin)
        "/v1/admin/audit-log",
    }
    missing = expected - set(paths)
    assert not missing, f"OpenAPI contract is missing: {sorted(missing)}"
