"""Tests for the /v1/councils router."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import CouncilSession, CouncilStatus
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# App fixture with fully mocked infrastructure
# ---------------------------------------------------------------------------


@pytest.fixture
def _wired_client(mock_astrocyte, mock_centrifugo, mock_llm):
    """App + TestClient with mocks applied *after* lifespan runs.

    Lifespan overwrites app.state — we must patch synapse.main.get_settings so
    it uses TEST_SETTINGS, then override astrocyte/centrifugo/sessionmaker after
    the lifespan yields.
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
        application.state.astrocyte = mock_astrocyte
        application.state.centrifugo = mock_centrifugo
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


def _make_thread_event(id: int = 1, thread_id: uuid.UUID | None = None) -> MagicMock:
    e = MagicMock()
    e.id = id
    e.thread_id = thread_id or uuid.uuid4()
    e.event_type = "council_started"
    e.actor_id = "system"
    e.actor_name = ""
    e.content = None
    e.event_metadata = {}
    e.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return e


def _make_council_session(**kwargs) -> CouncilSession:
    defaults = dict(
        id=uuid.uuid4(),
        question="What should we do?",
        status=CouncilStatus.closed,
        council_type="llm",
        members=[{"model_id": "openai/gpt-4o", "name": "GPT"}],
        chairman={"model_id": "anthropic/claude-opus-4-5", "name": "Chair"},
        config={},
        verdict="Proceed with plan A.",
        consensus_score=0.85,
        confidence_label="high",
        dissent_detected=False,
        topic_tag="product",
        template_id=None,
        created_by="user:user-1",
        tenant_id="tenant-test",
        created_at=datetime.now(UTC),
        closed_at=datetime.now(UTC),
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=CouncilSession)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# POST /v1/councils
# ---------------------------------------------------------------------------


def test_create_council_returns_202(client, db_session, headers):
    session_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    mock_cs = _make_council_session(id=session_id, status=CouncilStatus.pending)
    mock_thread = MagicMock()
    mock_thread.id = thread_id

    with (
        patch("synapse.routers.councils.asyncio.create_task"),
        patch("synapse.council.session.create_session", new=AsyncMock(return_value=mock_cs)),
        patch("synapse.routers.councils.create_thread", new=AsyncMock(return_value=mock_thread)),
        patch(
            "synapse.routers.councils.append_event",
            new=AsyncMock(return_value=_make_thread_event(thread_id=thread_id)),
        ),
    ):
        resp = client.post(
            "/v1/councils",
            json={"question": "What should we prioritise?"},
            headers=headers,
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "session_id" in body
    assert "thread_id" in body
    assert body["status"] == CouncilStatus.pending


def test_create_council_requires_auth(client):
    resp = client.post("/v1/councils", json={"question": "Q?"})
    assert resp.status_code == 401


def test_create_council_validates_question(client, headers):
    resp = client.post("/v1/councils", json={}, headers=headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /v1/councils/{session_id}
# ---------------------------------------------------------------------------


def test_get_council_returns_session(client, db_session, headers):
    session_id = uuid.uuid4()
    mock_cs = _make_council_session(id=session_id)
    db_session.get = AsyncMock(return_value=mock_cs)

    with patch("synapse.routers.councils.get_session", new=AsyncMock(return_value=mock_cs)):
        resp = client.get(f"/v1/councils/{session_id}", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == str(session_id)
    assert body["verdict"] == "Proceed with plan A."


def test_get_council_404_on_missing(client, db_session, headers):
    session_id = uuid.uuid4()
    with patch("synapse.routers.councils.get_session", new=AsyncMock(return_value=None)):
        resp = client.get(f"/v1/councils/{session_id}", headers=headers)
    assert resp.status_code == 404


def test_get_council_403_on_wrong_tenant(client, headers):
    session_id = uuid.uuid4()
    mock_cs = _make_council_session(id=session_id, tenant_id="other-tenant")
    with patch("synapse.routers.councils.get_session", new=AsyncMock(return_value=mock_cs)):
        resp = client.get(f"/v1/councils/{session_id}", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /v1/councils
# ---------------------------------------------------------------------------


def test_list_councils_returns_list(client, headers):
    sessions = [
        _make_council_session(id=uuid.uuid4()),
        _make_council_session(id=uuid.uuid4()),
    ]
    with patch("synapse.routers.councils.list_sessions", new=AsyncMock(return_value=sessions)):
        resp = client.get("/v1/councils", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    # Summary should truncate long questions
    for item in body:
        assert "session_id" in item
        assert "status" in item


def test_list_councils_requires_auth(client):
    resp = client.get("/v1/councils")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/centrifugo/token
# ---------------------------------------------------------------------------


def test_centrifugo_token_returns_token(client, headers):
    resp = client.get("/v1/centrifugo/token", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert isinstance(body["token"], str)


def test_centrifugo_token_requires_auth(client):
    resp = client.get("/v1/centrifugo/token")
    assert resp.status_code == 401
