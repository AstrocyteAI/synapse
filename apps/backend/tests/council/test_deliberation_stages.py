"""Tests for critique, revise, and red-team deliberation stages."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from synapse.council.models import CouncilMember, MemberCritique, StageOneResponse
from synapse.council.stages.critique import _format_other_responses, run_critique
from synapse.council.stages.red_team import run_red_team
from synapse.council.stages.revise import _format_critiques, run_revise

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _member(model_id: str, name: str = "", role: str = "") -> CouncilMember:
    return CouncilMember(model_id=model_id, name=name or model_id, role=role)


def _resp(member_id: str, content: str = "some content") -> StageOneResponse:
    return StageOneResponse(member_id=member_id, member_name=member_id, content=content)


def _critique(member_id: str, critique: str = "good points", error=None) -> MemberCritique:
    return MemberCritique(
        member_id=member_id, member_name=member_id, critique=critique, error=error
    )


# ---------------------------------------------------------------------------
# _format_other_responses
# ---------------------------------------------------------------------------


def test_format_other_responses_excludes_self():
    responses = [_resp("m1", "alpha"), _resp("m2", "beta"), _resp("m3", "gamma")]
    result = _format_other_responses("m1", responses)
    assert "alpha" not in result
    assert "beta" in result
    assert "gamma" in result


def test_format_other_responses_empty_when_only_self():
    responses = [_resp("m1", "solo")]
    result = _format_other_responses("m1", responses)
    assert "no other responses" in result


# ---------------------------------------------------------------------------
# _format_critiques
# ---------------------------------------------------------------------------


def test_format_critiques_excludes_self():
    critiques = [_critique("m1", "self crit"), _critique("m2", "peer crit")]
    result = _format_critiques("m1", critiques)
    assert "self crit" not in result
    assert "peer crit" in result


def test_format_critiques_excludes_errors():
    critiques = [_critique("m2", "", error="timeout"), _critique("m3", "valid critique")]
    result = _format_critiques("m1", critiques)
    assert "valid critique" in result
    # Error critique has empty text, should be excluded
    assert result.count("Critique") == 1


# ---------------------------------------------------------------------------
# run_critique
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_critique_returns_one_per_member():
    members = [_member("m1"), _member("m2"), _member("m3")]
    responses = [_resp("m1", "ans1"), _resp("m2", "ans2"), _resp("m3", "ans3")]
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="This response misses key points.")

    results = await run_critique(members, "Should we migrate?", responses, mock_llm, timeout=10)

    assert len(results) == 3
    for r in results:
        assert isinstance(r, MemberCritique)
        assert r.critique == "This response misses key points."
        assert r.error is None


@pytest.mark.asyncio
async def test_run_critique_handles_member_failure():
    members = [_member("m1"), _member("m2")]
    responses = [_resp("m1", "ans1"), _resp("m2", "ans2")]
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=Exception("LLM error"))

    results = await run_critique(members, "Question?", responses, mock_llm, timeout=10)

    assert len(results) == 2
    for r in results:
        assert r.error is not None
        assert r.critique == ""


# ---------------------------------------------------------------------------
# run_revise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_revise_returns_one_per_member():
    members = [_member("m1"), _member("m2")]
    responses = [_resp("m1", "original1"), _resp("m2", "original2")]
    critiques = [_critique("m1", "m1 crit"), _critique("m2", "m2 crit")]
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="Revised: I now agree with the critique.")

    results = await run_revise(members, "Question?", responses, critiques, mock_llm, timeout=10)

    assert len(results) == 2
    for r in results:
        assert isinstance(r, StageOneResponse)
        assert r.content == "Revised: I now agree with the critique."
        assert r.error is None


@pytest.mark.asyncio
async def test_run_revise_keeps_previous_on_failure():
    members = [_member("m1")]
    responses = [_resp("m1", "keep this")]
    critiques = [_critique("m2", "some feedback")]
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=TimeoutError())

    results = await run_revise(members, "Q?", responses, critiques, mock_llm, timeout=10)

    assert len(results) == 1
    # Previous response preserved on failure
    assert results[0].content == "keep this"
    assert results[0].error is not None


# ---------------------------------------------------------------------------
# run_red_team
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_red_team_returns_attacks():
    members = [_member("r1"), _member("r2")]
    responses = [_resp("r1", "proposal1"), _resp("r2", "proposal2")]
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value="This proposal fails because of X.")

    results = await run_red_team(members, "Should we launch?", responses, mock_llm, timeout=10)

    assert len(results) == 2
    for r in results:
        assert isinstance(r, MemberCritique)
        assert r.critique == "This proposal fails because of X."


@pytest.mark.asyncio
async def test_run_red_team_graceful_failure():
    members = [_member("r1"), _member("r2")]
    responses = [_resp("r1", "p1"), _resp("r2", "p2")]
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(side_effect=RuntimeError("boom"))

    results = await run_red_team(members, "Q?", responses, mock_llm, timeout=10)

    assert len(results) == 2
    for r in results:
        assert r.error is not None
