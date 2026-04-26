"""Webhook delivery — sign payloads and POST to registered endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)

WEBHOOK_EVENTS: frozenset[str] = frozenset(
    [
        "council_closed",
        "conflict_detected",
        "waiting_contributions",
        "pending_approval",
    ]
)


async def deliver_webhook(
    url: str,
    secret: str,
    event: str,
    data: dict[str, Any],
    http_client: Any,
    *,
    max_attempts: int = 3,
) -> bool:
    """Deliver a webhook payload to a URL with HMAC-SHA256 signing and retry.

    Returns True if delivery succeeded (any 2xx response), False otherwise.
    Never raises — all errors are logged.
    """
    payload: dict[str, Any] = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        **data,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Synapse-Signature": f"sha256={signature}",
    }

    backoff_seconds = [0, 1, 2]
    for attempt in range(max_attempts):
        delay = backoff_seconds[attempt] if attempt < len(backoff_seconds) else 2
        if delay > 0:
            await asyncio.sleep(delay)
        try:
            response = await http_client.post(url, content=payload_bytes, headers=headers)
            if 200 <= response.status_code < 300:
                return True
            _logger.warning(
                "Webhook delivery attempt %d/%d failed: %s %s",
                attempt + 1,
                max_attempts,
                response.status_code,
                url,
            )
        except Exception as exc:
            _logger.warning(
                "Webhook delivery attempt %d/%d error: %s %s",
                attempt + 1,
                max_attempts,
                exc,
                url,
            )
    _logger.error("Webhook delivery failed after %d attempts: %s", max_attempts, url)
    return False


async def fire_webhooks(
    db: AsyncSession,
    http_client: Any,
    event: str,
    data: dict[str, Any],
    tenant_id: str | None,
) -> None:
    """Query active webhooks for the event + tenant and fire each asynchronously.

    Errors are logged and never raised.
    """
    try:
        from synapse.db.models import Webhook

        stmt = select(Webhook).where(
            Webhook.active.is_(True),
            Webhook.tenant_id == tenant_id,
        )
        result = await db.execute(stmt)
        webhooks = result.scalars().all()

        matching = [wh for wh in webhooks if event in wh.events]
        for webhook in matching:
            asyncio.create_task(
                deliver_webhook(
                    url=webhook.url,
                    secret=webhook.secret,
                    event=event,
                    data=data,
                    http_client=http_client,
                )
            )
    except Exception as exc:
        _logger.error("fire_webhooks error for event %s: %s", event, exc)
