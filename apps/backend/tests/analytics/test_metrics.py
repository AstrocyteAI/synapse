"""Unit tests for synapse.analytics.metrics — B8."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from synapse.analytics.metrics import (
    consensus_distribution,
    decision_velocity,
    member_leaderboard,
    topic_summary,
)

# ---------------------------------------------------------------------------
# Helpers — async mock DB session factories
# ---------------------------------------------------------------------------


def _make_db(rows=None, mappings=None):
    """Return an AsyncSession mock whose execute() returns rows or mappings."""
    db = AsyncMock()
    result = MagicMock()

    if mappings is not None:
        result.mappings.return_value.all.return_value = mappings
    else:
        result.all.return_value = rows or []

    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# member_leaderboard — query structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_leaderboard_query_structure():
    rows = [
        {
            "member_id": "m1",
            "member_name": "Alice",
            "councils_participated": 3,
            "avg_consensus_score": 0.75,
            "dissent_count": 1,
        },
        {
            "member_id": "m2",
            "member_name": "Bob",
            "councils_participated": 1,
            "avg_consensus_score": None,
            "dissent_count": 0,
        },
    ]
    db = _make_db(mappings=rows)

    result = await member_leaderboard(db, tenant_id="t1")

    assert isinstance(result, list)
    assert len(result) == 2

    first = result[0]
    for key in (
        "member_id",
        "member_name",
        "councils_participated",
        "avg_consensus_score",
        "dissent_count",
    ):
        assert key in first, f"Missing key: {key}"

    assert first["member_id"] == "m1"
    assert first["councils_participated"] == 3
    assert first["avg_consensus_score"] == 0.75

    second = result[1]
    assert second["avg_consensus_score"] is None


# ---------------------------------------------------------------------------
# consensus_distribution — bucket math
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consensus_distribution_buckets():
    # Simulate 6 closed sessions: high=2, medium=1, low=1, unscored=2
    scores = [0.9, 0.8, 0.6, 0.3, None, None]

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [(s,) for s in scores]
    db.execute = AsyncMock(return_value=mock_result)

    dist = await consensus_distribution(db, tenant_id=None)

    assert dist["high"] == 2
    assert dist["medium"] == 1
    assert dist["low"] == 1
    assert dist["unscored"] == 2
    assert dist["total"] == 6


@pytest.mark.asyncio
async def test_consensus_distribution_empty():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    dist = await consensus_distribution(db, tenant_id="t1")

    assert dist == {"high": 0, "medium": 0, "low": 0, "unscored": 0, "total": 0}


# ---------------------------------------------------------------------------
# decision_velocity — zero-fill logic
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decision_velocity_fills_zero_days():
    # Use a relative date so the test stays valid regardless of when it runs.
    data_day = (datetime.now(UTC).date() - timedelta(days=3)).isoformat()

    # DB only returns 1 day with data; remaining days must be zero-filled
    rows = [{"day": data_day, "cnt": 5}]
    db = _make_db(mappings=rows)

    result = await decision_velocity(db, tenant_id=None, days=7)

    assert isinstance(result, list)
    # 7 days + today = 8 entries
    assert len(result) == 8

    # All entries have the expected shape
    for entry in result:
        assert "date" in entry
        assert "count" in entry
        assert isinstance(entry["count"], int)

    # The one day with data must have count=5
    day_map = {e["date"]: e["count"] for e in result}
    assert day_map.get(data_day) == 5

    # All other days must have count=0
    zero_days = [e for e in result if e["date"] != data_day]
    assert all(e["count"] == 0 for e in zero_days)


@pytest.mark.asyncio
async def test_decision_velocity_all_zero_when_no_data():
    db = _make_db(mappings=[])
    result = await decision_velocity(db, tenant_id="t1", days=3)

    assert len(result) == 4  # 3 past days + today
    assert all(e["count"] == 0 for e in result)


# ---------------------------------------------------------------------------
# topic_summary — basic shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_topic_summary_returns_expected_shape():
    Row = MagicMock
    r1 = Row()
    r1.topic_tag = "product"
    r1.count = 4
    r1.avg_consensus = 0.78

    r2 = Row()
    r2.topic_tag = None
    r2.count = 2
    r2.avg_consensus = None

    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [r1, r2]
    db.execute = AsyncMock(return_value=mock_result)

    result = await topic_summary(db, tenant_id=None)

    assert len(result) == 2
    assert result[0]["topic_tag"] == "product"
    assert result[0]["count"] == 4
    assert abs(result[0]["avg_consensus"] - 0.78) < 1e-6
    assert result[1]["topic_tag"] is None
    assert result[1]["avg_consensus"] is None
