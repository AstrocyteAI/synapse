"""DSAR router — POST /v1/dsar + lifecycle endpoints.

Single-tenant Synapse exposes the *basic* DSAR tier:

  * ``POST   /v1/dsar``                — log a new request (any user)
  * ``GET    /v1/dsar``                — list (admin)
  * ``GET    /v1/dsar/{id}``           — detail + signed certificate (admin)
  * ``PATCH  /v1/dsar/{id}/approve``   — approve a pending request (admin)
  * ``PATCH  /v1/dsar/{id}/reject``    — reject a pending request (admin)
  * ``PATCH  /v1/dsar/{id}/complete``  — run the erasure pipeline + sign cert (admin)

Customers who need cross-tenant DSAR queues, externally-verifiable
JWS certificates, or multi-system erasure attestation should upgrade
to **Cerebro Enterprise** — see ``synapse/docs/_design/migration.md``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.audit import emit as audit_emit
from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.db.models import DSARRequest, DSARStatus, DSARType
from synapse.db.session import get_session as get_db_session
from synapse.dsar import certificate, state_machine, worker

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["dsar"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class CreateDSARRequest(BaseModel):
    subject_principal: str
    request_type: DSARType
    reason: str | None = None
    notes: str | None = None
    tenant_id: str | None = None


class TransitionRequest(BaseModel):
    notes: str | None = None


class DSARResponse(BaseModel):
    id: uuid.UUID
    tenant_id: str | None
    subject_principal: str
    request_type: str
    reason: str | None
    status: str
    notes: str | None
    requested_by: str
    requested_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    completed_at: datetime | None = None
    certificate: dict[str, Any] | None = None


class DSARListResponse(BaseModel):
    data: list[DSARResponse]
    count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialise(req: DSARRequest) -> DSARResponse:
    return DSARResponse(
        id=req.id,
        tenant_id=req.tenant_id,
        subject_principal=req.subject_principal,
        request_type=req.request_type.value
        if isinstance(req.request_type, DSARType)
        else str(req.request_type),
        reason=req.reason,
        status=req.status.value if isinstance(req.status, DSARStatus) else str(req.status),
        notes=req.notes,
        requested_by=req.requested_by,
        requested_at=req.requested_at,
        reviewed_by=req.reviewed_by,
        reviewed_at=req.reviewed_at,
        completed_at=req.completed_at,
        certificate=req.certificate,
    )


def _require_admin(user: AuthenticatedUser) -> None:
    if "admin" not in (user.roles or []):
        raise HTTPException(status_code=403, detail="admin role required")


def _require_signing_secret(request: Request) -> str:
    """Return the configured HMAC secret or raise 503.

    The secret is required to sign fulfilment certificates. Operators
    are expected to set ``synapse_dsar_signing_secret`` via env var
    before approving any DSAR — the router fails closed rather than
    issuing unsigned certificates.
    """
    secret = (request.app.state.settings.synapse_dsar_signing_secret or "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "DSAR fulfilment is unavailable — "
                "synapse_dsar_signing_secret is not configured. Set the "
                "env var to enable signed certificates."
            ),
        )
    return secret


# ---------------------------------------------------------------------------
# POST /v1/dsar — log a new request
# ---------------------------------------------------------------------------


@router.post(
    "/dsar",
    response_model=DSARResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a new DSAR (data subject access request)",
)
async def create_dsar(
    body: CreateDSARRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DSARResponse:
    """Anyone with a valid token may file a DSAR. The lifecycle gates
    (approve / reject / complete) are admin-only, so a non-admin user
    can't side-step review by self-approving."""
    req = await state_machine.create(
        db,
        subject_principal=body.subject_principal,
        request_type=body.request_type,
        requested_by=user.principal,
        tenant_id=body.tenant_id or user.tenant_id,
        reason=body.reason,
        notes=body.notes,
    )
    await audit_emit(
        db,
        "dsar.created",
        user.principal,
        tenant_id=req.tenant_id,
        resource_type="dsar_request",
        resource_id=str(req.id),
        metadata={
            "subject_principal": req.subject_principal,
            "request_type": req.request_type.value,
        },
    )
    await db.commit()
    return _serialise(req)


# ---------------------------------------------------------------------------
# GET /v1/dsar — list (admin)
# ---------------------------------------------------------------------------


