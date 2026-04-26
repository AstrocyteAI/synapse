"""Tests for the /v1/api-keys router."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import ApiKey
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
def admin_token():
    return make_jwt(sub="admin-1", tenant_id="tenant-test", roles=["admin"])


@pytest.fixture
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key(**kwargs) -> MagicMock:
    key_id = uuid.uuid4()
    defaults = dict(
        id=key_id,
        name="test-key",
        key_hash="abc123hash",
        key_prefix="sk-abcdefgh",
        created_by="user:user-1",
        tenant_id="tenant-test",
        roles=["member"],
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        last_used_at=None,
        revoked_at=None,
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=ApiKey)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# POST /v1/api-keys
# ---------------------------------------------------------------------------


def test_create_api_key_returns_201_with_raw_key(client, db_session, headers):
    """POST /v1/api-keys returns 201 with a raw key that starts with 'sk-'."""
    db_session.add = MagicMock()
    db_session.commit = AsyncMock()
    db_session.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = client.post(
        "/v1/api-keys",
        json={"name": "my-key"},
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-key"
    assert body["key"].startswith("sk-")
    assert body["key_prefix"].startswith("sk-")
    assert "key_hash" not in body
    assert body["roles"] == ["member"]


def test_create_api_key_requires_auth(client):
    resp = client.post("/v1/api-keys", json={"name": "k"})
    assert resp.status_code == 401


def test_create_api_key_non_admin_cannot_create_admin_key(client, headers, db_session):
    """A member-role user cannot create an admin-scoped key."""
    resp = client.post(
        "/v1/api-keys",
        json={"name": "admin-key", "roles": ["admin"]},
        headers=headers,
    )
    assert resp.status_code == 403


def test_create_api_key_admin_can_create_admin_key(client, admin_headers, db_session):
    """An admin user can create an admin-scoped key."""
    db_session.add = MagicMock()
    db_session.commit = AsyncMock()
    db_session.refresh = AsyncMock(side_effect=lambda obj: None)

    resp = client.post(
        "/v1/api-keys",
        json={"name": "admin-key", "roles": ["admin"]},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["roles"] == ["admin"]


# ---------------------------------------------------------------------------
# GET /v1/api-keys
# ---------------------------------------------------------------------------


def test_list_api_keys_returns_keys_without_raw_key(client, db_session, headers):
    """GET /v1/api-keys returns list; key_hash never appears in response."""
    mock_key = _make_api_key()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_key]
    db_session.execute = AsyncMock(return_value=mock_result)

    resp = client.get("/v1/api-keys", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["name"] == "test-key"
    assert "key_hash" not in body[0]
    assert "key" not in body[0]


def test_list_api_keys_requires_auth(client):
    resp = client.get("/v1/api-keys")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /v1/api-keys/{key_id}
# ---------------------------------------------------------------------------


def test_revoke_api_key_returns_204(client, db_session, headers):
    """DELETE /v1/api-keys/{id} sets revoked_at and returns 204."""
    key_id = uuid.uuid4()
    mock_key = _make_api_key(id=key_id, created_by="user:user-1", revoked_at=None)
    db_session.get = AsyncMock(return_value=mock_key)
    db_session.commit = AsyncMock()

    resp = client.delete(f"/v1/api-keys/{key_id}", headers=headers)

    assert resp.status_code == 204
    assert mock_key.revoked_at is not None


def test_revoke_api_key_404_when_not_found(client, db_session, headers):
    key_id = uuid.uuid4()
    db_session.get = AsyncMock(return_value=None)

    resp = client.delete(f"/v1/api-keys/{key_id}", headers=headers)

    assert resp.status_code == 404


def test_revoke_api_key_409_when_already_revoked(client, db_session, headers):
    key_id = uuid.uuid4()
    mock_key = _make_api_key(
        id=key_id,
        created_by="user:user-1",
        revoked_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    db_session.get = AsyncMock(return_value=mock_key)

    resp = client.delete(f"/v1/api-keys/{key_id}", headers=headers)

    assert resp.status_code == 409


def test_revoke_api_key_403_when_wrong_owner(client, db_session, headers):
    """Cannot revoke another user's key without admin role."""
    key_id = uuid.uuid4()
    mock_key = _make_api_key(
        id=key_id,
        created_by="user:other-user",
        tenant_id="tenant-test",
        revoked_at=None,
    )
    db_session.get = AsyncMock(return_value=mock_key)

    resp = client.delete(f"/v1/api-keys/{key_id}", headers=headers)

    assert resp.status_code == 403
