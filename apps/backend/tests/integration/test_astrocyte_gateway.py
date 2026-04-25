"""Integration tests for AstrocyteGatewayClient against a live gateway.

These tests exercise the real retain → recall → reflect → forget lifecycle.
Each test uses a unique run_id tag so they are fully isolated from each other
and from production data.
"""

from __future__ import annotations

import asyncio

import pytest

from synapse.memory.banks import Banks

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# retain → recall round-trip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retain_and_recall(gateway, context, run_id):
    content = f"The council decided to proceed with plan Bravo. [{run_id}]"

    retain_result = await gateway.retain(
        content=content,
        bank_id=Banks.DECISIONS,
        tags=[run_id, "decision"],
        context=context,
        metadata={"council_id": "test-001", "consensus_score": 0.9},
    )
    assert retain_result.stored is True
    assert retain_result.memory_id

    # Allow indexing time
    await asyncio.sleep(1)

    hits = await gateway.recall(
        query="What did the council decide about Bravo?",
        bank_id=Banks.DECISIONS,
        context=context,
        max_results=5,
        tags=[run_id],
    )
    assert len(hits) >= 1
    assert any(run_id in h.content for h in hits)


@pytest.mark.asyncio
async def test_recall_empty_returns_no_results(gateway, context, run_id):
    hits = await gateway.recall(
        query="something completely unrelated to anything",
        bank_id=Banks.PRECEDENTS,
        context=context,
        max_results=5,
        tags=[f"nonexistent-{run_id}"],
    )
    assert hits == []


@pytest.mark.asyncio
async def test_retain_to_councils_bank(gateway, context, run_id):
    transcript = (
        f"Council: Should we adopt the new architecture? [{run_id}]\n\n"
        "[GPT-4o]: Yes, the benefits outweigh the migration cost.\n"
        "[Claude]: Agreed, but phase the rollout.\n\n"
        "Verdict: Proceed with phased rollout."
    )
    result = await gateway.retain(
        content=transcript,
        bank_id=Banks.COUNCILS,
        tags=[run_id, "architecture"],
        context=context,
        metadata={"council_id": "test-002", "consensus_score": 0.85},
    )
    assert result.stored is True


@pytest.mark.asyncio
async def test_retain_multiple_then_recall_ranked(gateway, context, run_id):
    """Retained content should come back ordered by relevance score."""
    documents = [
        (f"The council approved budget increase for Q3. [{run_id}]", "finance"),
        (f"The council rejected the security audit delay. [{run_id}]", "security"),
        (f"The council endorsed the new onboarding flow. [{run_id}]", "product"),
    ]
    for content, topic in documents:
        await gateway.retain(
            content=content,
            bank_id=Banks.DECISIONS,
            tags=[run_id, topic],
            context=context,
        )

    await asyncio.sleep(1)

    hits = await gateway.recall(
        query="What did the council decide about security?",
        bank_id=Banks.DECISIONS,
        context=context,
        max_results=3,
        tags=[run_id],
    )
    assert len(hits) >= 1
    # Most relevant hit should mention security
    assert "security" in hits[0].content.lower()
    # Scores should be descending
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# reflect
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reflect_synthesises_retained_content(gateway, context, run_id):
    await gateway.retain(
        content=f"The council ruled that all API changes require a two-week review window. [{run_id}]",
        bank_id=Banks.DECISIONS,
        tags=[run_id, "process"],
        context=context,
    )
    await asyncio.sleep(1)

    result = await gateway.reflect(
        query="What is the required review window for API changes?",
        bank_id=Banks.DECISIONS,
        context=context,
        include_sources=True,
    )
    assert result.answer
    assert len(result.answer) > 10
    # Should reference the two-week rule somewhere
    assert "two" in result.answer.lower() or "week" in result.answer.lower() or "review" in result.answer.lower()


# ---------------------------------------------------------------------------
# forget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forget_by_tags(gateway, context, run_id):
    forget_tag = f"forget-me-{run_id}"
    await gateway.retain(
        content=f"Temporary decision to be forgotten. [{run_id}]",
        bank_id=Banks.DECISIONS,
        tags=[run_id, forget_tag],
        context=context,
    )
    await asyncio.sleep(1)

    # Confirm it's there
    before = await gateway.recall(
        query="temporary decision",
        bank_id=Banks.DECISIONS,
        context=context,
        tags=[forget_tag],
    )
    assert len(before) >= 1

    # Forget it
    await gateway.forget(
        bank_id=Banks.DECISIONS,
        context=context,
        tags=[forget_tag],
    )
    await asyncio.sleep(1)

    # Confirm it's gone
    after = await gateway.recall(
        query="temporary decision",
        bank_id=Banks.DECISIONS,
        context=context,
        tags=[forget_tag],
    )
    assert len(after) == 0


# ---------------------------------------------------------------------------
# Precedents bank — used by council Stage 1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retain_and_recall_precedents(gateway, context, run_id):
    await gateway.retain(
        content=f"Prior ruling: monorepos require a dedicated platform team. [{run_id}]",
        bank_id=Banks.PRECEDENTS,
        tags=[run_id, "platform"],
        context=context,
    )
    await asyncio.sleep(1)

    hits = await gateway.recall(
        query="What has been decided about monorepo governance?",
        bank_id=Banks.PRECEDENTS,
        context=context,
        max_results=3,
        tags=[run_id],
    )
    assert len(hits) >= 1
    assert any("monorepo" in h.content.lower() for h in hits)
    assert all(h.bank_id == Banks.PRECEDENTS for h in hits)
