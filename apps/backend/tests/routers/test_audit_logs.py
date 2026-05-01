"""Tests for GET /v1/admin/audit-log."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import AuditEvent
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
def admin_headers():
    token = make_jwt(sub="admin-1", tenant_id="tenant-test", roles=["admin"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_headers():
    token = make_jwt(sub="user-1", tenant_id="tenant-test", roles=["member"])
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_audit_event(
    event_id: int = 1,
    event_type: str = "council.created",
    actor_principal: str = "user:user-1",
    tenant_id: str | None = "tenant-test",
) -> MagicMock:
    e = MagicMock(spec=AuditEvent)
    e.id = event_id
    e.event_type = event_type
    e.actor_principal = actor_principal
    e.tenant_id = tenant_id
    e.resource_type = "council"
    e.resource_id = "c-abc"
    e.event_metadata = {"question_preview": "Should we refactor?"}
    e.created_at = datetime.now(UTC)
    return e


def _mock_events(db_session, events: list) -> None:
    db_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=events)))
        )
    )


# ===========================================================================
# Auth / role gate
# ===========================================================================


def test_requires_auth(client):
    resp = client.get("/v1/admin/audit-log")
    assert resp.status_code == 401


def test_requires_admin_role(client, member_headers, db_session):
    _mock_events(db_session, [])
    resp = client.get("/v1/admin/audit-log", headers=member_headers)
    assert resp.status_code == 403


# ===========================================================================
# GET /v1/admin/audit-log — list
# ===========================================================================


def test_returns_empty_list(client, admin_headers, db_session):
    _mock_events(db_session, [])
    resp = client.get("/v1/admin/audit-log", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["data"] == []
    assert body["next_before_id"] is None


def test_returns_events(client, admin_headers, db_session):
    events = [_make_audit_event(3), _make_audit_event(2), _make_audit_event(1)]
    _mock_events(db_session, events)
    resp = client.get("/v1/admin/audit-log", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert body["data"][0]["id"] == 3
    assert body["data"][0]["event_type"] == "council.created"
    assert body["data"][0]["metadata"] == {"question_preview": "Should we refactor?"}


def test_next_before_id_set_when_more_rows(client, admin_headers, db_session):
    # limit=2 + 1 extra row returned by DB signals more pages
    # We fake limit=2 by passing ?limit=2 and returning 3 rows
    events = [_make_audit_event(5), _make_audit_event(4), _make_audit_event(3)]
    _mock_events(db_session, events)
    resp = client.get("/v1/admin/audit-log?limit=2", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["next_before_id"] == 4  # last row in page (id of rows[:limit][-1])


def test_next_before_id_none_when_no_more(client, admin_headers, db_session):
    events = [_make_audit_event(2), _make_audit_event(1)]
    _mock_events(db_session, events)
    resp = client.get("/v1/admin/audit-log?limit=5", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["next_before_id"] is None


# ===========================================================================
# Query param validation
# ===========================================================================


def test_limit_must_be_at_least_1(client, admin_headers):
    resp = client.get("/v1/admin/audit-log?limit=0", headers=admin_headers)
    assert resp.status_code == 422


def test_limit_cannot_exceed_200(client, admin_headers):
    resp = client.get("/v1/admin/audit-log?limit=201", headers=admin_headers)
    assert resp.status_code == 422


def test_filters_forwarded_to_query(client, admin_headers, db_session):
    _mock_events(db_session, [])
    resp = client.get(
        "/v1/admin/audit-log?event_type=api_key.created&principal=user:admin-1&resource_type=api_key",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    # Just verify it doesn't blow up — actual SQL where-clause is in router
    db_session.execute.assert_called_once()


# ===========================================================================
# emit() helper unit tests
# ===========================================================================


@pytest.mark.asyncio
async def test_emit_adds_event_row():
    from synapse.audit import emit

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    await emit(
        db,
        "api_key.created",
        "user:alice",
        tenant_id="t1",
        resource_type="api_key",
        resource_id="key-1",
        metadata={"name": "my key"},
    )

    db.add.assert_called_once()
    event = db.add.call_args[0][0]
    assert event.event_type == "api_key.created"
    assert event.actor_principal == "user:alice"
    assert event.tenant_id == "t1"
    assert event.resource_type == "api_key"
    assert event.resource_id == "key-1"
    assert event.event_metadata == {"name": "my key"}
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_emit_swallows_exceptions():
    from synapse.audit import emit

    db = AsyncMock()
    db.add = MagicMock(side_effect=RuntimeError("db exploded"))

    # Must not raise
    await emit(db, "test.event", "user:x")
