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

    # MT-1: fail closed on the tenant boundary. The previous behaviour
    # only filtered when `user.tenant_id` was truthy — a token with no
    # `synapse_tenant` claim therefore saw EVERY tenant's audit events,
    # which is precisely the leak audit logs are meant to prevent.
    #
    # Single-tenant Synapse deployments where every JWT lacks tenant_id
    # are still supported: see audit events with NULL tenant_id by
    # matching `IS NULL` rather than fanning out across tenants.
    stmt = select(AuditEvent).where(AuditEvent.tenant_id.is_not_distinct_from(user.tenant_id))

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


# ---------------------------------------------------------------------------
# Deprecated alias — kept for backward compatibility with the shared contract
# (originally `GET /v1/audit_logs`). New callers should use /admin/audit-log.
# ---------------------------------------------------------------------------


@router.get(
    "/audit_logs",
    response_model=AuditLogResponse,
    summary="[Deprecated] Use GET /v1/admin/audit-log instead",
    deprecated=True,
)
async def list_audit_log_legacy(
    limit: int = Query(default=50, ge=1, le=200),
    before_id: int | None = Query(default=None),
    principal: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Backward-compatible alias for GET /v1/admin/audit-log."""
    return await list_audit_log(
        limit=limit,
        before_id=before_id,
        principal=principal,
        event_type=event_type,
        resource_type=resource_type,
        user=user,
        db=db,
    )
