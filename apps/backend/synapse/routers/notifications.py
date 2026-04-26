"""Notification preferences and device token management (EE Team+).

All endpoints require the ``notifications`` EE feature flag. Returns 501 if
the feature is not licensed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.db.models import DeviceToken, NotificationPreferences

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
        await db.delete(device)
        await db.commit()
