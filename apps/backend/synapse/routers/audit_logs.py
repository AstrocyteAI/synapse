"""Audit log router — GET /v1/admin/audit-log (B11)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.db.models import AuditEvent
from synapse.db.session import get_session as get_db_session

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit-logs"])


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class AuditEventResponse(BaseModel):
    id: int
    event_type: str
    actor_principal: str
    tenant_id: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: dict[str, Any]
    created_at: datetime


class AuditLogResponse(BaseModel):
    data: list[AuditEventResponse]
    count: int
    # Cursors for next/previous page; None when there are no more pages
    next_before_id: int | None = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/admin/audit-log", response_model=AuditLogResponse)
async def list_audit_log(
    # Pagination
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None, description="Return events with id < before_id"),
    # Filters
    principal: str | None = Query(default=None, description="Filter by actor_principal"),
    event_type: str | None = Query(default=None, description="Filter by event_type"),
    resource_type: str | None = Query(default=None, description="Filter by resource_type"),
    # Auth
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Return recent audit events for the caller's tenant.

    Requires the ``admin`` role.  Results are ordered newest-first and
    paginated by BIGSERIAL cursor (``before_id``) — never use SQL OFFSET.
    """
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="admin role required")

    stmt = select(AuditEvent)

    # Tenant isolation — non-null tenant_id users only see their own tenant
    if user.tenant_id:
        stmt = stmt.where(AuditEvent.tenant_id == user.tenant_id)

    if before_id is not None:
        stmt = stmt.where(AuditEvent.id < before_id)

    if principal:
        stmt = stmt.where(AuditEvent.actor_principal == principal)

    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)

    if resource_type:
        stmt = stmt.where(AuditEvent.resource_type == resource_type)

    stmt = stmt.order_by(AuditEvent.id.desc()).limit(limit + 1)  # fetch one extra to detect more

    result = await db.execute(stmt)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    rows = rows[:limit]

    data = [
        AuditEventResponse(
            id=row.id,
            event_type=row.event_type,
            actor_principal=row.actor_principal,
            tenant_id=row.tenant_id,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            metadata=row.event_metadata,
            created_at=row.created_at,
        )
        for row in rows
    ]

    return AuditLogResponse(
        data=data,
        count=len(data),
        next_before_id=rows[-1].id if has_more and rows else None,
    )
