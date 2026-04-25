"""Threads router — message send and history retrieval."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.council.thread import append_event, get_history, get_thread
from synapse.db.models import ThreadEventType
from synapse.db.session import get_session as get_db_session

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["threads"])


class SendMessageRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# POST /v1/threads/{thread_id}/messages
# ---------------------------------------------------------------------------


@router.post(
    "/threads/{thread_id}/messages",
    status_code=status.HTTP_201_CREATED,
    summary="Send a user message to a thread (Mode 1 + 2)",
)
async def send_message(
    thread_id: uuid.UUID,
    body: SendMessageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    thread = await get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    _assert_thread_access(thread, user)

    event = await append_event(
        db,
        thread_id=thread_id,
        event_type=ThreadEventType.user_message,
        actor_id=user.principal,
        actor_name=_display_name(user),
        content=body.content,
    )
    return _event_dict(event)


# ---------------------------------------------------------------------------
# GET /v1/threads/{thread_id}/events
# ---------------------------------------------------------------------------


@router.get(
    "/threads/{thread_id}/events",
    summary="Paginated thread history (cursor-based — use before_id or after_id)",
)
async def list_events(
    thread_id: uuid.UUID,
    request: Request,
    before_id: int | None = None,
    after_id: int | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 200")

    thread = await get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    _assert_thread_access(thread, user)

    events = await get_history(
        db,
        thread_id,
        before_id=before_id,
        after_id=after_id,
        limit=limit,
    )

    items = [_event_dict(e) for e in events]
    return {
        "thread_id": str(thread_id),
        "events": items,
        "next_before_id": items[-1]["id"]
        if items and before_id is None and after_id is None
        else None,
        "count": len(items),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _assert_thread_access(thread, user: AuthenticatedUser) -> None:
    if "admin" in (user.roles or []):
        return
    if user.tenant_id and thread.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")


def _display_name(user: AuthenticatedUser) -> str:
    return user.raw_claims.get("name") or user.raw_claims.get("preferred_username") or user.sub


def _event_dict(event) -> dict:
    return {
        "id": event.id,
        "thread_id": str(event.thread_id),
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "actor_name": event.actor_name,
        "content": event.content,
        "metadata": event.metadata,
        "created_at": event.created_at.isoformat(),
    }
