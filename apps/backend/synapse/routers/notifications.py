"""Notification preferences and device token management (EE Team+).

All endpoints require the ``notifications`` EE feature flag. Returns 501 if
the feature is not licensed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.audit import emit as audit_emit
from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.db.models import CouncilSession, CouncilStatus, DeviceToken, NotificationPreferences
from synapse.db.session import get_session as get_db_session

router = APIRouter(tags=["notifications"])

_FEATURE = "notifications"


def _require_feature(request: Request) -> None:
    ff = request.app.state.feature_flags
    if not ff.is_enabled(_FEATURE):
        raise HTTPException(
            status_code=501,
            detail="Notifications require the EE Team+ plan. See https://cerebro.odeoncg.ai for licensing.",
        )


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PreferencesOut(BaseModel):
    email_enabled: bool
    email_address: str | None
    ntfy_enabled: bool
    updated_at: str


class UpdatePreferencesRequest(BaseModel):
    email_enabled: bool = False
    email_address: EmailStr | None = None
    ntfy_enabled: bool = False


class RegisterDeviceRequest(BaseModel):
    token_type: str = Field(default="ntfy", pattern="^ntfy$")
    token: str = Field(min_length=1, max_length=512)
    device_label: str | None = Field(default=None, max_length=128)


class DeviceTokenOut(BaseModel):
    id: str
    token_type: str
    token: str
    device_label: str | None
    created_at: str


# ---------------------------------------------------------------------------
# GET /v1/notifications/preferences
# ---------------------------------------------------------------------------


@router.get(
    "/notifications/preferences",
    summary="Get my notification preferences",
)
async def get_preferences(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(_require_feature),
) -> PreferencesOut:
    async with request.app.state.sessionmaker() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.principal == user.principal
            )
        )
        prefs = result.scalar_one_or_none()

    if prefs is None:
        return PreferencesOut(
            email_enabled=False,
            email_address=None,
            ntfy_enabled=False,
            updated_at=datetime.now(UTC).isoformat(),
        )

    return PreferencesOut(
        email_enabled=prefs.email_enabled,
        email_address=prefs.email_address,
        ntfy_enabled=prefs.ntfy_enabled,
        updated_at=prefs.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# PUT /v1/notifications/preferences
# ---------------------------------------------------------------------------


@router.put(
    "/notifications/preferences",
    summary="Update my notification preferences",
)
async def update_preferences(
    request: Request,
    body: UpdatePreferencesRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(_require_feature),
) -> PreferencesOut:
    now = datetime.now(UTC)

    async with request.app.state.sessionmaker() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(NotificationPreferences).where(
                NotificationPreferences.principal == user.principal
            )
        )
        prefs = result.scalar_one_or_none()

        if prefs is None:
            prefs = NotificationPreferences(
                id=uuid.uuid4(),
                principal=user.principal,
                tenant_id=user.tenant_id,
                email_enabled=body.email_enabled,
                email_address=str(body.email_address) if body.email_address else None,
                ntfy_enabled=body.ntfy_enabled,
                updated_at=now,
            )
            db.add(prefs)
        else:
            prefs.email_enabled = body.email_enabled
            prefs.email_address = str(body.email_address) if body.email_address else None
            prefs.ntfy_enabled = body.ntfy_enabled
            prefs.updated_at = now

        await audit_emit(
            db,
            "notification_prefs.updated",
            user.principal,
            tenant_id=user.tenant_id,
            resource_type="notification_preferences",
            resource_id=user.principal,
            metadata={"email_enabled": body.email_enabled, "ntfy_enabled": body.ntfy_enabled},
        )
        await db.commit()
        await db.refresh(prefs)

    return PreferencesOut(
        email_enabled=prefs.email_enabled,
        email_address=prefs.email_address,
        ntfy_enabled=prefs.ntfy_enabled,
        updated_at=prefs.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# POST /v1/notifications/devices
# ---------------------------------------------------------------------------


@router.post(
    "/notifications/devices",
    summary="Register a push notification endpoint (ntfy topic)",
    status_code=201,
)
async def register_device(
    request: Request,
    body: RegisterDeviceRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(_require_feature),
) -> DeviceTokenOut:
    now = datetime.now(UTC)
    device = DeviceToken(
        id=uuid.uuid4(),
        principal=user.principal,
        tenant_id=user.tenant_id,
        token_type=body.token_type,
        token=body.token,
        device_label=body.device_label,
        created_at=now,
    )

    async with request.app.state.sessionmaker() as db:
        db.add(device)
        await audit_emit(
            db,
            "device_token.registered",
            user.principal,
            tenant_id=user.tenant_id,
            resource_type="device_token",
            resource_id=str(device.id),
            metadata={"token_type": body.token_type, "device_label": body.device_label},
        )
        await db.commit()
        await db.refresh(device)

    return DeviceTokenOut(
        id=str(device.id),
        token_type=device.token_type,
        token=device.token,
        device_label=device.device_label,
        created_at=device.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /v1/notifications/devices
# ---------------------------------------------------------------------------


@router.get(
    "/notifications/devices",
    summary="List my registered push notification endpoints",
)
async def list_devices(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(_require_feature),
) -> dict[str, Any]:
    async with request.app.state.sessionmaker() as db:
        from sqlalchemy import select

        result = await db.execute(
            select(DeviceToken).where(DeviceToken.principal == user.principal)
        )
        devices = result.scalars().all()

    return {
        "count": len(devices),
        "devices": [
            DeviceTokenOut(
                id=str(d.id),
                token_type=d.token_type,
                token=d.token,
                device_label=d.device_label,
                created_at=d.created_at.isoformat(),
            )
            for d in devices
        ],
    }


# ---------------------------------------------------------------------------
# DELETE /v1/notifications/devices/{token_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/notifications/devices/{token_id}",
    summary="Unregister a push notification endpoint",
    status_code=204,
)
async def delete_device(
    token_id: uuid.UUID,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    _: None = Depends(_require_feature),
) -> None:
    async with request.app.state.sessionmaker() as db:
        device = await db.get(DeviceToken, token_id)
        if device is None or device.principal != user.principal:
            raise HTTPException(status_code=404, detail="Device token not found")
        await audit_emit(
            db,
            "device_token.deleted",
            user.principal,
            tenant_id=user.tenant_id,
            resource_type="device_token",
            resource_id=str(token_id),
            metadata={"token_type": device.token_type},
        )
        await db.delete(device)
        await db.commit()


# ---------------------------------------------------------------------------
# GET /v1/notifications/feed  — FREE tier, no EE gate
# ---------------------------------------------------------------------------


class FeedItem(BaseModel):
    type: str  # "verdict_ready" | "pending_approval" | "in_progress" | "summon_requested"
    council_id: str
    question: str
    verdict: str | None = None
    confidence_label: str | None = None
    consensus_score: float | None = None
    occurred_at: str  # ISO timestamp (closed_at for verdicts, created_at for others)


class NotificationFeedResponse(BaseModel):
    items: list[FeedItem]
    count: int


@router.get(
    "/notifications/feed",
    response_model=NotificationFeedResponse,
    summary="Recent notification feed for the current user (free tier)",
)
async def get_notification_feed(
    limit: int = Query(default=20, ge=1, le=50),
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> NotificationFeedResponse:
    """Return recent council lifecycle events relevant to the current user.

    Includes:
    - ``verdict_ready``      — council reached a verdict (status=closed)
    - ``pending_approval``   — council needs human approval (conflict detected)
    - ``in_progress``        — council is actively running
    - ``summon_requested``   — async council awaiting the user's contribution

    Not EE-gated — all plans can view the feed.
    """
    # Verdicts + pending approval + in-progress — councils the user created
    stmt = (
        select(CouncilSession)
        .where(CouncilSession.created_by == user.principal)
        .order_by(desc(CouncilSession.created_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    items: list[FeedItem] = []
    for s in sessions:
        if s.status == CouncilStatus.closed:
            item_type = "verdict_ready"
            occurred_at = (s.closed_at or s.created_at).isoformat()
        elif s.status == CouncilStatus.pending_approval:
            item_type = "pending_approval"
            occurred_at = (s.closed_at or s.created_at).isoformat()
        elif s.status == CouncilStatus.waiting_contributions:
            item_type = "summon_requested"
            occurred_at = s.created_at.isoformat()
        elif s.status in (CouncilStatus.stage_1, CouncilStatus.stage_2, CouncilStatus.stage_3):
            item_type = "in_progress"
            occurred_at = s.created_at.isoformat()
        else:
            # pending / scheduled / failed — skip
            continue

        items.append(
            FeedItem(
                type=item_type,
                council_id=str(s.id),
                question=s.question,
                verdict=s.verdict,
                confidence_label=s.confidence_label,
                consensus_score=s.consensus_score,
                occurred_at=occurred_at,
            )
        )

    return NotificationFeedResponse(items=items, count=len(items))
