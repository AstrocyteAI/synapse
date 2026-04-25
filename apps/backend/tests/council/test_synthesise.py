"""Tests for Stage 3: Synthesise."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from synapse.council.stages.synthesise import (
    _extract_confidence,
    _extract_uncertainty_markers,
    _rank_responses_for_chairman,
    _strip_confidence_footer,
    run_synthesise,
)

# ---------------------------------------------------------------------------
# _extract_confidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("My verdict here.\nCONFIDENCE: HIGH", "high"),
    ("Some text.\nCONFIDENCE: MEDIUM", "medium"),
    ("Uncertain outcome.\nCONFIDENCE: LOW", "low"),
    ("I strongly recommend this approach.", "high"),
    ("This is [UNCERTAIN] in some aspects.", "low"),
    ("A reasonable outcome overall.", "medium"),  # fallback
])
def test_extract_confidence(text, expected):
    assert _extract_confidence(text) == expected


# ---------------------------------------------------------------------------
# _extract_uncertainty_markers
# ---------------------------------------------------------------------------

def test_extract_uncertainty_markers_found():
    text = "The timeline is [UNCERTAIN] due to factors.\nThe cost [UNCERTAIN] as well."
    markers = _extract_uncertainty_markers(text)
    assert len(markers) == 2
    assert all("[UNCERTAIN]" in m for m in markers)


def test_extract_uncertainty_markers_none():
    assert _extract_uncertainty_markers("Clear and certain verdict.") == []


# ---------------------------------------------------------------------------
# _strip_confidence_footer
# ---------------------------------------------------------------------------

def test_strip_confidence_footer():
    text = "My verdict text.\nCONFIDENCE: HIGH"
    result = _strip_confidence_footer(text)
    assert "CONFIDENCE" not in result
    assert "My verdict text." in result


def test_strip_confidence_footer_no_footer():
    text = "No footer here."
    assert _strip_confidence_footer(text) == text


# ---------------------------------------------------------------------------
# _rank_responses_for_chairman
# ---------------------------------------------------------------------------

def test_rank_responses_for_chairman_ordered_by_score(
    sample_stage1_responses, sample_ranking_result
):
    ranked = _rank_responses_for_chairman(sample_stage1_responses, sample_ranking_result)
    # Response A (score 1.0) should appear before Response B (score 2.0)
    pos_a = ranked.find("Response A content")
    pos_b = ranked.find("Response B content")
    assert pos_a < pos_b


# ---------------------------------------------------------------------------
# run_synthesise
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_synthesise_returns_synthesis(
    default_chairman, sample_stage1_responses, sample_ranking_result
):
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value="Based on the responses, we should proceed.\nCONFIDENCE: HIGH"
    )

    result = await run_synthesise(
        chairman=default_chairman,
        stage1_responses=sample_stage1_responses,
        ranking_result=sample_ranking_result,
        question="What should we do?",
        llm=llm,
        timeout=10.0,
    )
    assert result.verdict == "Based on the responses, we should proceed."
    assert result.confidence_label == "high"
    assert result.uncertainty_markers == []


@pytest.mark.asyncio
async def test_run_synthesise_captures_uncertainty_markers(
    default_chairman, sample_stage1_responses, sample_ranking_result
):
    llm = AsyncMock()
    llm.complete = AsyncMock(
        return_value=(
            "Proceed but note [UNCERTAIN] timeline risk.\n"
            "CONFIDENCE: MEDIUM"
        )
    )

    result = await run_synthesise(
        chairman=default_chairman,
        stage1_responses=sample_stage1_responses,
        ranking_result=sample_ranking_result,
        question="Q?",
        llm=llm,
        timeout=10.0,
    )
    assert result.confidence_label == "medium"
    assert len(result.uncertainty_markers) == 1
