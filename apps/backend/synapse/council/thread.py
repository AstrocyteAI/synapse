"""Thread CRUD helpers — create threads, append events, query history."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.db.models import Thread, ThreadEvent


async def create_thread(
    db: AsyncSession,
    *,
    council_id: uuid.UUID | None = None,
    created_by: str,
    tenant_id: str | None = None,
    title: str | None = None,
) -> Thread:
    """Create a new thread, optionally linked to a council session."""
    thread = Thread(
        id=uuid.uuid4(),
        council_id=council_id,
        created_by=created_by,
        tenant_id=tenant_id,
        title=title,
    )
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


async def get_thread(
    db: AsyncSession,
    thread_id: uuid.UUID,
) -> Thread | None:
    return await db.get(Thread, thread_id)


async def get_thread_by_council(
    db: AsyncSession,
    council_id: uuid.UUID,
) -> Thread | None:
    result = await db.execute(
        select(Thread).where(Thread.council_id == council_id)
    )
    return result.scalar_one_or_none()


async def append_event(
    db: AsyncSession,
    *,
    thread_id: uuid.UUID,
    event_type: str,
    actor_id: str,
    actor_name: str = "",
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ThreadEvent:
    """Append a single event to the thread log and return it.

    The ``id`` (BIGSERIAL) is assigned by Postgres — never set by the caller.
    """
    event = ThreadEvent(
        thread_id=thread_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_name=actor_name,
        content=content,
        metadata=metadata or {},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_history(
    db: AsyncSession,
    thread_id: uuid.UUID,
    *,
    before_id: int | None = None,
    after_id: int | None = None,
    limit: int = 50,
) -> list[ThreadEvent]:
    """Cursor-paginated thread history — never uses SQL OFFSET.

    - ``before_id``: return the ``limit`` events with id < before_id, newest first.
      Used for loading older history (scrolling up).
    - ``after_id``: return the ``limit`` events with id > after_id, oldest first.
      Used for catching up after a reconnect.
    - Neither: return the most recent ``limit`` events, newest first.

    Callers should reverse the list when displaying in chronological order.
    """
    stmt = select(ThreadEvent).where(ThreadEvent.thread_id == thread_id)

    if before_id is not None:
        stmt = stmt.where(ThreadEvent.id < before_id).order_by(ThreadEvent.id.desc())
    elif after_id is not None:
        stmt = stmt.where(ThreadEvent.id > after_id).order_by(ThreadEvent.id.asc())
    else:
        stmt = stmt.order_by(ThreadEvent.id.desc())

    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
