"""Analytics router — B8: powers the W7 web dashboard."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.analytics.clustering import cluster_topics
from synapse.analytics.metrics import (
    consensus_distribution,
    decision_velocity,
    member_leaderboard,
    topic_summary,
)
from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.db.session import get_session as get_db_session
from synapse.memory.context import build_context

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


# ---------------------------------------------------------------------------
# GET /v1/analytics/members
# ---------------------------------------------------------------------------


@router.get("/analytics/members", summary="Member participation leaderboard")
async def get_member_leaderboard(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    try:
        data = await member_leaderboard(db, tenant_id=user.tenant_id, limit=limit)
    except Exception as exc:
        _logger.exception("analytics/members query failed")
        raise HTTPException(status_code=500, detail="analytics query failed") from exc

    return {
        "data": data,
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": user.tenant_id,
    }


# ---------------------------------------------------------------------------
# GET /v1/analytics/velocity
# ---------------------------------------------------------------------------


@router.get("/analytics/velocity", summary="Decision velocity (closed councils per day)")
async def get_decision_velocity(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    try:
        data = await decision_velocity(db, tenant_id=user.tenant_id, days=days)
    except Exception as exc:
        _logger.exception("analytics/velocity query failed")
        raise HTTPException(status_code=500, detail="analytics query failed") from exc

    return {
        "data": data,
        "days": days,
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": user.tenant_id,
    }


# ---------------------------------------------------------------------------
# GET /v1/analytics/consensus
# ---------------------------------------------------------------------------


@router.get("/analytics/consensus", summary="Consensus score distribution")
async def get_consensus_distribution(
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    try:
        data = await consensus_distribution(db, tenant_id=user.tenant_id)
    except Exception as exc:
        _logger.exception("analytics/consensus query failed")
        raise HTTPException(status_code=500, detail="analytics query failed") from exc

    return {
        "data": data,
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": user.tenant_id,
    }


# ---------------------------------------------------------------------------
# GET /v1/analytics/topics
# ---------------------------------------------------------------------------


@router.get("/analytics/topics", summary="Topic tag summary with optional clustering")
async def get_topic_summary(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    cluster: bool = Query(default=False),
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    try:
        data = await topic_summary(db, tenant_id=user.tenant_id, limit=limit)
    except Exception as exc:
        _logger.exception("analytics/topics query failed")
        raise HTTPException(status_code=500, detail="analytics query failed") from exc

    response: dict = {
        "data": data,
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": user.tenant_id,
    }

    if cluster:
        tags = [row["topic_tag"] for row in data if row["topic_tag"] is not None]
        context = build_context(user)
        astrocyte = request.app.state.astrocyte
        clustering_result = await cluster_topics(astrocyte, context, tags)
        response["clusters"] = clustering_result["clusters"]
        response["cluster_sources"] = clustering_result["sources"]

    return response
