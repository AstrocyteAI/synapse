"""Tests for conflict detection."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from synapse.council.conflict import SIMILARITY_THRESHOLD, check_conflict
from synapse.memory.gateway_client import MemoryHit


def _hit(content: str, score: float = 0.85) -> MemoryHit:
    return MemoryHit(
        memory_id="hit-1",
        content=content,
        score=score,
        bank_id="precedents",
        tags=[],
        metadata={},
    )


# ---------------------------------------------------------------------------
# Short-circuit: no high-similarity precedents
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_conflict_when_no_relevant_precedents():
    """Low-score precedents skip the LLM call entirely."""
    llm = AsyncMock()
    result = await check_conflict(
        verdict="We should use PostgreSQL.",
        question="Which database?",
        precedents=[_hit("Use MongoDB.", score=0.5)],  # below threshold
        chairman_model_id="openai/gpt-4o",
        llm=llm,
        timeout=5.0,
    )
    assert result.detected is False
    llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_no_conflict_when_empty_precedents():
    llm = AsyncMock()
    result = await check_conflict(
        verdict="Verdict.",
        question="Q?",
        precedents=[],
        chairman_model_id="openai/gpt-4o",
        llm=llm,
        timeout=5.0,
    )
    assert result.detected is False
    llm.complete.assert_not_called()


# ---------------------------------------------------------------------------
# LLM says YES — conflict detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflict_detected_when_llm_says_yes():
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=(
            "CONFLICT: YES\n"
            "The new verdict recommends PostgreSQL while the past decision mandated MongoDB."
        )
    )
    precedent = _hit("We decided to use MongoDB as our primary database.", score=0.88)

    result = await check_conflict(
        verdict="We should adopt PostgreSQL.",
        question="Which database should we use?",
        precedents=[precedent],
        chairman_model_id="openai/gpt-4o",
        llm=llm,
        timeout=5.0,
    )

    assert result.detected is True
    assert result.summary is not None
    assert "PostgreSQL" in result.summary or "MongoDB" in result.summary
    assert result.conflicting_content is not None
    assert result.precedent_score == 0.88


# ---------------------------------------------------------------------------
# LLM says NO — no conflict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_conflict_when_llm_says_no():
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="CONFLICT: NO")
    precedent = _hit("We use PostgreSQL for our primary store.", score=0.9)

    result = await check_conflict(
        verdict="We should continue using PostgreSQL.",
        question="Should we change databases?",
        precedents=[precedent],
        chairman_model_id="openai/gpt-4o",
        llm=llm,
        timeout=5.0,
    )

    assert result.detected is False
    assert result.summary is None


# ---------------------------------------------------------------------------
# LLM failure — graceful no-conflict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_failure_treated_as_no_conflict():
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=Exception("LLM unavailable"))
    precedent = _hit("Prior decision content.", score=0.9)

    result = await check_conflict(
        verdict="New verdict.",
        question="Q?",
        precedents=[precedent],
        chairman_model_id="openai/gpt-4o",
        llm=llm,
        timeout=5.0,
    )

    assert result.detected is False


# ---------------------------------------------------------------------------
# Only considers precedents above threshold
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uses_only_high_similarity_precedents():
    """Precedents below SIMILARITY_THRESHOLD are filtered out before the LLM call."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="CONFLICT: NO")

    below = _hit("Old decision below threshold.", score=SIMILARITY_THRESHOLD - 0.01)
    above = _hit("Old decision above threshold.", score=SIMILARITY_THRESHOLD + 0.01)

    await check_conflict(
        verdict="New verdict.",
        question="Q?",
        precedents=[below, above],
        chairman_model_id="openai/gpt-4o",
        llm=llm,
        timeout=5.0,
    )

    # LLM was called (above-threshold precedent exists)
    llm.complete.assert_called_once()
    # The prompt should contain only the above-threshold precedent
    call_messages = llm.complete.call_args.kwargs.get("messages") or llm.complete.call_args[1].get(
        "messages", []
    )
    system_content = next(m["content"] for m in call_messages if m["role"] == "system")
    assert "above threshold" in system_content
    assert "below threshold" not in system_content
