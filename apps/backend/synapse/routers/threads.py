"""Threads router — message send and history retrieval."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.council.thread import append_event, get_history, get_thread, thread_event_dict
from synapse.db.models import Thread, ThreadEvent, ThreadEventType
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
    thread = await _load_thread(db, thread_id, user)
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

    payload = thread_event_dict(event)
    await _publish(request, thread_id, payload)
    return payload


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

    thread = await _load_thread(db, thread_id, user)
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

    items = [thread_event_dict(e) for e in events]
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
    """Belt-and-braces tenant check kept around even though
    ``_load_thread`` now pre-filters at the repo layer. Combined effect
    is defense-in-depth — a future code path that fetches a thread
    without going through ``_load_thread`` still cannot leak
    cross-tenant data."""
    if "admin" in (user.roles or []):
        return
    if user.tenant_id and thread.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")


async def _load_thread(db: AsyncSession, thread_id, user: AuthenticatedUser):
    """Tenant-scoped thread fetch — admins bypass the filter."""
    if "admin" in (user.roles or []):
        return await get_thread(db, thread_id)
    return await get_thread(db, thread_id, tenant_id=user.tenant_id)


def _display_name(user: AuthenticatedUser) -> str:
    return user.raw_claims.get("name") or user.raw_claims.get("preferred_username") or user.sub


async def _publish(request: Request, thread_id: uuid.UUID, payload: dict) -> None:
    """Best-effort Centrifugo publish — never raises (DB write already succeeded)."""
    try:
        await request.app.state.centrifugo.publish(f"thread:{thread_id}", payload)
    except Exception:
        _logger.warning("Centrifugo publish failed for thread %s", thread_id, exc_info=True)


# ---------------------------------------------------------------------------
# S-MIG-THREADS — admin export endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/admin/threads",
    summary="[Migration export] List all threads with their event timelines (admin only)",
)
async def admin_list_threads(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Dump every thread with its full append-only event log.

    Pagination is over threads, not events. Each thread carries
    ``events: [...]`` with every event in id-ascending order. Operators
    importing into a different backend should preserve event ordering
    (the BIGSERIAL `id` is the canonical sort key).

    Limit caps at 200 threads per page because each thread can carry
    hundreds of events; a thread-of-the-day with 500 events × 200
    threads is already a 100K-row payload.
    """
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="admin role required")

    async with request.app.state.sessionmaker() as db:
        stmt = (
            select(Thread)
            .options(selectinload(Thread.events))
            .order_by(Thread.created_at)
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        threads = list(result.scalars().all())

    return {
        "count": len(threads),
        "data": [_thread_export_dict(t) for t in threads],
    }


def _thread_export_dict(thread: Thread) -> dict[str, Any]:
    return {
        "id": str(thread.id),
        "council_id": str(thread.council_id) if thread.council_id else None,
        "tenant_id": thread.tenant_id,
        "created_by": thread.created_by,
        "title": thread.title,
        "created_at": thread.created_at.isoformat(),
        "events": [_thread_event_export_dict(e) for e in thread.events],
    }


def _thread_event_export_dict(event: ThreadEvent) -> dict[str, Any]:
    """Thread-event shape for the migration bundle.

    Mirrors ``thread_event_dict`` from the realtime path but keeps the
    BIGSERIAL ``id`` (so importers can preserve ordering) and renames
    ``event_metadata`` → ``metadata`` to match the schema's
    SynapseThreadEvent shape.
    """
    return {
        "id": event.id,
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "actor_name": event.actor_name,
        "content": event.content,
        "metadata": event.event_metadata or {},
        "created_at": event.created_at.isoformat(),
    }
