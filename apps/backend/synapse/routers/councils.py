"""Councils router — CRUD + SSE stream for real-time updates."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.council.models import (
    CouncilMember,
    CouncilResult,
    CreateCouncilRequest,
)
from synapse.council.orchestrator import CouncilOrchestrator
from synapse.council.session import create_session, get_session, list_sessions, mark_failed
from synapse.db.models import CouncilStatus
from synapse.db.session import get_session as get_db_session
from synapse.llm.client import LLMClient
from synapse.memory.context import build_context

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["councils"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_orchestrator(request: Request) -> CouncilOrchestrator:
    return CouncilOrchestrator(
        astrocyte=request.app.state.astrocyte,
        centrifugo=request.app.state.centrifugo,
        llm=LLMClient(request.app.state.settings),
        settings=request.app.state.settings,
    )


def _resolve_members(
    request_members: list[CouncilMember] | None,
    settings,
) -> list[CouncilMember]:
    if request_members:
        return request_members
    return [CouncilMember(**m) for m in settings.default_members]


def _resolve_chairman(
    request_chairman: CouncilMember | None,
    settings,
) -> CouncilMember:
    if request_chairman:
        return request_chairman
    return CouncilMember(**settings.default_chairman)


# ---------------------------------------------------------------------------
# POST /v1/councils
# ---------------------------------------------------------------------------

@router.post(
    "/councils",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=dict,
    summary="Start a new council session",
)
async def create_council(
    body: CreateCouncilRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    settings = request.app.state.settings
    members = _resolve_members(body.members, settings)
    chairman = _resolve_chairman(body.chairman, settings)

    council_session = await create_session(
        db=db,
        request=body,
        members=members,
        chairman=chairman,
        created_by=user.principal,
        tenant_id=user.tenant_id,
    )
    session_id = council_session.id

    orchestrator = _get_orchestrator(request)
    context = build_context(user)

    async def _run() -> None:
        async with request.app.state.sessionmaker() as bg_db:
            try:
                await orchestrator.run(
                    session_id=session_id,
                    question=body.question,
                    members=members,
                    chairman=chairman,
                    context=context,
                    db=bg_db,
                    council_type=body.council_type,
                    topic_tag=body.topic_tag,
                )
            except Exception as exc:
                _logger.error("Council %s failed: %s", session_id, exc)
                async with request.app.state.sessionmaker() as err_db:
                    await mark_failed(err_db, session_id, error=str(exc))

    # Fire and forget — client polls or listens via Centrifugo/SSE
    asyncio.create_task(_run())

    return {"session_id": str(session_id), "status": CouncilStatus.pending}


# ---------------------------------------------------------------------------
# GET /v1/councils
# ---------------------------------------------------------------------------

@router.get(
    "/councils",
    summary="List council sessions for the current user",
)
async def list_councils(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict]:
    sessions = await list_sessions(
        db,
        tenant_id=user.tenant_id,
        created_by=user.principal,
        limit=limit,
        offset=offset,
    )
    return [_session_summary(s) for s in sessions]


# ---------------------------------------------------------------------------
# GET /v1/councils/{session_id}
# ---------------------------------------------------------------------------

@router.get(
    "/councils/{session_id}",
    summary="Get a council session by ID",
)
async def get_council(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Council session not found")
    _assert_owns(session, user)
    return _session_detail(session)


# ---------------------------------------------------------------------------
# GET /v1/councils/{session_id}/stream  — SSE fallback
# ---------------------------------------------------------------------------

@router.get(
    "/councils/{session_id}/stream",
    summary="SSE stream for council events (fallback — prefer Centrifugo WS)",
)
async def stream_council(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    session = await get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Council session not found")
    _assert_owns(session, user)

    async def _event_generator() -> AsyncIterator[str]:
        """Poll DB status every 1 s and emit SSE events until closed/failed."""
        last_status: str | None = None
        async with request.app.state.sessionmaker() as poll_db:
            while True:
                if await request.is_disconnected():
                    break
                s = await get_session(poll_db, session_id)
                if s is None:
                    break
                if s.status != last_status:
                    last_status = s.status
                    data = json.dumps({"status": s.status, "session_id": str(session_id)})
                    yield f"data: {data}\n\n"
                if s.status in (CouncilStatus.closed, CouncilStatus.failed):
                    if s.status == CouncilStatus.closed:
                        payload = json.dumps({
                            "event": "session_closed",
                            "verdict": s.verdict,
                            "consensus_score": s.consensus_score,
                            "confidence_label": s.confidence_label,
                        })
                        yield f"data: {payload}\n\n"
                    break
                await asyncio.sleep(1)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _assert_owns(session, user: AuthenticatedUser) -> None:
    # Admins can see all; otherwise enforce tenant + principal
    if "admin" in (user.roles or []):
        return
    if user.tenant_id and session.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")


def _session_summary(s) -> dict:
    return {
        "session_id": str(s.id),
        "question": s.question[:120] + "..." if len(s.question) > 120 else s.question,
        "status": s.status,
        "council_type": s.council_type,
        "confidence_label": s.confidence_label,
        "consensus_score": s.consensus_score,
        "created_at": s.created_at.isoformat(),
        "closed_at": s.closed_at.isoformat() if s.closed_at else None,
    }


def _session_detail(s) -> dict:
    return {
        "session_id": str(s.id),
        "question": s.question,
        "status": s.status,
        "council_type": s.council_type,
        "verdict": s.verdict,
        "confidence_label": s.confidence_label,
        "consensus_score": s.consensus_score,
        "dissent_detected": s.dissent_detected,
        "topic_tag": s.topic_tag,
        "template_id": s.template_id,
        "created_at": s.created_at.isoformat(),
        "closed_at": s.closed_at.isoformat() if s.closed_at else None,
        "members": s.members,
        "chairman": s.chairman,
    }
