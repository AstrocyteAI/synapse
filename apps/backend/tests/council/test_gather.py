"""Tests for Stage 1: Gather."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from synapse.council.models import CouncilMember, StageOneResponse
from synapse.council.stages.gather import (
    _build_system_prompt,
    _format_precedents,
    run_gather,
)
from synapse.memory.gateway_client import MemoryHit

# ---------------------------------------------------------------------------
# _format_precedents
# ---------------------------------------------------------------------------


def test_format_precedents_empty():
    assert _format_precedents([]) == ""


def test_format_precedents_includes_content():
    hits = [
        MemoryHit(
            memory_id="h1",
            content="Some past decision.",
            score=0.9,
            bank_id="precedents",
            tags=[],
            metadata={},
        )
    ]
    result = _format_precedents(hits)
    assert "Some past decision." in result
    assert "1." in result


def test_format_precedents_truncates_long_content():
    long_content = "x" * 600
    hits = [
        MemoryHit(
            memory_id="h1",
            content=long_content,
            score=0.8,
            bank_id="precedents",
            tags=[],
            metadata={},
        )
    ]
    result = _format_precedents(hits)
    # Should truncate at 500 chars
    assert "x" * 500 in result
    assert "x" * 501 not in result


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_includes_name():
    member = CouncilMember(model_id="openai/gpt-4o", name="MyBot")
    prompt = _build_system_prompt(member, [])
    assert "MyBot" in prompt


def test_build_system_prompt_includes_role():
    member = CouncilMember(model_id="openai/gpt-4o", name="Bot", role="Devil's advocate")
    prompt = _build_system_prompt(member, [])
    assert "Devil's advocate" in prompt


def test_build_system_prompt_override():
    member = CouncilMember(
        model_id="openai/gpt-4o",
        name="Bot",
        system_prompt_override="Be concise.",
    )
    prompt = _build_system_prompt(member, [])
    assert prompt == "Be concise."


def test_build_system_prompt_with_precedents():
    member = CouncilMember(model_id="openai/gpt-4o", name="Bot")
    hits = [
        MemoryHit(
            memory_id="h1",
            content="Prior ruling.",
            score=0.85,
            bank_id="precedents",
            tags=[],
            metadata={},
        )
    ]
    prompt = _build_system_prompt(member, hits)
    assert "Prior ruling." in prompt


# ---------------------------------------------------------------------------
# run_gather
# ---------------------------------------------------------------------------


@pytest.fixture
def two_members():
    return [
        CouncilMember(model_id="openai/gpt-4o", name="GPT"),
        CouncilMember(model_id="anthropic/claude-3-5-sonnet-20241022", name="Claude"),
    ]


@pytest.mark.asyncio
async def test_run_gather_returns_responses_for_all_members(two_members, mock_llm):
    responses = await run_gather(
        members=two_members,
        question="What should we do?",
        precedents=[],
        llm=mock_llm,
        timeout=10.0,
    )
    assert len(responses) == 2
    assert all(isinstance(r, StageOneResponse) for r in responses)
    assert all(r.content == "This is a mock LLM response.\nCONFIDENCE: HIGH" for r in responses)


@pytest.mark.asyncio
async def test_run_gather_excludes_failed_members(two_members):
    llm = AsyncMock()
    call_count = 0

    async def _side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM error")
        return "Good response"

    llm.complete = AsyncMock(side_effect=_side_effect)

    responses = await run_gather(
        members=two_members,
        question="Q?",
        precedents=[],
        llm=llm,
        timeout=10.0,
    )
    assert len(responses) == 1
    assert responses[0].content == "Good response"


@pytest.mark.asyncio
async def test_run_gather_raises_if_all_fail(two_members):
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("total failure"))

    with pytest.raises(RuntimeError, match="All council members failed"):
        await run_gather(
            members=two_members,
            question="Q?",
            precedents=[],
            llm=llm,
            timeout=10.0,
        )


@pytest.mark.asyncio
async def test_run_gather_handles_timeout(two_members):
    llm = AsyncMock()

    async def _hang(**kwargs):
        await asyncio.sleep(99)

    llm.complete = AsyncMock(side_effect=_hang)

    # Only one member, so all fail → raises
    with pytest.raises(RuntimeError, match="All council members failed"):
        await run_gather(
            members=[two_members[0]],
            question="Q?",
            precedents=[],
            llm=llm,
            timeout=0.05,
        )
