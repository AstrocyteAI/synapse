"""Tests for the /v1/webhooks router."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import Webhook
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


@pytest.fixture
def token():
    return make_jwt(sub="user-1", tenant_id="tenant-test")


@pytest.fixture
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_webhook(**kwargs) -> MagicMock:
    wh_id = uuid.uuid4()
    defaults = dict(
        id=wh_id,
        url="https://example.com/webhook",
        events=["council_closed"],
        secret="test-secret",
        active=True,
        created_by="user:user-1",
        tenant_id="tenant-test",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_delivery_at=None,
        failure_count=0,
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=Webhook)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# POST /v1/webhooks
# ---------------------------------------------------------------------------


def test_create_webhook_returns_201_with_secret(client, db_session, headers):
    """POST /v1/webhooks returns 201 with the signing secret."""
    db_session.add = MagicMock()
    db_session.commit = AsyncMock()
    db_session.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = client.post(
        "/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["council_closed"]},
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["url"] == "https://example.com/hook"
    assert body["events"] == ["council_closed"]
    assert "secret" in body
    assert body["active"] is True


def test_create_webhook_accepts_custom_secret(client, db_session, headers):
    """User-provided secret is accepted and returned."""
    db_session.add = MagicMock()
    db_session.commit = AsyncMock()
    db_session.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = client.post(
        "/v1/webhooks",
        json={
            "url": "https://example.com/hook",
            "events": ["conflict_detected"],
            "secret": "my-custom-secret",
        },
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["secret"] == "my-custom-secret"


def test_create_webhook_rejects_invalid_event_type(client, headers):
    """POST /v1/webhooks returns 422 for unknown event types."""
    resp = client.post(
        "/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["unknown_event"]},
        headers=headers,
    )
    assert resp.status_code == 422


def test_create_webhook_rejects_empty_events(client, headers):
    resp = client.post(
        "/v1/webhooks",
        json={"url": "https://example.com/hook", "events": []},
        headers=headers,
    )
    assert resp.status_code == 422


def test_create_webhook_requires_auth(client):
    resp = client.post(
        "/v1/webhooks",
        json={"url": "https://example.com/hook", "events": ["council_closed"]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/webhooks
# ---------------------------------------------------------------------------


def test_list_webhooks_returns_registered_hooks(client, db_session, headers):
    """GET /v1/webhooks returns webhooks for the current user."""
    mock_wh = _make_webhook()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_wh]
    db_session.execute = AsyncMock(return_value=mock_result)

    resp = client.get("/v1/webhooks", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["url"] == "https://example.com/webhook"
    # Secret must never appear in list response
    assert "secret" not in body[0]


def test_list_webhooks_requires_auth(client):
    resp = client.get("/v1/webhooks")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /v1/webhooks/{wh_id}
# ---------------------------------------------------------------------------


def test_deactivate_webhook_returns_204(client, db_session, headers):
    """DELETE /v1/webhooks/{id} sets active=False and returns 204."""
    wh_id = uuid.uuid4()
    mock_wh = _make_webhook(id=wh_id, created_by="user:user-1", active=True)
    db_session.get = AsyncMock(return_value=mock_wh)
    db_session.commit = AsyncMock()

    resp = client.delete(f"/v1/webhooks/{wh_id}", headers=headers)

    assert resp.status_code == 204
    assert mock_wh.active is False


def test_deactivate_webhook_404_when_not_found(client, db_session, headers):
    wh_id = uuid.uuid4()
    db_session.get = AsyncMock(return_value=None)

    resp = client.delete(f"/v1/webhooks/{wh_id}", headers=headers)

    assert resp.status_code == 404


def test_deactivate_webhook_403_wrong_owner(client, db_session, headers):
    """Cannot deactivate another user's webhook without admin role."""
    wh_id = uuid.uuid4()
    mock_wh = _make_webhook(
        id=wh_id, created_by="user:other-user", tenant_id="tenant-test", active=True
    )
    db_session.get = AsyncMock(return_value=mock_wh)

    resp = client.delete(f"/v1/webhooks/{wh_id}", headers=headers)

    assert resp.status_code == 403
