"""Tests for Stage 2: Rank."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from synapse.council.models import MemberRanking, StageOneResponse
from synapse.council.stages.rank import (
    _anonymise,
    _compute_aggregate_scores,
    _compute_kendalls_w,
    _parse_ranking,
    run_rank,
)

# ---------------------------------------------------------------------------
# _anonymise
# ---------------------------------------------------------------------------


def test_anonymise_labels_a_b_c():
    responses = [
        StageOneResponse(member_id="m1", member_name="One", content="aaa"),
        StageOneResponse(member_id="m2", member_name="Two", content="bbb"),
        StageOneResponse(member_id="m3", member_name="Three", content="ccc"),
    ]
    anon, label_map = _anonymise(responses)
    assert [a["label"] for a in anon] == ["Response A", "Response B", "Response C"]
    assert label_map["Response A"] == "m1"
    assert label_map["Response C"] == "m3"
    # Content is preserved
    assert anon[0]["content"] == "aaa"


# ---------------------------------------------------------------------------
# _parse_ranking
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_first",
    [
        ("FINAL RANKING:\n1. Response B\n2. Response A", "Response B"),
        ("I think Response A is best.\nFINAL RANKING:\n1. Response A\n2. Response B", "Response A"),
        # Fallback: no FINAL RANKING section
        ("Response B was clearly superior to Response A.", "Response B"),
    ],
)
def test_parse_ranking(text, expected_first):
    labels = ["A", "B"]
    result = _parse_ranking(text, labels)
    assert result[0] == expected_first


def test_parse_ranking_fills_missing_labels():
    labels = ["A", "B", "C"]
    text = "FINAL RANKING:\n1. Response A"  # B and C missing
    result = _parse_ranking(text, labels)
    assert "Response B" in result
    assert "Response C" in result
    assert len(result) == 3


# ---------------------------------------------------------------------------
# _compute_aggregate_scores
# ---------------------------------------------------------------------------


def test_compute_aggregate_scores_perfect_agreement():
    rankings = [
        MemberRanking(
            member_id="m1", member_name="M1", ranking=["Response A", "Response B"], raw_response=""
        ),
        MemberRanking(
            member_id="m2", member_name="M2", ranking=["Response A", "Response B"], raw_response=""
        ),
    ]
    scores = _compute_aggregate_scores(rankings, ["A", "B"])
    assert scores["Response A"] == 1.0
    assert scores["Response B"] == 2.0


def test_compute_aggregate_scores_split_vote():
    rankings = [
        MemberRanking(
            member_id="m1", member_name="M1", ranking=["Response A", "Response B"], raw_response=""
        ),
        MemberRanking(
            member_id="m2", member_name="M2", ranking=["Response B", "Response A"], raw_response=""
        ),
    ]
    scores = _compute_aggregate_scores(rankings, ["A", "B"])
    assert scores["Response A"] == scores["Response B"] == 1.5


# ---------------------------------------------------------------------------
# _compute_kendalls_w
# ---------------------------------------------------------------------------


def test_kendalls_w_perfect_agreement():
    rankings = [
        MemberRanking(
            member_id="m1",
            member_name="M1",
            ranking=["Response A", "Response B", "Response C"],
            raw_response="",
        ),
        MemberRanking(
            member_id="m2",
            member_name="M2",
            ranking=["Response A", "Response B", "Response C"],
            raw_response="",
        ),
        MemberRanking(
            member_id="m3",
            member_name="M3",
            ranking=["Response A", "Response B", "Response C"],
            raw_response="",
        ),
    ]
    w = _compute_kendalls_w(rankings, ["A", "B", "C"])
    assert w == pytest.approx(1.0, abs=0.01)


def test_kendalls_w_no_agreement():
    # Three raters, three items — reverse orders
    rankings = [
        MemberRanking(
            member_id="m1",
            member_name="M1",
            ranking=["Response A", "Response B", "Response C"],
            raw_response="",
        ),
        MemberRanking(
            member_id="m2",
            member_name="M2",
            ranking=["Response B", "Response C", "Response A"],
            raw_response="",
        ),
        MemberRanking(
            member_id="m3",
            member_name="M3",
            ranking=["Response C", "Response A", "Response B"],
            raw_response="",
        ),
    ]
    w = _compute_kendalls_w(rankings, ["A", "B", "C"])
    assert 0.0 <= w <= 1.0


def test_kendalls_w_single_rater_returns_one():
    rankings = [
        MemberRanking(
            member_id="m1", member_name="M1", ranking=["Response A", "Response B"], raw_response=""
        ),
    ]
    w = _compute_kendalls_w(rankings, ["A", "B"])
    assert w == 1.0


def test_kendalls_w_single_item_returns_one():
    rankings = [
        MemberRanking(member_id="m1", member_name="M1", ranking=["Response A"], raw_response=""),
        MemberRanking(member_id="m2", member_name="M2", ranking=["Response A"], raw_response=""),
    ]
    w = _compute_kendalls_w(rankings, ["A"])
    assert w == 1.0


# ---------------------------------------------------------------------------
# run_rank
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_rank_returns_ranking_result(sample_stage1_responses, default_members):
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value="Response B is better.\nFINAL RANKING:\n1. Response B\n2. Response A"
    )

    result = await run_rank(
        members=default_members,
        stage1_responses=sample_stage1_responses,
        llm=llm,
        timeout=10.0,
    )
    assert result.consensus_score is not None
    assert "Response A" in result.aggregate_scores
    assert "Response B" in result.aggregate_scores
    assert len(result.member_rankings) == 2


@pytest.mark.asyncio
async def test_run_rank_fallback_on_all_failure(sample_stage1_responses, default_members):
    llm = AsyncMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

    result = await run_rank(
        members=default_members,
        stage1_responses=sample_stage1_responses,
        llm=llm,
        timeout=10.0,
    )
    # Fallback identity ranking
    assert len(result.member_rankings) == 1
    assert result.member_rankings[0].member_id == "fallback"
