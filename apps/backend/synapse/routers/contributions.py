"""Contributions router — POST /v1/councils/{id}/contribute (B3)."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.council.models import ContributeRequest
from synapse.council.orchestrator import CouncilOrchestrator
from synapse.council.session import add_contribution, get_session, quorum_met
from synapse.db.models import CouncilStatus
from synapse.db.session import get_session as get_db_session
from synapse.llm.client import LLMClient

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["contributions"])


def _get_orchestrator(request: Request) -> CouncilOrchestrator:
    return CouncilOrchestrator(
        astrocyte=request.app.state.astrocyte,
        centrifugo=request.app.state.centrifugo,
        llm=LLMClient(request.app.state.settings),
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
    )


@router.post(
    "/councils/{session_id}/contribute",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a contribution to an async council (B3)",
)
async def contribute(
    session_id: uuid.UUID,
    body: ContributeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Post a human (or external agent) contribution to an async council.

    The council must be in ``waiting_contributions`` status.  When the
    contribution pushes the session past quorum, Stage 2+3 fires in the
    background and the session transitions through ``stage_2`` → ``stage_3``
    → ``closed`` (or ``pending_approval`` if a conflict is detected).

    Returns ``quorum_met: true`` in the response body when synthesis has
    been triggered.
    """
    council = await get_session(db, session_id)
    if not council:
        raise HTTPException(status_code=404, detail="Council session not found")

    if council.status != CouncilStatus.waiting_contributions:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Council is not accepting contributions "
                f"(status: {council.status}). "
                "Only 'waiting_contributions' sessions accept new contributions."
            ),
        )

    # Persist the contribution
    council = await add_contribution(db, session_id, body, member_type="human")

    met = quorum_met(council)
    if met:
        orchestrator = _get_orchestrator(request)

        async def _resume() -> None:
            async with request.app.state.sessionmaker() as bg_db:
                try:
                    await orchestrator.resume(session_id, bg_db)
                except Exception as exc:
                    _logger.error(
                        "Resume failed for council %s after contribution: %s",
                        session_id,
                        exc,
                    )
                    from synapse.council.session import mark_failed

                    async with request.app.state.sessionmaker() as err_db:
                        await mark_failed(err_db, session_id, error=str(exc))

        asyncio.create_task(_resume())

    return {
        "session_id": str(session_id),
        "contributions_received": len(council.contributions),
        "quorum": council.quorum or len(council.members),
        "quorum_met": met,
    }
