"""Audit log emission helper (B11).

``emit()`` is fire-and-forget: it inserts one ``AuditEvent`` row and never
raises, so callers are never blocked by audit failures.

Usage::

    from synapse.audit import emit

    await emit(
        db,
        event_type="api_key.created",
        actor_principal=user.principal,
        tenant_id=user.tenant_id,
        resource_type="api_key",
        resource_id=str(api_key.id),
        metadata={"name": api_key.name},
    )

Event type convention:  ``<resource>.<action>``
  council.created      council.closed       council.failed
  api_key.created      api_key.revoked
  webhook.created      webhook.deleted
  device_token.registered   device_token.deleted
  notification_prefs.updated
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from synapse.db.models import AuditEvent

_logger = logging.getLogger(__name__)


async def emit(
    db: AsyncSession,
    event_type: str,
    actor_principal: str,
    *,
    tenant_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Insert one audit event row.  Never raises."""
    try:
        event = AuditEvent(
            event_type=event_type,
            actor_principal=actor_principal,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            event_metadata=metadata or {},
        )
        db.add(event)
        await db.flush()  # write within the caller's transaction; they commit
    except Exception:
        _logger.exception("audit emit failed: event_type=%s actor=%s", event_type, actor_principal)
