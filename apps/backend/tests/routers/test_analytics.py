"""Tests for the /v1/analytics router — B8."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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
def headers():
    return {"Authorization": f"Bearer {make_jwt(sub='user-1', tenant_id='tenant-test')}"}


# ---------------------------------------------------------------------------
# Helper — common mock response factories
# ---------------------------------------------------------------------------


def _patch_leaderboard(members=None):
    if members is None:
        members = [
            {
                "member_id": "m1",
                "member_name": "Alice",
                "councils_participated": 5,
                "avg_consensus_score": 0.82,
                "dissent_count": 1,
            }
        ]
    return patch(
        "synapse.routers.analytics.member_leaderboard",
        new=AsyncMock(return_value=members),
    )


def _patch_velocity(data=None):
    if data is None:
        data = [{"date": "2026-04-01", "count": 3}]
    return patch(
        "synapse.routers.analytics.decision_velocity",
        new=AsyncMock(return_value=data),
    )


def _patch_consensus(data=None):
    if data is None:
        data = {"high": 4, "medium": 2, "low": 1, "unscored": 0, "total": 7}
    return patch(
        "synapse.routers.analytics.consensus_distribution",
        new=AsyncMock(return_value=data),
    )


def _patch_topics(data=None):
    if data is None:
        data = [{"topic_tag": "product", "count": 3, "avg_consensus": 0.8}]
    return patch(
        "synapse.routers.analytics.topic_summary",
        new=AsyncMock(return_value=data),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_member_leaderboard_returns_200(client, headers):
    with _patch_leaderboard():
        resp = client.get("/v1/analytics/members", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "generated_at" in body
    assert isinstance(body["data"], list)


def test_decision_velocity_returns_200(client, headers):
    with _patch_velocity():
        resp = client.get("/v1/analytics/velocity", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "days" in body
    assert isinstance(body["data"], list)


def test_consensus_distribution_returns_200(client, headers):
    with _patch_consensus():
        resp = client.get("/v1/analytics/consensus", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    dist = body["data"]
    for key in ("high", "medium", "low", "unscored", "total"):
        assert key in dist


def test_topics_returns_200_without_cluster(client, headers):
    with _patch_topics():
        resp = client.get("/v1/analytics/topics", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body
    assert "clusters" not in body


def test_topics_cluster_true_calls_astrocyte(client, app, headers, mock_astrocyte):
    from synapse.memory.gateway_client import ReflectResult

    mock_astrocyte.reflect = AsyncMock(
        return_value=ReflectResult(answer="Cluster A: product, tech", sources=[])
    )
    app.state.astrocyte = mock_astrocyte

    with _patch_topics():
        resp = client.get("/v1/analytics/topics?cluster=true", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert "clusters" in body
    assert body["clusters"] == "Cluster A: product, tech"


def test_analytics_scoped_by_tenant(client, headers):
    """Metric functions must receive the user's tenant_id from the JWT."""
    captured: list[str | None] = []

    async def _capture(db, tenant_id, **kwargs):
        captured.append(tenant_id)
        return []

    with patch("synapse.routers.analytics.member_leaderboard", new=_capture):
        client.get("/v1/analytics/members", headers=headers)

    assert captured == ["tenant-test"]


def test_analytics_returns_500_on_db_error(client, headers):
    async def _boom(db, tenant_id, **kwargs):
        raise RuntimeError("db down")

    with patch("synapse.routers.analytics.member_leaderboard", new=_boom):
        resp = client.get("/v1/analytics/members", headers=headers)

    assert resp.status_code == 500
    assert resp.json()["detail"] == "analytics query failed"
