"""Tests for the GET /v1/memory/search endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.main import create_app
from synapse.memory.gateway_client import MemoryHit
from tests.conftest import TEST_SETTINGS, make_jwt


@pytest.fixture
def client(mock_astrocyte, mock_centrifugo):
    app = create_app()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_sessionmaker.return_value.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as c,
    ):
        app.state.astrocyte = mock_astrocyte
        app.state.centrifugo = mock_centrifugo
        app.state.sessionmaker = mock_sessionmaker
        yield c, mock_astrocyte


@pytest.fixture
def token():
    return make_jwt(sub="user-1", tenant_id="tenant-test")


@pytest.fixture
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_search_returns_hits(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.recall = AsyncMock(
        return_value=[
            MemoryHit(
                memory_id="m-1",
                content="We decided to adopt PostgreSQL.",
                score=0.92,
                bank_id="decisions",
                tags=["verdict", "architecture"],
                metadata={"council_id": "abc"},
            ),
            MemoryHit(
                memory_id="m-2",
                content="Microservices deferred to Q3.",
                score=0.81,
                bank_id="decisions",
                tags=["verdict"],
                metadata={},
            ),
        ]
    )

    resp = c.get("/v1/memory/search", params={"q": "database choice"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "database choice"
    assert data["bank"] == "decisions"
    assert data["count"] == 2
    hits = data["hits"]
    assert hits[0]["memory_id"] == "m-1"
    assert hits[0]["content"] == "We decided to adopt PostgreSQL."
    assert hits[0]["score"] == 0.92
    assert "architecture" in hits[0]["tags"]


def test_search_with_bank_param(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.recall = AsyncMock(return_value=[])

    resp = c.get(
        "/v1/memory/search",
        params={"q": "security incident", "bank": "precedents"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["bank"] == "precedents"
    mock_astrocyte.recall.assert_called_once()
    call_kwargs = mock_astrocyte.recall.call_args.kwargs
    assert call_kwargs["bank_id"] == "precedents"


def test_search_with_limit_param(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.recall = AsyncMock(return_value=[])

    resp = c.get(
        "/v1/memory/search",
        params={"q": "anything", "limit": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    call_kwargs = mock_astrocyte.recall.call_args.kwargs
    assert call_kwargs["max_results"] == 5


def test_search_empty_results(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.recall = AsyncMock(return_value=[])

    resp = c.get("/v1/memory/search", params={"q": "nothing matches"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["hits"] == []


def test_search_invalid_bank_falls_back_to_default(client, headers):
    """Unknown bank values are silently replaced with the default bank."""
    c, mock_astrocyte = client
    mock_astrocyte.recall = AsyncMock(return_value=[])

    resp = c.get(
        "/v1/memory/search",
        params={"q": "test", "bank": "not-a-real-bank"},
        headers=headers,
    )
    assert resp.status_code == 200
    call_kwargs = mock_astrocyte.recall.call_args.kwargs
    assert call_kwargs["bank_id"] == "decisions"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_search_requires_auth(client):
    c, _ = client
    resp = c.get("/v1/memory/search", params={"q": "test"})
    assert resp.status_code == 401


def test_search_missing_q_returns_422(client, headers):
    c, _ = client
    resp = c.get("/v1/memory/search", headers=headers)
    assert resp.status_code == 422


def test_search_limit_capped_at_20(client, headers):
    c, _ = client
    resp = c.get(
        "/v1/memory/search",
        params={"q": "test", "limit": 999},
        headers=headers,
    )
    assert resp.status_code == 422
