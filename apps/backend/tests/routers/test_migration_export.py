"""Tests for admin migration-export endpoints (X-4).

Covers:
  GET /v1/admin/api-keys              — metadata-only dump, admin-only
  GET /v1/admin/webhooks              — full dump inc. secrets, admin-only
  GET /v1/admin/notifications/preferences  — prefs dump, admin-only
  GET /v1/admin/notifications/devices      — device token dump, admin-only
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import ApiKey, DeviceToken, NotificationPreferences, Webhook
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def _wired_client():
    application = create_app()
    mock_session = AsyncMock()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sessionmaker.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(application, raise_server_exceptions=False) as c,
    ):
        application.state.sessionmaker = mock_sessionmaker
        yield c, mock_session


@pytest.fixture
def client(_wired_client):
    c, _ = _wired_client
    return c


@pytest.fixture
def db_session(_wired_client):
    _, session = _wired_client
    return session


def _admin_headers() -> dict:
    token = make_jwt(sub="admin-1", roles=["admin", "member"])
    return {"Authorization": f"Bearer {token}"}


def _admin_export_headers() -> dict:
    """Admin headers + the X-Migration-Export opt-in for /v1/admin/webhooks."""
    return {**_admin_headers(), "X-Migration-Export": "true"}


def _member_headers() -> dict:
    token = make_jwt(sub="user-1", roles=["member"])
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers — mock DB row factories
# ---------------------------------------------------------------------------


def _make_api_key(**kwargs) -> MagicMock:
    key_id = uuid.uuid4()
    defaults = dict(
        id=key_id,
        name="CI/CD pipeline",
        key_hash="abc123",
        key_prefix="sk-a1b2c3d4",
        created_by="user:alice",
        tenant_id="tenant-test",
        roles=["member"],
        created_at=datetime(2026, 3, 1, tzinfo=UTC),
        last_used_at=None,
        revoked_at=None,
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=ApiKey)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_webhook(**kwargs) -> MagicMock:
    wh_id = uuid.uuid4()
    defaults = dict(
        id=wh_id,
        url="https://hooks.example.com/synapse",
        events=["council.closed"],
        secret="whsec_test",
        active=True,
        created_by="user:alice",
        tenant_id="tenant-test",
        created_at=datetime(2026, 3, 10, tzinfo=UTC),
        last_delivery_at=None,
        failure_count=0,
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=Webhook)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_pref(**kwargs) -> MagicMock:
    pref_id = uuid.uuid4()
    defaults = dict(
        id=pref_id,
        principal="user:alice",
        tenant_id="tenant-test",
        email_enabled=True,
        email_address="alice@example.com",
        ntfy_enabled=False,
        updated_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=NotificationPreferences)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_device(**kwargs) -> MagicMock:
    device_id = uuid.uuid4()
    defaults = dict(
        id=device_id,
        principal="user:carol",
        tenant_id="tenant-test",
        token_type="ntfy",
        token="carol-alerts",
        device_label="Work laptop",
        created_at=datetime(2026, 4, 3, tzinfo=UTC),
        last_used_at=None,
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=DeviceToken)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# GET /v1/admin/api-keys
# ---------------------------------------------------------------------------


class TestAdminListApiKeys:
    def test_returns_200_with_key_list(self, client, db_session):
        key = _make_api_key()
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [key])))
        )

        resp = client.get("/v1/admin/api-keys", headers=_admin_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "CI/CD pipeline"
        assert body["data"][0]["key_prefix"] == "sk-a1b2c3d4"
        assert "key_hash" not in body["data"][0], "key_hash must never appear in export"
        assert "note" in body  # re-issuance guidance

    def test_returns_empty_list_when_no_keys(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get("/v1/admin/api-keys", headers=_admin_headers())
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_returns_403_for_non_admin(self, client):
        resp = client.get("/v1/admin/api-keys", headers=_member_headers())
        assert resp.status_code == 403

    def test_pagination_params_accepted(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get("/v1/admin/api-keys?limit=10&offset=20", headers=_admin_headers())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /v1/admin/webhooks
# ---------------------------------------------------------------------------


class TestAdminListWebhooks:
    def test_returns_200_with_webhook_list_including_secret(self, client, db_session):
        wh = _make_webhook()
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [wh])))
        )

        resp = client.get("/v1/admin/webhooks", headers=_admin_export_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        item = body["data"][0]
        assert item["url"] == "https://hooks.example.com/synapse"
        assert item["events"] == ["council.closed"]
        assert item["secret"] == "whsec_test"  # must be present for migration continuity
        assert item["active"] is True

    def test_returns_empty_list_when_no_webhooks(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get("/v1/admin/webhooks", headers=_admin_export_headers())
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_returns_403_for_non_admin(self, client):
        resp = client.get("/v1/admin/webhooks", headers=_member_headers())
        assert resp.status_code == 403

    def test_returns_403_when_migration_export_header_missing(self, client):
        # Even with the admin role the dump is gated on an explicit opt-in
        # header so a CSRF / clickjack from a logged-in admin browser
        # session can't trigger a full secret leak.
        resp = client.get("/v1/admin/webhooks", headers=_admin_headers())
        assert resp.status_code == 403
        assert "X-Migration-Export" in resp.json()["detail"]

    def test_returns_403_when_migration_export_header_wrong_value(self, client):
        headers = {**_admin_headers(), "X-Migration-Export": "yes"}
        resp = client.get("/v1/admin/webhooks", headers=headers)
        assert resp.status_code == 403

    def test_pagination_params_accepted(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get(
            "/v1/admin/webhooks?limit=50&offset=100", headers=_admin_export_headers()
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /v1/admin/notifications/preferences
# ---------------------------------------------------------------------------


class TestAdminListNotificationPrefs:
    def test_returns_200_with_prefs(self, client, db_session):
        pref = _make_pref()
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [pref])))
        )

        resp = client.get("/v1/admin/notifications/preferences", headers=_admin_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        item = body["data"][0]
        assert item["principal"] == "user:alice"
        assert item["email_enabled"] is True
        assert item["email_address"] == "alice@example.com"
        assert item["ntfy_enabled"] is False

    def test_returns_empty_list_when_no_prefs(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get("/v1/admin/notifications/preferences", headers=_admin_headers())
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_returns_403_for_non_admin(self, client):
        resp = client.get("/v1/admin/notifications/preferences", headers=_member_headers())
        assert resp.status_code == 403

    def test_pagination_params_accepted(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get(
            "/v1/admin/notifications/preferences?limit=25&offset=50",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /v1/admin/notifications/devices
# ---------------------------------------------------------------------------


class TestAdminListDeviceTokens:
    def test_returns_200_with_devices(self, client, db_session):
        device = _make_device()
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [device])))
        )

        resp = client.get("/v1/admin/notifications/devices", headers=_admin_headers())
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        item = body["data"][0]
        assert item["principal"] == "user:carol"
        assert item["token_type"] == "ntfy"
        assert item["token"] == "carol-alerts"
        assert item["device_label"] == "Work laptop"
        assert item["last_used_at"] is None

    def test_returns_empty_list_when_no_devices(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get("/v1/admin/notifications/devices", headers=_admin_headers())
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_returns_403_for_non_admin(self, client):
        resp = client.get("/v1/admin/notifications/devices", headers=_member_headers())
        assert resp.status_code == 403

    def test_pagination_params_accepted(self, client, db_session):
        db_session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=lambda: [])))
        )

        resp = client.get(
            "/v1/admin/notifications/devices?limit=200&offset=0",
            headers=_admin_headers(),
        )
        assert resp.status_code == 200
