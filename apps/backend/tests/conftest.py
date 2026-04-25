"""Shared pytest fixtures for the Synapse backend test suite."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import jwt
import pytest

from synapse.config import Settings, get_settings
from synapse.council.models import CouncilMember, MemberRanking, RankingResult, StageOneResponse
from synapse.memory.gateway_client import MemoryHit

# ---------------------------------------------------------------------------
# Settings override — point at test doubles, never a real DB
# ---------------------------------------------------------------------------

TEST_SETTINGS = Settings(
    database_url="postgresql+asyncpg://synapse:synapse@localhost:5432/synapse_test",
    astrocyte_gateway_url="http://astrocyte-mock",
    astrocyte_token="test-api-key",
    centrifugo_api_url="http://centrifugo-mock",
    centrifugo_api_key="test-centrifugo-key",
    centrifugo_token_secret="test-centrifugo-secret",
    synapse_auth_mode="jwt_hs256",
    synapse_jwt_secret="test-jwt-secret",
    synapse_jwt_audience="synapse",
    stage1_timeout_seconds=10,
    stage2_timeout_seconds=10,
    stage3_timeout_seconds=10,
    max_precedents=3,
)


@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Replace the cached settings singleton with test values."""
    get_settings.cache_clear()
    monkeypatch.setattr("synapse.config.get_settings", lambda: TEST_SETTINGS)
    yield
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# JWT helper
# ---------------------------------------------------------------------------


def make_jwt(
    sub: str = "user-1",
    principal: str = "user-1",
    tenant_id: str = "tenant-test",
    roles: list[str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "sub": sub,
        "aud": "synapse",
        "synapse_roles": roles or ["member"],
        "synapse_tenant": tenant_id,
        "principal": principal,
    }
    return jwt.encode(payload, "test-jwt-secret", algorithm="HS256")


# ---------------------------------------------------------------------------
# Default council fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_members() -> list[CouncilMember]:
    return [
        CouncilMember(model_id="openai/gpt-4o", name="GPT-4o"),
        CouncilMember(model_id="anthropic/claude-3-5-sonnet-20241022", name="Claude"),
    ]


@pytest.fixture
def default_chairman() -> CouncilMember:
    return CouncilMember(model_id="anthropic/claude-opus-4-5", name="Chair")


@pytest.fixture
def sample_stage1_responses() -> list[StageOneResponse]:
    return [
        StageOneResponse(
            member_id="openai/gpt-4o", member_name="GPT-4o", content="Response A content"
        ),
        StageOneResponse(
            member_id="anthropic/claude-3-5-sonnet-20241022",
            member_name="Claude",
            content="Response B content",
        ),
    ]


@pytest.fixture
def sample_ranking_result(sample_stage1_responses) -> RankingResult:
    return RankingResult(
        label_map={
            "Response A": "openai/gpt-4o",
            "Response B": "anthropic/claude-3-5-sonnet-20241022",
        },
        member_rankings=[
            MemberRanking(
                member_id="openai/gpt-4o",
                member_name="GPT-4o",
                ranking=["Response A", "Response B"],
                raw_response="FINAL RANKING:\n1. Response A\n2. Response B",
            ),
            MemberRanking(
                member_id="anthropic/claude-3-5-sonnet-20241022",
                member_name="Claude",
                ranking=["Response A", "Response B"],
                raw_response="FINAL RANKING:\n1. Response A\n2. Response B",
            ),
        ],
        aggregate_scores={"Response A": 1.0, "Response B": 2.0},
        consensus_score=1.0,
    )


@pytest.fixture
def sample_precedents() -> list[MemoryHit]:
    return [
        MemoryHit(
            memory_id="hit-1",
            content="Past decision about testing.",
            score=0.9,
            bank_id="precedents",
            tags=[],
            metadata={},
        ),
        MemoryHit(
            memory_id="hit-2",
            content="Prior council verdict.",
            score=0.8,
            bank_id="precedents",
            tags=[],
            metadata={},
        ),
    ]


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="This is a mock LLM response.\nCONFIDENCE: HIGH")
    return llm


# ---------------------------------------------------------------------------
# Mock Astrocyte gateway client
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_astrocyte(sample_precedents):
    client = AsyncMock()
    client.recall = AsyncMock(return_value=sample_precedents)
    client.retain = AsyncMock(return_value=None)
    client.reflect = AsyncMock(return_value=None)
    client.forget = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# Mock Centrifugo client
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_centrifugo():
    client = AsyncMock()
    client.publish = AsyncMock(return_value=None)
    client.publish_council_event = AsyncMock(return_value=None)
    return client


# ---------------------------------------------------------------------------
# FastAPI test client (sync, no real DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def test_token() -> str:
    return make_jwt()


@pytest.fixture
def auth_headers(test_token) -> dict[str, str]:
    return {"Authorization": f"Bearer {test_token}"}
