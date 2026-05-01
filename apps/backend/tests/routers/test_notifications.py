"""Tests for POST/GET/PUT/DELETE /v1/notifications/* endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import DeviceToken, NotificationPreferences
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def _wired_client(mock_astrocyte, mock_centrifugo):
    application = create_app()
    mock_session = AsyncMock()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sessionmaker.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(application, raise_server_exceptions=False) as c,
    ):
        application.state.astrocyte = mock_astrocyte
        application.state.centrifugo = mock_centrifugo
        application.state.sessionmaker = mock_sessionmaker
        yield c, mock_session, application


@pytest.fixture
def client(_wired_client):
    c, _, _ = _wired_client
    return c


@pytest.fixture
def db_session(_wired_client):
    _, session, _ = _wired_client
    return session


@pytest.fixture
def app(_wired_client):
    _, _, application = _wired_client
    return application


@pytest.fixture
def token():
    return make_jwt(sub="user-1", tenant_id="tenant-test")


@pytest.fixture
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enable_feature(app):
    app.state.feature_flags = MagicMock()
    app.state.feature_flags.is_enabled = MagicMock(return_value=True)


def _disable_feature(app):
    app.state.feature_flags = MagicMock()
    app.state.feature_flags.is_enabled = MagicMock(return_value=False)


def _make_prefs(principal: str = "user-1") -> MagicMock:
    p = MagicMock(spec=NotificationPreferences)
    p.principal = principal
    p.email_enabled = True
    p.email_address = "alice@example.com"
    p.ntfy_enabled = False
    from datetime import UTC, datetime

    p.updated_at = datetime.now(UTC)
    return p


def _make_device(token_id: uuid.UUID | None = None) -> MagicMock:
    d = MagicMock(spec=DeviceToken)
    d.id = token_id or uuid.uuid4()
    d.token_type = "ntfy"
    d.token = "my-topic"
    d.device_label = "Alice's phone"
    from datetime import UTC, datetime

    d.created_at = datetime.now(UTC)
    return d


# ===========================================================================
# EE feature gate
# ===========================================================================


def test_get_preferences_501_when_feature_disabled(_wired_client, headers):
    c, _, application = _wired_client
    _disable_feature(application)
    resp = c.get("/v1/notifications/preferences", headers=headers)
    assert resp.status_code == 501


def test_put_preferences_501_when_feature_disabled(_wired_client, headers):
    c, _, application = _wired_client
    _disable_feature(application)
    resp = c.put(
        "/v1/notifications/preferences",
        json={"email_enabled": True, "email_address": "a@b.com", "ntfy_enabled": False},
        headers=headers,
    )
    assert resp.status_code == 501


def test_post_device_501_when_feature_disabled(_wired_client, headers):
    c, _, application = _wired_client
    _disable_feature(application)
    resp = c.post(
        "/v1/notifications/devices",
        json={"token": "my-topic"},
        headers=headers,
    )
    assert resp.status_code == 501


# ===========================================================================
# Auth
# ===========================================================================


def test_get_preferences_requires_auth(client, app):
    _enable_feature(app)
    resp = client.get("/v1/notifications/preferences")
    assert resp.status_code == 401


def test_put_preferences_requires_auth(client, app):
    _enable_feature(app)
    resp = client.put(
        "/v1/notifications/preferences",
        json={"email_enabled": False, "ntfy_enabled": False},
    )
    assert resp.status_code == 401


# ===========================================================================
# GET /v1/notifications/preferences — no row → defaults
# ===========================================================================


def test_get_preferences_returns_defaults_when_no_row(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )

    resp = c.get("/v1/notifications/preferences", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email_enabled"] is False
    assert data["email_address"] is None
    assert data["ntfy_enabled"] is False


def test_get_preferences_returns_stored_values(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    prefs = _make_prefs()
    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=prefs))
    )

    resp = c.get("/v1/notifications/preferences", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email_enabled"] is True
    assert data["email_address"] == "alice@example.com"
    assert data["ntfy_enabled"] is False


# ===========================================================================
# PUT /v1/notifications/preferences
# ===========================================================================


def test_put_preferences_creates_row_when_none_exists(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    prefs = _make_prefs()
    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    db_session.commit = AsyncMock()
    db_session.refresh = AsyncMock(return_value=prefs)
    db_session.add = MagicMock()

    # After add+commit+refresh, the refreshed object is returned
    async def _refresh(obj):
        obj.email_enabled = True
        obj.email_address = "alice@example.com"
        obj.ntfy_enabled = False
        from datetime import UTC, datetime

        obj.updated_at = datetime.now(UTC)

    db_session.refresh = _refresh

    resp = c.put(
        "/v1/notifications/preferences",
        json={"email_enabled": True, "email_address": "alice@example.com", "ntfy_enabled": False},
        headers=headers,
    )
    assert resp.status_code == 200
    # add() is called twice: once for the NotificationPreferences row and
    # once for the AuditEvent row emitted by B11's audit helper.
    from synapse.db.models import AuditEvent, NotificationPreferences

    added_types = [type(call.args[0]) for call in db_session.add.call_args_list]
    assert NotificationPreferences in added_types
    assert AuditEvent in added_types
    db_session.commit.assert_awaited_once()


def test_put_preferences_updates_existing_row(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    prefs = _make_prefs()
    db_session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=prefs))
    )
    db_session.commit = AsyncMock()

    async def _refresh(obj):
        pass

    db_session.refresh = _refresh

    resp = c.put(
        "/v1/notifications/preferences",
        json={"email_enabled": False, "ntfy_enabled": True},
        headers=headers,
    )
    assert resp.status_code == 200
    db_session.commit.assert_awaited_once()


def test_put_preferences_validates_email(_wired_client, headers, app):
    c, _, application = _wired_client
    _enable_feature(application)
    resp = c.put(
        "/v1/notifications/preferences",
        json={"email_enabled": True, "email_address": "not-an-email", "ntfy_enabled": False},
        headers=headers,
    )
    assert resp.status_code == 422


# ===========================================================================
# POST /v1/notifications/devices
# ===========================================================================


def test_register_device_returns_201(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    db_session.commit = AsyncMock()
    db_session.add = MagicMock()

    device = _make_device()

    async def _refresh(obj):
        obj.id = device.id
        obj.token_type = "ntfy"
        obj.token = "my-topic"
        obj.device_label = "Alice's phone"
        from datetime import UTC, datetime

        obj.created_at = datetime.now(UTC)

    db_session.refresh = _refresh

    resp = c.post(
        "/v1/notifications/devices",
        json={"token": "my-topic", "device_label": "Alice's phone"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["token"] == "my-topic"
    assert data["token_type"] == "ntfy"


def test_register_device_validates_token_type(_wired_client, headers, app):
    c, _, application = _wired_client
    _enable_feature(application)
    resp = c.post(
        "/v1/notifications/devices",
        json={"token_type": "fcm", "token": "device-token"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_register_device_requires_token(_wired_client, headers, app):
    c, _, application = _wired_client
    _enable_feature(application)
    resp = c.post("/v1/notifications/devices", json={}, headers=headers)
    assert resp.status_code == 422


# ===========================================================================
# GET /v1/notifications/devices
# ===========================================================================


def test_list_devices_returns_empty(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    db_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )

    resp = c.get("/v1/notifications/devices", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


def test_list_devices_returns_registered(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    devices = [_make_device(), _make_device()]
    db_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=devices)))
        )
    )

    resp = c.get("/v1/notifications/devices", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 2


# ===========================================================================
# DELETE /v1/notifications/devices/{token_id}
# ===========================================================================


def test_delete_device_204(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    token_id = uuid.uuid4()
    device = _make_device(token_id)
    device.principal = "user:user-1"  # jwt.py sets principal = f"user:{sub}"
    device.tenant_id = "tenant-test"  # match the JWT tenant
    db_session.get = AsyncMock(return_value=device)
    db_session.delete = AsyncMock()
    db_session.commit = AsyncMock()

    resp = c.delete(f"/v1/notifications/devices/{token_id}", headers=headers)
    assert resp.status_code == 204
    db_session.delete.assert_awaited_once_with(device)


def test_delete_device_404_when_not_found(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    db_session.get = AsyncMock(return_value=None)

    resp = c.delete(f"/v1/notifications/devices/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


def test_delete_device_404_when_wrong_owner(_wired_client, headers, db_session):
    c, _, application = _wired_client
    _enable_feature(application)
    device = _make_device()
    device.principal = "user:other-user"
    db_session.get = AsyncMock(return_value=device)

    resp = c.delete(f"/v1/notifications/devices/{device.id}", headers=headers)
    assert resp.status_code == 404
