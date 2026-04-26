"""Tests for the memory router (/v1/memory/*)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.main import create_app
from synapse.memory.gateway_client import MemoryHit, ReflectResult, RetainResult
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


# ===========================================================================
# GET /v1/memory/search
# ===========================================================================


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
    call_kwargs = mock_astrocyte.recall.call_args.kwargs
    assert call_kwargs["bank_id"] == "precedents"


def test_search_with_limit_param(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.recall = AsyncMock(return_value=[])

    resp = c.get("/v1/memory/search", params={"q": "anything", "limit": 5}, headers=headers)
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


# ===========================================================================
# POST /v1/memory/retain
# ===========================================================================


def test_retain_stores_to_agents_bank(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.retain = AsyncMock(return_value=RetainResult(memory_id="new-mem-1", stored=True))

    resp = c.post(
        "/v1/memory/retain",
        json={"content": "Agent context note.", "bank_id": "agents", "tags": ["context"]},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["memory_id"] == "new-mem-1"
    assert data["stored"] is True
    mock_astrocyte.retain.assert_called_once()
    call_kwargs = mock_astrocyte.retain.call_args.kwargs
    assert call_kwargs["bank_id"] == "agents"
    assert call_kwargs["content"] == "Agent context note."
    assert call_kwargs["tags"] == ["context"]


def test_retain_rejects_non_agent_bank(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/retain",
        json={"content": "Sneaky write.", "bank_id": "decisions"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "agents" in resp.json()["detail"]


def test_retain_requires_auth(client):
    c, _ = client
    resp = c.post(
        "/v1/memory/retain",
        json={"content": "text", "bank_id": "agents"},
    )
    assert resp.status_code == 401


def test_retain_requires_content(client, headers):
    c, _ = client
    resp = c.post("/v1/memory/retain", json={"bank_id": "agents"}, headers=headers)
    assert resp.status_code == 422


def test_retain_passes_metadata(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.retain = AsyncMock(return_value=RetainResult(memory_id="mem-meta", stored=True))

    resp = c.post(
        "/v1/memory/retain",
        json={"content": "With metadata.", "bank_id": "agents", "metadata": {"source": "ui"}},
        headers=headers,
    )
    assert resp.status_code == 201
    call_kwargs = mock_astrocyte.retain.call_args.kwargs
    assert call_kwargs["metadata"] == {"source": "ui"}


# ===========================================================================
# POST /v1/memory/reflect
# ===========================================================================


def test_reflect_returns_answer_and_sources(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.reflect = AsyncMock(
        return_value=ReflectResult(
            answer="We chose PostgreSQL for its ACID guarantees.",
            sources=[{"memory_id": "m-1", "content": "Adopted PostgreSQL."}],
        )
    )

    resp = c.post(
        "/v1/memory/reflect",
        json={"query": "Why PostgreSQL?", "bank_id": "decisions"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer"] == "We chose PostgreSQL for its ACID guarantees."
    assert len(data["sources"]) == 1
    mock_astrocyte.reflect.assert_called_once()
    call_kwargs = mock_astrocyte.reflect.call_args.kwargs
    assert call_kwargs["query"] == "Why PostgreSQL?"
    assert call_kwargs["bank_id"] == "decisions"
    assert call_kwargs["include_sources"] is True


def test_reflect_rejects_invalid_bank(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/reflect",
        json={"query": "anything", "bank_id": "agents"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_reflect_passes_max_tokens(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.reflect = AsyncMock(return_value=ReflectResult(answer="short", sources=[]))

    resp = c.post(
        "/v1/memory/reflect",
        json={"query": "summary", "bank_id": "decisions", "max_tokens": 500},
        headers=headers,
    )
    assert resp.status_code == 200
    call_kwargs = mock_astrocyte.reflect.call_args.kwargs
    assert call_kwargs["max_tokens"] == 500


def test_reflect_requires_auth(client):
    c, _ = client
    resp = c.post(
        "/v1/memory/reflect",
        json={"query": "test", "bank_id": "decisions"},
    )
    assert resp.status_code == 401


def test_reflect_requires_query(client, headers):
    c, _ = client
    resp = c.post("/v1/memory/reflect", json={"bank_id": "decisions"}, headers=headers)
    assert resp.status_code == 422


# ===========================================================================
# POST /v1/memory/forget
# ===========================================================================


def test_forget_by_memory_ids(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.forget = AsyncMock(return_value={"deleted": 1})

    resp = c.post(
        "/v1/memory/forget",
        json={"bank_id": "agents", "memory_ids": ["mem-abc"]},
        headers=headers,
    )
    assert resp.status_code == 200
    mock_astrocyte.forget.assert_called_once()
    call_kwargs = mock_astrocyte.forget.call_args.kwargs
    assert call_kwargs["bank_id"] == "agents"
    assert call_kwargs["memory_ids"] == ["mem-abc"]


def test_forget_by_tags(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.forget = AsyncMock(return_value={"deleted": 3})

    resp = c.post(
        "/v1/memory/forget",
        json={"bank_id": "agents", "tags": ["temp", "draft"]},
        headers=headers,
    )
    assert resp.status_code == 200
    call_kwargs = mock_astrocyte.forget.call_args.kwargs
    assert call_kwargs["tags"] == ["temp", "draft"]


def test_forget_requires_selector(client, headers):
    """Omitting both memory_ids and tags should return 422."""
    c, _ = client
    resp = c.post("/v1/memory/forget", json={"bank_id": "agents"}, headers=headers)
    assert resp.status_code == 422


def test_forget_rejects_non_agent_bank(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/forget",
        json={"bank_id": "decisions", "memory_ids": ["m-1"]},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "agents" in resp.json()["detail"]


def test_forget_requires_auth(client):
    c, _ = client
    resp = c.post(
        "/v1/memory/forget",
        json={"bank_id": "agents", "memory_ids": ["m-1"]},
    )
    assert resp.status_code == 401


# ===========================================================================
# POST /v1/memory/graph/search
# ===========================================================================


def test_graph_search_returns_entities(client, headers, sample_graph_entities):
    c, mock_astrocyte = client
    mock_astrocyte.graph_search = AsyncMock(return_value=sample_graph_entities)

    resp = c.post(
        "/v1/memory/graph/search",
        json={"query": "PostgreSQL", "bank_id": "decisions"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["query"] == "PostgreSQL"
    assert data["bank"] == "decisions"
    assert data["count"] == 2
    assert data["entities"][0]["entity_id"] == "ent-1"
    assert data["entities"][0]["name"] == "PostgreSQL"
    assert data["entities"][0]["entity_type"] == "technology"


def test_graph_search_passes_limit(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.graph_search = AsyncMock(return_value=[])

    resp = c.post(
        "/v1/memory/graph/search",
        json={"query": "Redis", "bank_id": "decisions", "limit": 5},
        headers=headers,
    )
    assert resp.status_code == 200
    call_kwargs = mock_astrocyte.graph_search.call_args.kwargs
    assert call_kwargs["limit"] == 5


def test_graph_search_rejects_invalid_bank(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/graph/search",
        json={"query": "anything", "bank_id": "councils"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_graph_search_requires_auth(client):
    c, _ = client
    resp = c.post(
        "/v1/memory/graph/search",
        json={"query": "x", "bank_id": "decisions"},
    )
    assert resp.status_code == 401


def test_graph_search_limit_capped_at_50(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/graph/search",
        json={"query": "x", "bank_id": "decisions", "limit": 999},
        headers=headers,
    )
    assert resp.status_code == 422


# ===========================================================================
# POST /v1/memory/graph/neighbors
# ===========================================================================


def test_graph_neighbors_returns_hits(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.graph_neighbors = AsyncMock(
        return_value=[
            MemoryHit(
                memory_id="m-1",
                content="PostgreSQL chosen.",
                score=0.9,
                bank_id="decisions",
                tags=["verdict"],
                metadata={},
            )
        ]
    )

    resp = c.post(
        "/v1/memory/graph/neighbors",
        json={"entity_ids": ["ent-1"], "bank_id": "decisions"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["hits"][0]["memory_id"] == "m-1"
    mock_astrocyte.graph_neighbors.assert_called_once()
    call_kwargs = mock_astrocyte.graph_neighbors.call_args.kwargs
    assert call_kwargs["entity_ids"] == ["ent-1"]
    assert call_kwargs["max_depth"] == 2  # default


def test_graph_neighbors_custom_depth(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.graph_neighbors = AsyncMock(return_value=[])

    resp = c.post(
        "/v1/memory/graph/neighbors",
        json={"entity_ids": ["ent-1", "ent-2"], "bank_id": "agents", "max_depth": 3, "limit": 50},
        headers=headers,
    )
    assert resp.status_code == 200
    call_kwargs = mock_astrocyte.graph_neighbors.call_args.kwargs
    assert call_kwargs["max_depth"] == 3
    assert call_kwargs["limit"] == 50


def test_graph_neighbors_rejects_invalid_bank(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/graph/neighbors",
        json={"entity_ids": ["ent-1"], "bank_id": "councils"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_graph_neighbors_requires_auth(client):
    c, _ = client
    resp = c.post(
        "/v1/memory/graph/neighbors",
        json={"entity_ids": ["ent-1"], "bank_id": "decisions"},
    )
    assert resp.status_code == 401


def test_graph_neighbors_max_depth_capped_at_5(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/graph/neighbors",
        json={"entity_ids": ["ent-1"], "bank_id": "decisions", "max_depth": 99},
        headers=headers,
    )
    assert resp.status_code == 422


# ===========================================================================
# POST /v1/memory/compile
# ===========================================================================


def test_compile_triggers_wiki_synthesis(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.compile = AsyncMock(
        return_value={"pages_written": 3, "scopes": ["architecture", "security"]}
    )

    resp = c.post(
        "/v1/memory/compile",
        json={"bank_id": "decisions"},
        headers=headers,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["pages_written"] == 3
    assert "architecture" in data["scopes"]
    mock_astrocyte.compile.assert_called_once()
    call_kwargs = mock_astrocyte.compile.call_args.kwargs
    assert call_kwargs["bank_id"] == "decisions"
    assert call_kwargs["scope"] is None


def test_compile_with_scope(client, headers):
    c, mock_astrocyte = client
    mock_astrocyte.compile = AsyncMock(return_value={"pages_written": 1, "scopes": ["security"]})

    resp = c.post(
        "/v1/memory/compile",
        json={"bank_id": "agents", "scope": "security"},
        headers=headers,
    )
    assert resp.status_code == 202
    call_kwargs = mock_astrocyte.compile.call_args.kwargs
    assert call_kwargs["scope"] == "security"


def test_compile_rejects_non_compile_bank(client, headers):
    c, _ = client
    resp = c.post(
        "/v1/memory/compile",
        json={"bank_id": "precedents"},
        headers=headers,
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "decisions" in detail or "agents" in detail


def test_compile_requires_auth(client):
    c, _ = client
    resp = c.post("/v1/memory/compile", json={"bank_id": "decisions"})
    assert resp.status_code == 401
