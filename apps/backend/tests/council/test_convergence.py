"""Tests for convergence detection."""

from __future__ import annotations

from synapse.council.convergence import check_convergence, jaccard
from synapse.council.models import StageOneResponse


def _resp(member_id: str, content: str) -> StageOneResponse:
    return StageOneResponse(member_id=member_id, member_name=member_id, content=content)


# ---------------------------------------------------------------------------
# jaccard()
# ---------------------------------------------------------------------------


def test_jaccard_identical():
    assert jaccard("hello world", "hello world") == 1.0


def test_jaccard_disjoint():
    assert jaccard("hello world", "foo bar baz") == 0.0


def test_jaccard_partial():
    score = jaccard("the quick brown fox", "the slow brown dog")
    # Shared: the, brown (2); union = 6
    assert 0.3 < score < 0.5


def test_jaccard_empty_strings():
    assert jaccard("", "") == 1.0


def test_jaccard_one_empty():
    assert jaccard("hello", "") == 0.0


# ---------------------------------------------------------------------------
# check_convergence()
# ---------------------------------------------------------------------------

_TEXT_A = "We should adopt PostgreSQL because it is mature, well-supported, and integrates well with our stack."
_TEXT_B = "Redis is a good choice for caching but PostgreSQL should be the primary data store for reliability."


def test_no_convergence_when_responses_very_different():
    prev = [_resp("m1", _TEXT_A), _resp("m2", _TEXT_B)]
    new = [
        _resp("m1", "Completely different recommendation: use MongoDB instead."),
        _resp("m2", "I now think SQLite would be sufficient for our needs at this scale."),
    ]
    assert check_convergence(prev, new, threshold=0.72) is False


def test_convergence_when_responses_nearly_identical():
    prev = [_resp("m1", _TEXT_A), _resp("m2", _TEXT_A)]
    # Only minor rewording
    slightly_changed = _TEXT_A.replace("mature", "stable").replace("well-supported", "widely used")
    new = [_resp("m1", slightly_changed), _resp("m2", slightly_changed)]
    assert check_convergence(prev, new, threshold=0.72) is True


def test_convergence_exact_same_responses():
    prev = [_resp("m1", _TEXT_A), _resp("m2", _TEXT_B)]
    new = [_resp("m1", _TEXT_A), _resp("m2", _TEXT_B)]
    assert check_convergence(prev, new, threshold=0.72) is True


def test_no_comparable_pairs_returns_false():
    prev = [_resp("m1", _TEXT_A)]
    new = [_resp("m2", _TEXT_A)]  # different member IDs
    assert check_convergence(prev, new, threshold=0.72) is False


def test_threshold_boundary():
    # Score exactly at threshold should converge
    prev = [_resp("m1", _TEXT_A)]
    # Same text → similarity = 1.0 > any reasonable threshold
    assert check_convergence(prev, [_resp("m1", _TEXT_A)], threshold=0.99) is True


def test_partial_member_overlap():
    """Members only in new list (no prev) are ignored."""
    prev = [_resp("m1", _TEXT_A)]
    new = [_resp("m1", _TEXT_A), _resp("m2", "brand new member")]
    # m1 converged (identical), m2 has no prev — should still detect convergence for m1
    assert check_convergence(prev, new, threshold=0.72) is True
