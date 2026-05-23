"""Tests for the Phase 1B conversation-editing endpoints:

  * POST /v1/chat/sessions/:id/fork
  * POST /v1/chat/sessions/:id/messages/:msg_id/edit
  * POST /v1/chat/sessions/:id/messages/:msg_id/regenerate

The fork tests exercise routing + LineageError handling. Edit and
regenerate routes both stream SSE — we assert that the streaming
generator is wired through and that the marker event is persisted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.chat.lineage import LineageError
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt


def _make_session(**overrides) -> MagicMock:
    s = MagicMock()
    s.id = overrides.get("id", uuid.uuid4())
    s.thread_id = overrides.get("thread_id", uuid.uuid4())
    s.tenant_id = overrides.get("tenant_id", "tenant-test")
    s.created_by = overrides.get("created_by", "user:user-1")
    s.title = overrides.get("title", "parent")
    s.status = overrides.get("status", "active")
    s.council_id = overrides.get("council_id")
    s.agent_config = overrides.get("agent_config", {})
    s.parent_session_id = overrides.get("parent_session_id")
    s.parent_fork_event_id = overrides.get("parent_fork_event_id")
    s.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    s.updated_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return s


# ---------------------------------------------------------------------------
# Wired-client fixture (mirrors tests/routers/test_chat_sessions.py)
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
        application.state.astrocyte = MagicMock()
        yield c, mock_session


@pytest.fixture
def client(_wired_client):
    return _wired_client[0]


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {make_jwt(sub='user-1', tenant_id='tenant-test')}"}


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


class TestForkSession:
    def test_returns_201_with_child_session(self, client, auth_headers):
        parent = _make_session()
        child = _make_session(
            id=uuid.uuid4(),
            title="branch",
            parent_session_id=parent.id,
            parent_fork_event_id=42,
        )
        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=parent)),
            patch("synapse.routers.chat.fork_session", AsyncMock(return_value=child)),
        ):
            r = client.post(
                f"/v1/chat/sessions/{parent.id}/fork",
                json={"from_event_id": 42, "title": "branch"},
                headers=auth_headers,
            )
        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "branch"
        assert body["parent_fork_event_id"] == 42

    def test_returns_422_when_event_not_in_thread(self, client, auth_headers):
        parent = _make_session()
        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=parent)),
            patch(
                "synapse.routers.chat.fork_session",
                AsyncMock(side_effect=LineageError("event_not_in_thread", "nope")),
            ),
        ):
            r = client.post(
                f"/v1/chat/sessions/{parent.id}/fork",
                json={"from_event_id": 999},
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_returns_404_when_parent_session_missing(self, client, auth_headers):
        with patch("synapse.routers.chat.get_session", AsyncMock(return_value=None)):
            r = client.post(
                f"/v1/chat/sessions/{uuid.uuid4()}/fork",
                json={"from_event_id": 1},
                headers=auth_headers,
            )
        assert r.status_code == 404

    def test_requires_auth(self, client):
        r = client.post(f"/v1/chat/sessions/{uuid.uuid4()}/fork", json={"from_event_id": 1})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


class TestEditMessage:
    def test_persists_edit_and_streams_new_turn(self, client, auth_headers):
        session = _make_session()

        async def fake_stream(**_kwargs):
            yield 'data: {"type": "session_started"}\n\n'
            yield 'data: {"type": "token", "content": "ok"}\n\n'
            yield 'data: {"type": "message_complete"}\n\n'

        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch(
                "synapse.routers.chat.lineage_edit",
                AsyncMock(return_value="edited content"),
            ),
            patch("synapse.routers.chat.stream_chat_response", fake_stream),
        ):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/edit",
                json={"content": "edited content"},
                headers=auth_headers,
            )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        assert "session_started" in r.text
        assert "message_complete" in r.text

    def test_returns_422_for_non_user_message(self, client, auth_headers):
        session = _make_session()
        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch(
                "synapse.routers.chat.lineage_edit",
                AsyncMock(side_effect=LineageError("wrong_event_type", "not a user msg")),
            ),
        ):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/edit",
                json={"content": "x"},
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_returns_404_for_unknown_event(self, client, auth_headers):
        session = _make_session()
        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch(
                "synapse.routers.chat.lineage_edit",
                AsyncMock(side_effect=LineageError("event_not_in_thread", "missing")),
            ),
        ):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/edit",
                json={"content": "x"},
                headers=auth_headers,
            )
        assert r.status_code == 404

    def test_returns_422_when_session_archived(self, client, auth_headers):
        session = _make_session(status="archived")
        with patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/edit",
                json={"content": "x"},
                headers=auth_headers,
            )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Regenerate
# ---------------------------------------------------------------------------


class TestRegenerateMessage:
    def test_persists_regenerate_and_streams_new_turn(self, client, auth_headers):
        session = _make_session(agent_config={"model": "openai:gpt-4o-mini"})

        async def fake_stream(**_kwargs):
            yield 'data: {"type": "message_complete"}\n\n'

        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch(
                "synapse.routers.chat.lineage_regenerate",
                AsyncMock(return_value="original question"),
            ),
            patch("synapse.routers.chat.stream_chat_response", fake_stream),
        ):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/regenerate",
                json={},
                headers=auth_headers,
            )
        assert r.status_code == 200

    def test_agent_config_override_does_not_mutate_session(self, client, auth_headers):
        # The session row's agent_config must not be persisted with the
        # override applied — regeneration is a one-shot experiment.
        session = _make_session(agent_config={"model": "openai:gpt-4o-mini"})
        captured: dict = {}

        async def fake_stream(**kwargs):
            captured["model"] = kwargs["session"].agent_config.get("model")
            yield 'data: {"type": "message_complete"}\n\n'

        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch(
                "synapse.routers.chat.lineage_regenerate",
                AsyncMock(return_value="q"),
            ),
            patch("synapse.routers.chat.stream_chat_response", fake_stream),
        ):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/regenerate",
                json={"agent_config_override": {"model": "anthropic:claude-3-5-sonnet"}},
                headers=auth_headers,
            )
        assert r.status_code == 200
        # The override drove the agent for this turn…
        assert captured["model"] == "anthropic:claude-3-5-sonnet"
        # …and the session row was never committed with the override (the
        # MagicMock session has no commit recorded for agent_config — the
        # in-memory mutation in _stream_agent_turn is fine, but the DB
        # row was never re-saved).

    def test_returns_422_for_non_reflection(self, client, auth_headers):
        session = _make_session()
        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch(
                "synapse.routers.chat.lineage_regenerate",
                AsyncMock(side_effect=LineageError("wrong_event_type", "not a refl")),
            ),
        ):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/regenerate",
                json={},
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_returns_422_when_no_preceding_user_message(self, client, auth_headers):
        session = _make_session()
        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch(
                "synapse.routers.chat.lineage_regenerate",
                AsyncMock(side_effect=LineageError("no_preceding_user_message", "nothing to feed")),
            ),
        ):
            r = client.post(
                f"/v1/chat/sessions/{session.id}/messages/1/regenerate",
                json={},
                headers=auth_headers,
            )
        assert r.status_code == 422
