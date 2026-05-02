"""DSAR lifecycle — pending → approved → completed (or rejected).

The transitions are guarded by ``InvalidStatusTransition`` so that
attempts to e.g. complete a request that's still pending fail fast at
the data layer instead of relying on the router to enforce ordering.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.db.models import DSARRequest, DSARStatus, DSARType


class InvalidStatusTransition(Exception):
    """Raised when a transition is attempted from a non-permitted source state.

    e.g. ``approve()`` on a row that's already in ``rejected`` —
    Synapse refuses rather than silently no-op'ing, so operators can
    surface the misuse instead of trusting the row's mutation.
    """

    def __init__(self, *, expected: list[DSARStatus] | DSARStatus, actual: DSARStatus):
        self.expected = expected if isinstance(expected, list) else [expected]
        self.actual = actual
        super().__init__(
            f"Invalid DSAR status transition — expected one of "
            f"{[s.value for s in self.expected]}, got {actual.value}"
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


async def get(db: AsyncSession, request_id: uuid.UUID) -> DSARRequest | None:
    return await db.get(DSARRequest, request_id)


async def list_requests(
    db: AsyncSession,
    *,
    status: DSARStatus | None = None,
    tenant_id: str | None = None,
    limit: int = 100,
) -> list[DSARRequest]:
    """Return DSAR requests newest-first.

    Tenant filter is intentionally optional — Synapse is single-tenant so
    most deployments populate the column for categorisation only and
    leave it un-queried. When a deployment does populate per-org
    tenant_ids, the index on ``(tenant_id, status)`` keeps the lookup
    fast.
    """
    stmt = select(DSARRequest)
    if status is not None:
        stmt = stmt.where(DSARRequest.status == status)
    if tenant_id is not None:
        stmt = stmt.where(DSARRequest.tenant_id == tenant_id)
    stmt = stmt.order_by(DSARRequest.requested_at.desc()).limit(max(1, min(limit, 500)))
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def create(
    db: AsyncSession,
    *,
    subject_principal: str,
    request_type: DSARType,
    requested_by: str,
    tenant_id: str | None = None,
    reason: str | None = None,
    notes: str | None = None,
) -> DSARRequest:
    """Insert a new DSAR request in ``pending`` state."""
    req = DSARRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject_principal=subject_principal,
        request_type=request_type,
        reason=reason,
        notes=notes,
        status=DSARStatus.pending,
        requested_by=requested_by,
        requested_at=datetime.now(UTC),
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def approve(
    db: AsyncSession,
    request_id: uuid.UUID,
    reviewer_principal: str,
    notes: str | None = None,
) -> DSARRequest:
    """Move a pending request to ``approved``. Records reviewer + timestamp."""
    return await _transition(
        db,
        request_id,
        from_status=DSARStatus.pending,
        to_status=DSARStatus.approved,
        reviewer_principal=reviewer_principal,
        notes=notes,
    )


async def reject(
    db: AsyncSession,
    request_id: uuid.UUID,
    reviewer_principal: str,
    notes: str | None = None,
) -> DSARRequest:
    """Move a pending request to ``rejected`` (terminal)."""
    return await _transition(
        db,
        request_id,
        from_status=DSARStatus.pending,
        to_status=DSARStatus.rejected,
        reviewer_principal=reviewer_principal,
        notes=notes,
    )


async def mark_completed(
    db: AsyncSession,
    request_id: uuid.UUID,
    reviewer_principal: str,
    *,
    certificate: dict[str, Any] | None = None,
) -> DSARRequest:
    """Transition an approved request to ``completed`` and stamp the
    fulfilment certificate.

    The router calls this AFTER the worker's erasure pipeline has run,
    passing the signed certificate built by ``synapse.dsar.certificate``.
    For non-erasure requests (access / rectification) the certificate
    records a no-op action and is signed exactly the same way.
    """
    req = await get(db, request_id)
    if req is None:
        raise LookupError(f"DSAR request {request_id} not found")
    if req.status != DSARStatus.approved:
        raise InvalidStatusTransition(expected=DSARStatus.approved, actual=req.status)

    req.status = DSARStatus.completed
    req.completed_at = datetime.now(UTC)
    if certificate is not None:
        req.certificate = certificate
    # The reviewer who completes is recorded on the certificate itself;
    # the row's ``reviewed_by`` already carries the approver's principal
    # from the earlier transition.
    if reviewer_principal and req.reviewed_by is None:
        req.reviewed_by = reviewer_principal
    await db.commit()
    await db.refresh(req)
    return req


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


async def _transition(
    db: AsyncSession,
    request_id: uuid.UUID,
    *,
    from_status: DSARStatus,
    to_status: DSARStatus,
    reviewer_principal: str,
    notes: str | None,
) -> DSARRequest:
    req = await get(db, request_id)
    if req is None:
        raise LookupError(f"DSAR request {request_id} not found")
    if req.status != from_status:
        raise InvalidStatusTransition(expected=from_status, actual=req.status)

    req.status = to_status
    req.reviewed_by = reviewer_principal
    req.reviewed_at = datetime.now(UTC)
    if notes is not None:
        # Append rather than overwrite so prior context isn't lost.
        req.notes = (req.notes + "\n\n" if req.notes else "") + notes
    await db.commit()
    await db.refresh(req)
    return req
