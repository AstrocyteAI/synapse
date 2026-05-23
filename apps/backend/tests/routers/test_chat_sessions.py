"""Tests for /v1/chat/sessions — chat-with-tools session CRUD."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    session_id: uuid.UUID | None = None,
    *,
    tenant_id: str | None = "tenant-test",
    created_by: str = "user:user-1",
    status_value: str = "active",
    title: str | None = "Test chat",
    council_id: uuid.UUID | None = None,
    agent_config: dict | None = None,
    parent_session_id: uuid.UUID | None = None,
    parent_fork_event_id: int | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = session_id or uuid.uuid4()
    s.thread_id = uuid.uuid4()
    s.tenant_id = tenant_id
    s.created_by = created_by
    s.title = title
    s.status = status_value
    s.council_id = council_id
    s.agent_config = agent_config or {}
    s.parent_session_id = parent_session_id
    s.parent_fork_event_id = parent_fork_event_id
    s.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    s.updated_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return s


# ---------------------------------------------------------------------------
# App fixture — same pattern as test_threads.py
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
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_token():
    return make_jwt(sub="admin-1", tenant_id="tenant-test", roles=["admin"])


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# POST /v1/chat/sessions
# ---------------------------------------------------------------------------


class TestCreateChatSession:
    def test_create_returns_201_with_session(self, client, db_session, auth_headers):
        new_session = _make_session(title="My new chat")

        with patch("synapse.routers.chat.create_session", AsyncMock(return_value=new_session)):
            resp = client.post(
                "/v1/chat/sessions",
                json={"title": "My new chat"},
                headers=auth_headers,
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "My new chat"
        assert body["status"] == "active"
        assert body["created_by"] == "user:user-1"
        assert body["tenant_id"] == "tenant-test"
        assert "id" in body
        assert "thread_id" in body

    def test_create_accepts_council_id_for_mode_3_chat(self, client, db_session, auth_headers):
        council_id = uuid.uuid4()
        new_session = _make_session(council_id=council_id, title="Verdict chat")

        with patch("synapse.routers.chat.create_session", AsyncMock(return_value=new_session)):
            resp = client.post(
                "/v1/chat/sessions",
                json={"title": "Verdict chat", "council_id": str(council_id)},
                headers=auth_headers,
            )

        assert resp.status_code == 201
        assert resp.json()["council_id"] == str(council_id)

    def test_create_accepts_agent_config(self, client, db_session, auth_headers):
        new_session = _make_session(
            agent_config={
                "model": "openai:gpt-4o",
                "instructions": "Be brief.",
                "tools": ["web_search"],
                "memory_banks": ["acme:decisions"],
                "sandbox_runtime_preference": "auto",
            }
        )

        with patch("synapse.routers.chat.create_session", AsyncMock(return_value=new_session)):
            resp = client.post(
                "/v1/chat/sessions",
                json={
                    "agent_config": {
                        "model": "openai:gpt-4o",
                        "instructions": "Be brief.",
                        "tools": ["web_search"],
                    },
                },
                headers=auth_headers,
            )

        assert resp.status_code == 201
        cfg = resp.json()["agent_config"]
        assert cfg["model"] == "openai:gpt-4o"
        assert "web_search" in cfg["tools"]

    def test_create_requires_auth(self, client):
        resp = client.post("/v1/chat/sessions", json={"title": "Anon"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/chat/sessions
# ---------------------------------------------------------------------------


class TestListChatSessions:
    def test_list_returns_active_sessions_by_default(self, client, db_session, auth_headers):
        rows = [_make_session(title=f"Chat {i}") for i in range(3)]
        with patch(
            "synapse.routers.chat.list_sessions",
            AsyncMock(return_value=(rows, None)),
        ):
            resp = client.get("/v1/chat/sessions", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 3
        assert body["next_before_id"] is None

    def test_list_returns_cursor_when_more_pages_exist(self, client, db_session, auth_headers):
        rows = [_make_session() for _ in range(2)]
        cursor = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        with patch(
            "synapse.routers.chat.list_sessions",
            AsyncMock(return_value=(rows, cursor)),
        ):
            resp = client.get("/v1/chat/sessions", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["next_before_id"] is not None

    def test_list_status_filter_archived(self, client, db_session, auth_headers):
        archived = [_make_session(status_value="archived")]
        mock = AsyncMock(return_value=(archived, None))
        with patch("synapse.routers.chat.list_sessions", mock):
            resp = client.get("/v1/chat/sessions?status=archived", headers=auth_headers)

        assert resp.status_code == 200
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["status"] == "archived"

    def test_list_invalid_status_returns_422(self, client, auth_headers):
        resp = client.get("/v1/chat/sessions?status=nonsense", headers=auth_headers)
        assert resp.status_code == 422

    def test_list_scopes_to_caller_principal_by_default(self, client, db_session, auth_headers):
        mock = AsyncMock(return_value=([], None))
        with patch("synapse.routers.chat.list_sessions", mock):
            client.get("/v1/chat/sessions", headers=auth_headers)

        assert mock.call_args.kwargs["created_by"] == "user:user-1"

    def test_list_admin_sees_all_sessions_in_tenant(self, client, db_session, admin_headers):
        mock = AsyncMock(return_value=([], None))
        with patch("synapse.routers.chat.list_sessions", mock):
            client.get("/v1/chat/sessions", headers=admin_headers)

        # Admin role bypasses the per-principal filter.
        assert mock.call_args.kwargs["created_by"] is None

    def test_list_requires_auth(self, client):
        resp = client.get("/v1/chat/sessions")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/chat/sessions/{id}
# ---------------------------------------------------------------------------


class TestGetChatSession:
    def test_get_returns_session(self, client, db_session, auth_headers):
        session_id = uuid.uuid4()
        session = _make_session(session_id=session_id)
        with patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)):
            resp = client.get(f"/v1/chat/sessions/{session_id}", headers=auth_headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(session_id)

    def test_get_returns_404_for_missing(self, client, db_session, auth_headers):
        session_id = uuid.uuid4()
        with patch("synapse.routers.chat.get_session", AsyncMock(return_value=None)):
            resp = client.get(f"/v1/chat/sessions/{session_id}", headers=auth_headers)

        assert resp.status_code == 404

    def test_get_returns_404_for_cross_tenant(self, client, db_session, auth_headers):
        # Service layer returns None for cross-tenant fetches — same 404 path
        # as missing. Verify the router doesn't leak with 403 or 500.
        session_id = uuid.uuid4()
        with patch("synapse.routers.chat.get_session", AsyncMock(return_value=None)):
            resp = client.get(f"/v1/chat/sessions/{session_id}", headers=auth_headers)

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /v1/chat/sessions/{id}
# ---------------------------------------------------------------------------


class TestPatchChatSession:
    def test_patch_updates_title(self, client, db_session, auth_headers):
        session_id = uuid.uuid4()
        session = _make_session(session_id=session_id, title="Old")
        updated = _make_session(session_id=session_id, title="New")

        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch("synapse.routers.chat.update_session", AsyncMock(return_value=updated)),
        ):
            resp = client.patch(
                f"/v1/chat/sessions/{session_id}",
                json={"title": "New"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["title"] == "New"

    def test_patch_updates_status_to_archived(self, client, db_session, auth_headers):
        session_id = uuid.uuid4()
        session = _make_session(session_id=session_id)
        archived = _make_session(session_id=session_id, status_value="archived")

        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch("synapse.routers.chat.update_session", AsyncMock(return_value=archived)),
        ):
            resp = client.patch(
                f"/v1/chat/sessions/{session_id}",
                json={"status": "archived"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"

    def test_patch_returns_404_for_missing(self, client, db_session, auth_headers):
        session_id = uuid.uuid4()
        with patch("synapse.routers.chat.get_session", AsyncMock(return_value=None)):
            resp = client.patch(
                f"/v1/chat/sessions/{session_id}",
                json={"title": "Doesn't matter"},
                headers=auth_headers,
            )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /v1/chat/sessions/{id}
# ---------------------------------------------------------------------------


class TestDeleteChatSession:
    def test_delete_archives_session(self, client, db_session, auth_headers):
        session_id = uuid.uuid4()
        session = _make_session(session_id=session_id)

        archive_mock = AsyncMock(
            return_value=_make_session(session_id=session_id, status_value="archived")
        )
        with (
            patch("synapse.routers.chat.get_session", AsyncMock(return_value=session)),
            patch("synapse.routers.chat.archive_session", archive_mock),
        ):
            resp = client.delete(f"/v1/chat/sessions/{session_id}", headers=auth_headers)

        assert resp.status_code == 204
        archive_mock.assert_awaited_once()

    def test_delete_returns_404_for_missing(self, client, db_session, auth_headers):
        session_id = uuid.uuid4()
        with patch("synapse.routers.chat.get_session", AsyncMock(return_value=None)):
            resp = client.delete(f"/v1/chat/sessions/{session_id}", headers=auth_headers)

        assert resp.status_code == 404
