"""Webhooks router — B9: register and manage outbound event webhooks."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.db.models import Webhook
from synapse.db.session import get_session as get_db_session
from synapse.webhooks.delivery import WEBHOOK_EVENTS

router = APIRouter(tags=["webhooks"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateWebhookRequest(BaseModel):
    url: HttpUrl
    events: list[str]
    secret: str | None = None


class WebhookCreatedResponse(BaseModel):
    id: uuid.UUID
    url: str
    events: list[str]
    secret: str  # shown once on creation
    active: bool
    created_at: datetime
    tenant_id: str | None = None


class WebhookResponse(BaseModel):
    id: uuid.UUID
    url: str
    events: list[str]
    active: bool
    created_at: datetime
    last_delivery_at: datetime | None = None
    failure_count: int = 0
    tenant_id: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/webhooks", response_model=WebhookCreatedResponse, status_code=201)
async def create_webhook(
    body: CreateWebhookRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Register a new webhook. The signing secret is returned once."""
    # Validate event types
    invalid = [e for e in body.events if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid event types: {invalid}. Allowed: {sorted(WEBHOOK_EVENTS)}",
        )
    if not body.events:
        raise HTTPException(status_code=422, detail="At least one event type is required")

    signing_secret = body.secret if body.secret else secrets.token_urlsafe(32)
    url_str = str(body.url)

    webhook = Webhook(
        id=uuid.uuid4(),
        url=url_str,
        events=body.events,
        secret=signing_secret,
        active=True,
        created_by=user.principal,
        tenant_id=user.tenant_id,
        created_at=datetime.now(UTC),
    )
    db.add(webhook)
    await db.commit()
    await db.refresh(webhook)

    return WebhookCreatedResponse(
        id=webhook.id,
        url=webhook.url,
        events=list(webhook.events),
        secret=signing_secret,
        active=webhook.active,
        created_at=webhook.created_at,
        tenant_id=webhook.tenant_id,
    )


@router.get("/webhooks", response_model=list[WebhookResponse])
async def list_webhooks(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """List webhooks registered by the current user."""
    stmt = select(Webhook).where(Webhook.created_by == user.principal)
    result = await db.execute(stmt)
    webhooks = result.scalars().all()
    return [
        WebhookResponse(
            id=wh.id,
            url=wh.url,
            events=list(wh.events),
            active=wh.active,
            created_at=wh.created_at,
            last_delivery_at=wh.last_delivery_at,
            failure_count=wh.failure_count,
            tenant_id=wh.tenant_id,
        )
        for wh in webhooks
    ]


@router.delete("/webhooks/{wh_id}", status_code=204)
async def deactivate_webhook(
    wh_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Deactivate a webhook (sets active=False)."""
    webhook = await db.get(Webhook, wh_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    is_admin = "admin" in user.roles
    owns_webhook = webhook.created_by == user.principal
    same_tenant = webhook.tenant_id == user.tenant_id

    if not owns_webhook and not (is_admin and same_tenant):
        raise HTTPException(status_code=403, detail="Cannot deactivate this webhook")

    webhook.active = False
    await db.commit()
