"""Tests for the /v1/threads router."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import ThreadEventType
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thread(thread_id: uuid.UUID, tenant_id: str = "tenant-test") -> MagicMock:
    t = MagicMock()
    t.id = thread_id
    t.tenant_id = tenant_id
    t.council_id = None
    t.created_by = "user:test-1"
    t.title = "Test thread"
    return t


def _make_event(
    id: int,
    thread_id: uuid.UUID,
    event_type: str = ThreadEventType.user_message,
    actor_id: str = "user:test-1",
    actor_name: str = "Test User",
    content: str = "Hello",
    metadata: dict | None = None,
) -> MagicMock:
    e = MagicMock()
    e.id = id
    e.thread_id = thread_id
    e.event_type = event_type
    e.actor_id = actor_id
    e.actor_name = actor_name
    e.content = content
    e.metadata = metadata or {}
    e.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return e


# ---------------------------------------------------------------------------
# App fixture — fully mocked, no real DB
# ---------------------------------------------------------------------------


@pytest.fixture
def _wired_client():
    """App + TestClient with mocks applied *after* lifespan runs.

    Lifespan overwrites app.state — we must patch synapse.main.get_settings so
    it uses TEST_SETTINGS, then override sessionmaker after the lifespan yields.
    """
    application = create_app()
    mock_session = AsyncMock()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sessionmaker.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(application, raise_server_exceptions=False) as c,
    ):
        # Lifespan has run with TEST_SETTINGS — now inject test doubles
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
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /v1/threads/{thread_id}/messages
# ---------------------------------------------------------------------------


class TestSendMessage:
    def test_send_message_returns_201(self, client, db_session, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        event = _make_event(id=1, thread_id=thread_id, content="What should we do?")

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.append_event", AsyncMock(return_value=event)),
        ):
            resp = client.post(
                f"/v1/threads/{thread_id}/messages",
                json={"content": "What should we do?"},
                headers=auth_headers,
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["content"] == "What should we do?"
        assert body["event_type"] == ThreadEventType.user_message
        assert body["actor_id"] == "user:test-1"

    def test_send_message_appends_correct_fields(self, client, db_session, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        event = _make_event(id=5, thread_id=thread_id, content="Another message")

        append_mock = AsyncMock(return_value=event)
        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.append_event", append_mock),
        ):
            client.post(
                f"/v1/threads/{thread_id}/messages",
                json={"content": "Another message"},
                headers=auth_headers,
            )

        append_mock.assert_called_once()
        kwargs = append_mock.call_args.kwargs
        assert kwargs["thread_id"] == thread_id
        assert kwargs["event_type"] == ThreadEventType.user_message
        assert kwargs["content"] == "Another message"

    def test_send_message_404_when_thread_missing(self, client, auth_headers):
        thread_id = uuid.uuid4()
        with patch("synapse.routers.threads.get_thread", AsyncMock(return_value=None)):
            resp = client.post(
                f"/v1/threads/{thread_id}/messages",
                json={"content": "Hello"},
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_send_message_403_wrong_tenant(self, client, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id, tenant_id="other-tenant")
        event = _make_event(id=1, thread_id=thread_id)

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.append_event", AsyncMock(return_value=event)),
        ):
            resp = client.post(
                f"/v1/threads/{thread_id}/messages",
                json={"content": "Hello"},
                headers=auth_headers,
            )
        assert resp.status_code == 403

    def test_send_message_401_when_unauthenticated(self, client):
        resp = client.post(
            f"/v1/threads/{uuid.uuid4()}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 401

    def test_send_message_admin_can_access_any_tenant(self, client, auth_headers):
        """Admin role bypasses tenant check."""
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id, tenant_id="different-tenant")
        event = _make_event(id=1, thread_id=thread_id)
        admin_token = make_jwt(sub="admin-1", tenant_id="tenant-admin", roles=["admin"])

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.append_event", AsyncMock(return_value=event)),
        ):
            resp = client.post(
                f"/v1/threads/{thread_id}/messages",
                json={"content": "Admin message"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# GET /v1/threads/{thread_id}/events
# ---------------------------------------------------------------------------


class TestListEvents:
    def test_list_events_returns_events(self, client, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        events = [_make_event(i, thread_id, content=f"msg {i}") for i in range(1, 4)]

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", AsyncMock(return_value=events)),
        ):
            resp = client.get(f"/v1/threads/{thread_id}/events", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["thread_id"] == str(thread_id)
        assert body["count"] == 3
        assert len(body["events"]) == 3

    def test_list_events_passes_before_id(self, client, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        history_mock = AsyncMock(return_value=[])

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", history_mock),
        ):
            client.get(
                f"/v1/threads/{thread_id}/events?before_id=50",
                headers=auth_headers,
            )

        kwargs = history_mock.call_args.kwargs
        assert kwargs["before_id"] == 50
        assert kwargs.get("after_id") is None

    def test_list_events_passes_after_id(self, client, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        history_mock = AsyncMock(return_value=[])

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", history_mock),
        ):
            client.get(
                f"/v1/threads/{thread_id}/events?after_id=20",
                headers=auth_headers,
            )

        kwargs = history_mock.call_args.kwargs
        assert kwargs["after_id"] == 20
        assert kwargs.get("before_id") is None

    def test_list_events_passes_limit(self, client, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        history_mock = AsyncMock(return_value=[])

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", history_mock),
        ):
            client.get(
                f"/v1/threads/{thread_id}/events?limit=25",
                headers=auth_headers,
            )

        kwargs = history_mock.call_args.kwargs
        assert kwargs["limit"] == 25

    def test_list_events_next_before_id_set_when_no_cursor(self, client, auth_headers):
        """next_before_id is the oldest event id in the page — use it as the next before_id cursor."""
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        # Events returned newest-first (DESC): ids 10, 9, 8
        events = [_make_event(i, thread_id) for i in range(10, 7, -1)]

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", AsyncMock(return_value=events)),
        ):
            resp = client.get(f"/v1/threads/{thread_id}/events", headers=auth_headers)

        body = resp.json()
        assert body["next_before_id"] == 8  # items[-1] — oldest id on page

    def test_list_events_next_before_id_null_when_before_id_given(self, client, auth_headers):
        """next_before_id is None when the client already supplied before_id."""
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        events = [_make_event(i, thread_id) for i in range(5, 2, -1)]

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", AsyncMock(return_value=events)),
        ):
            resp = client.get(
                f"/v1/threads/{thread_id}/events?before_id=10",
                headers=auth_headers,
            )

        assert resp.json()["next_before_id"] is None

    def test_list_events_limit_too_low_returns_422(self, client, auth_headers):
        thread_id = uuid.uuid4()
        with patch(
            "synapse.routers.threads.get_thread", AsyncMock(return_value=_make_thread(thread_id))
        ):
            resp = client.get(
                f"/v1/threads/{thread_id}/events?limit=0",
                headers=auth_headers,
            )
        assert resp.status_code == 422

    def test_list_events_limit_too_high_returns_422(self, client, auth_headers):
        thread_id = uuid.uuid4()
        with patch(
            "synapse.routers.threads.get_thread", AsyncMock(return_value=_make_thread(thread_id))
        ):
            resp = client.get(
                f"/v1/threads/{thread_id}/events?limit=201",
                headers=auth_headers,
            )
        assert resp.status_code == 422

    def test_list_events_404_when_thread_missing(self, client, auth_headers):
        with patch("synapse.routers.threads.get_thread", AsyncMock(return_value=None)):
            resp = client.get(
                f"/v1/threads/{uuid.uuid4()}/events",
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_list_events_403_wrong_tenant(self, client, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id, tenant_id="other-tenant")

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", AsyncMock(return_value=[])),
        ):
            resp = client.get(f"/v1/threads/{thread_id}/events", headers=auth_headers)
        assert resp.status_code == 403

    def test_list_events_empty_thread(self, client, auth_headers):
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", AsyncMock(return_value=[])),
        ):
            resp = client.get(f"/v1/threads/{thread_id}/events", headers=auth_headers)

        body = resp.json()
        assert body["count"] == 0
        assert body["events"] == []
        assert body["next_before_id"] is None

    def test_list_events_event_shape(self, client, auth_headers):
        """Each event dict must contain all required fields."""
        thread_id = uuid.uuid4()
        thread = _make_thread(thread_id)
        events = [_make_event(1, thread_id, content="Test content")]

        with (
            patch("synapse.routers.threads.get_thread", AsyncMock(return_value=thread)),
            patch("synapse.routers.threads.get_history", AsyncMock(return_value=events)),
        ):
            resp = client.get(f"/v1/threads/{thread_id}/events", headers=auth_headers)

        event = resp.json()["events"][0]
        assert set(event.keys()) >= {
            "id",
            "thread_id",
            "event_type",
            "actor_id",
            "actor_name",
            "content",
            "metadata",
            "created_at",
        }
        assert event["content"] == "Test content"
        assert event["thread_id"] == str(thread_id)
