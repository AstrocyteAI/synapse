"""Webhooks router — B9: register and manage outbound event webhooks."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.audit import emit as audit_emit
from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.db.models import Webhook
from synapse.db.session import get_session as get_db_session
from synapse.webhooks.delivery import WEBHOOK_EVENTS

_logger = logging.getLogger(__name__)

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
    await audit_emit(
        db,
        "webhook.created",
        user.principal,
        tenant_id=user.tenant_id,
        resource_type="webhook",
        resource_id=str(webhook.id),
        metadata={"url": url_str, "events": body.events},
    )
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
    # MT-1: tenant_id filter alongside created_by. See api_keys.list for
    # the rationale; `is_not_distinct_from` is NULL-safe.
    stmt = select(Webhook).where(
        Webhook.created_by == user.principal,
        Webhook.tenant_id.is_not_distinct_from(user.tenant_id),
    )
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
    await audit_emit(
        db,
        "webhook.deleted",
        user.principal,
        tenant_id=user.tenant_id,
        resource_type="webhook",
        resource_id=str(wh_id),
        metadata={"url": webhook.url},
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Admin export endpoint — migration use only (X-4)
# ---------------------------------------------------------------------------


class WebhookExportOut(BaseModel):
    id: str
    url: str
    events: list[str]
    secret: str  # plain HMAC signing secret — exported for migration continuity
    active: bool
    created_by: str
    created_at: str
    last_delivery_at: str | None


# Header that callers must send to opt into the secret-bearing export.
# Without it the endpoint returns 403 even for admins. Stops a CSRF / clickjack
# / accidental-link from triggering a full secret dump from a logged-in admin
# browser session.
_MIGRATION_EXPORT_HEADER = "X-Migration-Export"
_MIGRATION_EXPORT_VALUE = "true"


@router.get(
    "/admin/webhooks",
    summary="[Migration export] List all webhooks including signing secrets (admin only)",
)
async def admin_list_webhooks(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    request: Request = None,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Dump all webhooks (including signing secrets) for migration to Cerebro.

    This endpoint exposes plaintext HMAC signing keys for every webhook in
    the deployment. A single compromised admin token therefore exfiltrates
    every consumer's signing key. Three guard rails:

      * ``admin`` role required.
      * ``X-Migration-Export: true`` header required — opts into the dump
        explicitly so a stolen admin browser session can't trigger it via
        CSRF or a malicious link. The Cerebro migration importer sends
        this header; nothing else should.
      * Every call is audit-logged at HIGH severity with the requesting
        principal, source IP, user agent, and the count of secrets
        returned. Operators should alarm on this event in real time.

    The ``secret`` field is the plain HMAC signing key. It is included here
    (and only here) so existing webhook consumers do not need to update
    their signature-verification setup after migration.
    """
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="admin role required")

    if request.headers.get(_MIGRATION_EXPORT_HEADER) != _MIGRATION_EXPORT_VALUE:
        # 403 (not 400) so that any audit pipeline treats this as an
        # authorization failure on a sensitive resource, not a
        # malformed-request blip.
        raise HTTPException(
            status_code=403,
            detail=(
                f"{_MIGRATION_EXPORT_HEADER}: {_MIGRATION_EXPORT_VALUE} header "
                "required for this endpoint."
            ),
        )

    async with request.app.state.sessionmaker() as db:
        result = await db.execute(
            select(Webhook).order_by(Webhook.created_at).limit(limit).offset(offset)
        )
        rows = result.scalars().all()

        # Loud audit trail — every secret dump is a HIGH-severity event.
        client_ip = request.client.host if request.client else None
        await audit_emit(
            db,
            "webhook.secrets_exported",
            user.principal,
            tenant_id=user.tenant_id,
            resource_type="webhook",
            resource_id=None,
            metadata={
                "severity": "high",
                "count": len(rows),
                "client_ip": client_ip,
                "user_agent": request.headers.get("user-agent"),
                "limit": limit,
                "offset": offset,
            },
        )
        await db.commit()

    _logger.warning(
        "webhook.secrets_exported principal=%s tenant=%s ip=%s count=%d",
        user.principal,
        user.tenant_id,
        client_ip,
        len(rows),
    )

    return {
        "count": len(rows),
        "data": [
            WebhookExportOut(
                id=str(r.id),
                url=r.url,
                events=list(r.events),
                secret=r.secret,
                active=r.active,
                created_by=r.created_by,
                created_at=r.created_at.isoformat(),
                last_delivery_at=r.last_delivery_at.isoformat() if r.last_delivery_at else None,
            )
            for r in rows
        ],
    }
