"""Council session CRUD helpers — thin layer over SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.council.models import CouncilMember, CreateCouncilRequest
from synapse.db.models import CouncilSession, CouncilStatus


async def create_session(
    db: AsyncSession,
    request: CreateCouncilRequest,
    members: list[CouncilMember],
    chairman: CouncilMember,
    created_by: str,
    tenant_id: str | None = None,
) -> CouncilSession:
    """Insert a new CouncilSession in pending state and return it."""
    session = CouncilSession(
        id=uuid.uuid4(),
        question=request.question,
        status=CouncilStatus.pending,
        council_type=request.council_type,
        members=[m.model_dump() for m in members],
        chairman=chairman.model_dump(),
        config=request.config,
        topic_tag=request.topic_tag,
        template_id=request.template_id,
        created_by=created_by,
        tenant_id=tenant_id,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> CouncilSession | None:
    return await db.get(CouncilSession, session_id)


async def list_sessions(
    db: AsyncSession,
    *,
    tenant_id: str | None = None,
    created_by: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[CouncilSession]:
    """Return sessions newest-first, optionally filtered by tenant / principal."""
    stmt = select(CouncilSession).order_by(desc(CouncilSession.created_at))
    if tenant_id is not None:
        stmt = stmt.where(CouncilSession.tenant_id == tenant_id)
    if created_by is not None:
        stmt = stmt.where(CouncilSession.created_by == created_by)
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_failed(
    db: AsyncSession,
    session_id: uuid.UUID,
    *,
    error: str | None = None,
) -> None:
    session = await db.get(CouncilSession, session_id)
    if session:
        session.status = CouncilStatus.failed
        session.closed_at = datetime.now(UTC)
        if error:
            session.config = {**session.config, "_error": error}
        await db.commit()