@router.get(
    "/dsar",
    response_model=DSARListResponse,
    summary="List DSAR requests",
)
async def list_dsar(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DSARListResponse:
    _require_admin(user)
    parsed_status: DSARStatus | None
    if status_filter is None:
        parsed_status = None
    else:
        try:
            parsed_status = DSARStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"unknown status: {status_filter}") from exc

    rows = await state_machine.list_requests(
        db, status=parsed_status, tenant_id=user.tenant_id, limit=limit
    )
    return DSARListResponse(data=[_serialise(r) for r in rows], count=len(rows))


# ---------------------------------------------------------------------------
# GET /v1/dsar/{id} — detail (admin)
# ---------------------------------------------------------------------------


@router.get(
    "/dsar/{request_id}",
    response_model=DSARResponse,
    summary="Get a DSAR request including the fulfilment certificate",
)
async def get_dsar(
    request_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DSARResponse:
    _require_admin(user)
    req = await state_machine.get(db, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="DSAR request not found")
    # MT-1: collapse cross-tenant fetch to 404, same shape as missing
    if user.tenant_id and req.tenant_id is not None and req.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="DSAR request not found")
    return _serialise(req)


# ---------------------------------------------------------------------------
# PATCH /v1/dsar/{id}/approve  /  /reject
# ---------------------------------------------------------------------------


@router.patch(
    "/dsar/{request_id}/approve",
    response_model=DSARResponse,
    summary="Approve a pending DSAR (admin)",
)
async def approve_dsar(
    request_id: uuid.UUID,
    body: TransitionRequest | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DSARResponse:
    _require_admin(user)
    try:
        req = await state_machine.approve(
            db, request_id, user.principal, notes=body.notes if body else None
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except state_machine.InvalidStatusTransition as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_status_transition",
                "expected": [s.value for s in exc.expected],
                "actual": exc.actual.value,
            },
        ) from exc

    await audit_emit(
        db,
        "dsar.approved",
        user.principal,
        tenant_id=req.tenant_id,
        resource_type="dsar_request",
        resource_id=str(req.id),
        metadata={"subject_principal": req.subject_principal},
    )
    await db.commit()
    return _serialise(req)


@router.patch(
    "/dsar/{request_id}/reject",
    response_model=DSARResponse,
    summary="Reject a pending DSAR (admin) — terminal",
)
async def reject_dsar(
    request_id: uuid.UUID,
    body: TransitionRequest | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DSARResponse:
    _require_admin(user)
    try:
        req = await state_machine.reject(
            db, request_id, user.principal, notes=body.notes if body else None
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except state_machine.InvalidStatusTransition as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_status_transition",
                "expected": [s.value for s in exc.expected],
                "actual": exc.actual.value,
            },
        ) from exc

    await audit_emit(
        db,
        "dsar.rejected",
        user.principal,
        tenant_id=req.tenant_id,
        resource_type="dsar_request",
        resource_id=str(req.id),
        metadata={"subject_principal": req.subject_principal},
    )
    await db.commit()
    return _serialise(req)


# ---------------------------------------------------------------------------
# PATCH /v1/dsar/{id}/complete
# ---------------------------------------------------------------------------


@router.patch(
    "/dsar/{request_id}/complete",
    response_model=DSARResponse,
    summary="Run the erasure pipeline, sign the certificate, mark completed (admin)",
)
async def complete_dsar(
    request_id: uuid.UUID,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> DSARResponse:
    _require_admin(user)
    secret = _require_signing_secret(request)

    req = await state_machine.get(db, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="DSAR request not found")
    if req.status != DSARStatus.approved:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "invalid_status_transition",
                "expected": [DSARStatus.approved.value],
                "actual": req.status.value
                if isinstance(req.status, DSARStatus)
                else str(req.status),
            },
        )

    # Run the erasure pipeline first (or no-op for non-erasure types),
    # then sign the resulting certificate.
    actions = await worker.run_erasure(db, request=req, astrocyte=request.app.state.astrocyte)
    payload = worker.build_certificate_payload(req, completed_by=user.principal, actions=actions)
    signed = certificate.build_and_sign(payload, secret=secret)

    completed = await state_machine.mark_completed(
        db, request_id, user.principal, certificate=signed
    )

    await audit_emit(
        db,
        "dsar.completed",
        user.principal,
        tenant_id=completed.tenant_id,
        resource_type="dsar_request",
        resource_id=str(completed.id),
        metadata={
            "subject_principal": completed.subject_principal,
            "actions": len(actions),
        },
    )
    await db.commit()
    return _serialise(completed)
