"""Pure async analytics query functions.

All functions accept an AsyncSession and tenant_id; they return plain Python
structures (lists of dicts / dicts) so the router can serialise them freely.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.db.models import CouncilSession


async def member_leaderboard(
    db: AsyncSession,
    tenant_id: str | None,
    limit: int = 20,
) -> list[dict]:
    """Return per-member participation stats across all closed councils.

    Uses jsonb_array_elements to explode the ``members`` JSONB array, then
    aggregates by the member's ``id`` field.  Falls back to the member ``name``
    field from the first occurrence.
    """
    tenant_clause = "AND cs.tenant_id = :tenant_id" if tenant_id is not None else ""

    query = text(
        f"""
        WITH exploded AS (
            SELECT
                cs.id                             AS council_id,
                cs.consensus_score                AS consensus_score,
                cs.dissent_detected               AS dissent_detected,
                m.value ->> 'id'                  AS member_id,
                m.value ->> 'name'                AS member_name
            FROM council_sessions cs,
                 jsonb_array_elements(cs.members) AS m(value)
            WHERE cs.status = 'closed'
            {tenant_clause}
        ),
        agg AS (
            SELECT
                member_id,
                -- take the first non-null name encountered
                (array_agg(member_name ORDER BY member_name) FILTER (WHERE member_name IS NOT NULL))[1]
                    AS member_name,
                COUNT(*)                          AS councils_participated,
                AVG(consensus_score)              AS avg_consensus_score,
                COUNT(*) FILTER (WHERE dissent_detected)
                    AS dissent_count
            FROM exploded
            WHERE member_id IS NOT NULL
            GROUP BY member_id
        )
        SELECT
            member_id,
            member_name,
            councils_participated,
            avg_consensus_score,
            dissent_count
        FROM agg
        ORDER BY councils_participated DESC,
                 avg_consensus_score   DESC NULLS LAST
        LIMIT :limit
        """
    )

    params: dict = {"limit": limit}
    if tenant_id is not None:
        params["tenant_id"] = tenant_id

    result = await db.execute(query, params)
    rows = result.mappings().all()

    return [
        {
            "member_id": row["member_id"],
            "member_name": row["member_name"],
            "councils_participated": int(row["councils_participated"]),
            "avg_consensus_score": (
                float(row["avg_consensus_score"])
                if row["avg_consensus_score"] is not None
                else None
            ),
            "dissent_count": int(row["dissent_count"]),
        }
        for row in rows
    ]


async def decision_velocity(
    db: AsyncSession,
    tenant_id: str | None,
    days: int = 30,
) -> list[dict]:
    """Count closed councils per calendar day for the past *days* days.

    Days with zero councils are included (zero-filled in Python).
    """
    tenant_clause = "AND tenant_id = :tenant_id" if tenant_id is not None else ""

    query = text(
        f"""
        SELECT
            DATE(closed_at AT TIME ZONE 'UTC') AS day,
            COUNT(*)                           AS cnt
        FROM council_sessions
        WHERE status = 'closed'
          AND closed_at >= NOW() - INTERVAL '{days} days'
          {tenant_clause}
        GROUP BY day
        ORDER BY day
        """
    )

    params: dict = {}
    if tenant_id is not None:
        params["tenant_id"] = tenant_id

    result = await db.execute(query, params)
    rows = result.mappings().all()

    # Build a lookup from the DB rows
    counts_by_day: dict[str, int] = {str(row["day"]): int(row["cnt"]) for row in rows}

    # Zero-fill every calendar day in the window
    today = datetime.now(UTC).date()
    output: list[dict] = []
    for offset in range(days, -1, -1):
        day = today - timedelta(days=offset)
        day_str = str(day)
        output.append({"date": day_str, "count": counts_by_day.get(day_str, 0)})

    return output


async def consensus_distribution(
    db: AsyncSession,
    tenant_id: str | None,
) -> dict:
    """Bucket closed councils by consensus_score into high/medium/low/unscored."""
    stmt = select(CouncilSession.consensus_score).where(CouncilSession.status == "closed")
    if tenant_id is not None:
        stmt = stmt.where(CouncilSession.tenant_id == tenant_id)

    result = await db.execute(stmt)
    scores = [row[0] for row in result.all()]

    high = medium = low = unscored = 0
    for score in scores:
        if score is None:
            unscored += 1
        elif score >= 0.75:
            high += 1
        elif score >= 0.5:
            medium += 1
        else:
            low += 1

    return {
        "high": high,
        "medium": medium,
        "low": low,
        "unscored": unscored,
        "total": len(scores),
    }


async def topic_summary(
    db: AsyncSession,
    tenant_id: str | None,
    limit: int = 50,
) -> list[dict]:
    """Aggregate closed councils by topic_tag, sorted by count DESC."""
    stmt = (
        select(
            CouncilSession.topic_tag,
            func.count().label("count"),
            func.avg(CouncilSession.consensus_score).label("avg_consensus"),
        )
        .where(CouncilSession.status == "closed")
        .group_by(CouncilSession.topic_tag)
        .order_by(func.count().desc())
        .limit(limit)
    )
    if tenant_id is not None:
        stmt = stmt.where(CouncilSession.tenant_id == tenant_id)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        {
            "topic_tag": row.topic_tag,
            "count": int(row.count),
            "avg_consensus": (float(row.avg_consensus) if row.avg_consensus is not None else None),
        }
        for row in rows
    ]
