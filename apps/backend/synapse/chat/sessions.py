"""Chat session service — CRUD operations on ChatSession + underlying Thread.

Tenant scoping is enforced at this layer (matching ``synapse.council.thread``).
Cross-tenant fetches return ``None`` so callers raise 404, not 403 — same
posture as the existing thread service.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.chat.api_models import ChatSessionCreate, ChatSessionUpdate
from synapse.council.thread import create_thread
from synapse.db.models import ChatSession


async def create_session(
    db: AsyncSession,
    *,
    request: ChatSessionCreate,
    created_by: str,
    tenant_id: str | None,
) -> ChatSession:
    """Create a new chat session.

    Always creates a fresh Thread to back the session. Forks are created via
    ``create_fork`` (TBD, next commit) which references a parent session +
    cursor and creates its own thread.
    """
    thread = await create_thread(
        db,
        council_id=request.council_id,
        created_by=created_by,
        tenant_id=tenant_id,
        title=request.title,
    )

    session = ChatSession(
        id=uuid.uuid4(),
        thread_id=thread.id,
        tenant_id=tenant_id,
        created_by=created_by,
        title=request.title,
        status="active",
        council_id=request.council_id,
        agent_config=request.agent_config.model_dump(exclude_unset=False),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    *,
    tenant_id: str | None | type(...) = ...,
) -> ChatSession | None:
    """Fetch a chat session by id, tenant-scoped by default.

    Same posture as ``synapse.council.thread.get_thread``: cross-tenant
    rows return None so the router raises 404, never leaking existence.
    Passing ``...`` (the sentinel) skips tenant scoping for system callers.
    """
    session = await db.get(ChatSession, session_id)
    if session is None:
        return None
    if tenant_id is ...:
        return session
    if session.tenant_id != tenant_id:
        return None
    return session


async def list_sessions(
    db: AsyncSession,
    *,
    tenant_id: str | None,
    created_by: str | None = None,
    status: str = "active",
    before_created_at: datetime | None = None,
    limit: int = 50,
) -> tuple[list[ChatSession], datetime | None]:
    """List chat sessions for a tenant, optionally scoped to a single principal.

    Cursor pagination via ``before_created_at`` — pass the previous page's
    ``next_before_id`` to fetch older sessions. Ordering is created_at DESC
    so the active set is at the head of the cursor stream.

    Status filter values: ``"active"`` (default), ``"archived"``, ``"all"``.
    """
    stmt = select(ChatSession)
    if tenant_id is None:
        stmt = stmt.where(ChatSession.tenant_id.is_(None))
    else:
        stmt = stmt.where(ChatSession.tenant_id == tenant_id)

    if created_by is not None:
        stmt = stmt.where(ChatSession.created_by == created_by)

    if status != "all":
        stmt = stmt.where(ChatSession.status == status)

    if before_created_at is not None:
        stmt = stmt.where(ChatSession.created_at < before_created_at)

    # Fetch limit + 1 so we can compute the next cursor without a separate
    # count query. If we got back limit + 1 rows, there's another page.
    stmt = stmt.order_by(desc(ChatSession.created_at)).limit(limit + 1)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor: datetime | None = rows[-1].created_at
    else:
        next_cursor = None

    return rows, next_cursor


async def update_session(
    db: AsyncSession,
    session: ChatSession,
    *,
    request: ChatSessionUpdate,
) -> ChatSession:
    """Apply a partial update to a session.

    Caller is responsible for tenant scoping (typically obtained via
    ``get_session(tenant_id=user.tenant_id)`` before this call).
    """
    if request.title is not None:
        session.title = request.title
    if request.status is not None:
        session.status = request.status
    if request.agent_config is not None:
        # Merge into existing agent_config rather than replacing wholesale —
        # callers typically update one field (e.g., switch model) without
        # wanting to clear tools / memory_banks.
        merged = dict(session.agent_config or {})
        merged.update(request.agent_config.model_dump(exclude_unset=True))
        session.agent_config = merged

    session.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return session


async def archive_session(
    db: AsyncSession,
    session: ChatSession,
) -> ChatSession:
    """Soft-delete via status flip. Underlying thread + events preserved
    for audit."""
    session.status = "archived"
    session.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(session)
    return session
