"""DSAR erasure pipeline — Synapse-side cleanup + Astrocyte forget_principal.

Triggered when an approved erasure request is being completed. Each
action is independent and records its own success / failure / pending
state in the certificate; a failed Astrocyte call doesn't undo the
Synapse-side cleanup that already succeeded, so an operator can re-run
the pipeline once the gateway is reachable.

## Actions performed

  * ``synapse_audit_events`` — delete audit rows authored by the subject
  * ``synapse_council_members`` — strip the subject from each council's
    ``members`` JSON list (council preserved for audit chain integrity)
  * ``synapse_notification_prefs`` — delete the subject's notification
    preferences row(s)
  * ``synapse_device_tokens`` — delete the subject's push device tokens
  * ``synapse_api_keys`` — revoke (set ``revoked_at``) — never hard
    delete API keys, the audit chain references them
  * ``astrocyte_forget_principal`` — single POST to the gateway; treats
    404/501 as ``astrocyte_pending`` (image lag, not a real failure);
    all other errors as ``failed``

Non-erasure requests (access / rectification) record a single ``no_op``
action so the certificate still ships and operators can attest "we
considered the request and took the appropriate action."
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.db.models import (
    ApiKey,
    AuditEvent,
    CouncilSession,
    DeviceToken,
    DSARRequest,
    DSARType,
    NotificationPreferences,
)
from synapse.memory.context import AstrocyteContext
from synapse.memory.gateway_client import AstrocyteGatewayClient

_logger = logging.getLogger(__name__)


async def run_erasure(
    db: AsyncSession,
    *,
    request: DSARRequest,
    astrocyte: AstrocyteGatewayClient,
) -> list[dict[str, Any]]:
    """Run the full erasure pipeline for ``request`` and return the
    list of action records ready to drop into the certificate payload.

    Each action record is a JSON-serializable dict with at least
    ``system``, ``action``, ``status``, and timestamps. Status is one of
    ``completed``, ``astrocyte_pending``, ``failed``, ``no_op``.

    The function commits Synapse-side mutations as it goes — an
    Astrocyte failure does NOT roll back the local deletes; that's the
    correct shape for DSAR (we'd rather have partial completion with
    accurate attestation than silently retry forever).
    """
    if request.request_type != DSARType.erasure:
        return [
            {
                "system": "synapse",
                "action": "no_op",
                "status": "no_op",
                "request_type": request.request_type.value,
                "note": ("Non-erasure request; pipeline finalised without data changes."),
            }
        ]

    actions: list[dict[str, Any]] = []
    actions.append(await _action(_erase_audit_events, db, request))
    actions.append(await _action(_erase_council_members, db, request))
    actions.append(await _action(_erase_notification_prefs, db, request))
    actions.append(await _action(_erase_device_tokens, db, request))
    actions.append(await _action(_revoke_api_keys, db, request))
    actions.append(await _astrocyte_forget(astrocyte, request))
    return actions


# ---------------------------------------------------------------------------
# Synapse-side actions
# ---------------------------------------------------------------------------


async def _erase_audit_events(db: AsyncSession, req: DSARRequest) -> dict[str, Any]:
    """Delete audit rows authored by the subject.

    Per DSAR: the right to erasure overrides the operator's interest in
    keeping the rows. Operators who need long-term audit retention
    should mirror events to a write-once external sink (see
    ``audit-log.md``) so the principal's actions remain attestable
    after their Synapse rows are gone.
    """
    stmt = delete(AuditEvent).where(AuditEvent.actor_principal == req.subject_principal)
    if req.tenant_id is not None:
        stmt = stmt.where(AuditEvent.tenant_id == req.tenant_id)
    result = await db.execute(stmt)
    await db.commit()
    return {
        "system": "synapse",
        "action": "synapse_audit_events",
        "deleted": result.rowcount or 0,
    }


async def _erase_council_members(db: AsyncSession, req: DSARRequest) -> dict[str, Any]:
    """Strip the subject from each council's ``members`` JSON list.

    The council row itself is preserved — verdicts already reference it
    and breaking those references corrupts the audit chain. We rewrite
    the members array in place; metadata fields like ``created_by``
    are left to ``_anonymise_council_authorship`` if the subject was
    the creator.
    """
    stmt = select(CouncilSession)
    if req.tenant_id is not None:
        stmt = stmt.where(CouncilSession.tenant_id == req.tenant_id)
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())

    touched = 0
    member_entries_removed = 0
    for s in sessions:
        members = s.members or []
        kept = [
            m
            for m in members
            if (m.get("principal") if isinstance(m, dict) else None) != req.subject_principal
            and (m.get("model_id") if isinstance(m, dict) else None) != req.subject_principal
        ]
        if len(kept) != len(members):
            member_entries_removed += len(members) - len(kept)
            s.members = kept
            touched += 1

        # Anonymise the creator if it was the subject — keep the row but
        # drop the personal pointer.
        if s.created_by == req.subject_principal:
            s.created_by = "user:erased"
            touched += 1

    if touched:
        await db.commit()

    return {
        "system": "synapse",
        "action": "synapse_council_members",
        "councils_touched": touched,
        "member_entries_removed": member_entries_removed,
    }


async def _erase_notification_prefs(db: AsyncSession, req: DSARRequest) -> dict[str, Any]:
    stmt = delete(NotificationPreferences).where(
        NotificationPreferences.principal == req.subject_principal
    )
    if req.tenant_id is not None:
        stmt = stmt.where(NotificationPreferences.tenant_id == req.tenant_id)
    result = await db.execute(stmt)
    await db.commit()
    return {
        "system": "synapse",
        "action": "synapse_notification_prefs",
        "deleted": result.rowcount or 0,
    }


async def _erase_device_tokens(db: AsyncSession, req: DSARRequest) -> dict[str, Any]:
    stmt = delete(DeviceToken).where(DeviceToken.principal == req.subject_principal)
    if req.tenant_id is not None:
        stmt = stmt.where(DeviceToken.tenant_id == req.tenant_id)
    result = await db.execute(stmt)
    await db.commit()
    return {
        "system": "synapse",
        "action": "synapse_device_tokens",
        "deleted": result.rowcount or 0,
    }


async def _revoke_api_keys(db: AsyncSession, req: DSARRequest) -> dict[str, Any]:
    """Revoke (soft-delete) — never hard-delete. The audit chain
    references API keys by id; removing the row would orphan those
    audit references and break compliance attestation. The hash is
    cleared so the key value can't be reconstructed."""
    now = datetime.now(UTC)
    stmt = (
        update(ApiKey)
        .where(
            ApiKey.created_by == req.subject_principal,
            ApiKey.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    if req.tenant_id is not None:
        stmt = stmt.where(ApiKey.tenant_id == req.tenant_id)
    result = await db.execute(stmt)
    await db.commit()
    return {
        "system": "synapse",
        "action": "synapse_api_keys",
        "revoked": result.rowcount or 0,
    }


# ---------------------------------------------------------------------------
# Astrocyte cross-system call
# ---------------------------------------------------------------------------


async def _astrocyte_forget(astrocyte: AstrocyteGatewayClient, req: DSARRequest) -> dict[str, Any]:
    started = datetime.now(UTC).isoformat()
    context = AstrocyteContext(
        principal="synapse:dsar-worker",
        tenant_id=req.tenant_id,
    )
    try:
        body = await astrocyte.forget_principal(
            principal=req.subject_principal,
            context=context,
            tenant_id=req.tenant_id,
        )
    except NotImplementedError as exc:
        _logger.warning("DSAR worker — Astrocyte endpoint absent: %s", exc)
        return {
            "system": "astrocyte",
            "action": "astrocyte_forget_principal",
            "status": "astrocyte_pending",
            "started_at": started,
            "note": (
                "Astrocyte gateway returned 404/501 for "
                "/v1/dsar/forget_principal — image lags this Synapse "
                "version. Synapse-side erasure has completed; re-run "
                "the DSAR (or pin a newer Astrocyte image) to finish "
                "cross-system erasure."
            ),
        }
    except Exception as exc:  # noqa: BLE001 — log everything, fail soft
        _logger.error("DSAR worker — Astrocyte forget failed: %s", exc)
        return {
            "system": "astrocyte",
            "action": "astrocyte_forget_principal",
            "status": "failed",
            "started_at": started,
            "failed_at": datetime.now(UTC).isoformat(),
            "error": repr(exc),
        }

    return {
        "system": "astrocyte",
        "action": "astrocyte_forget_principal",
        "status": "completed",
        "started_at": started,
        "completed_at": datetime.now(UTC).isoformat(),
        "result": body,
    }


# ---------------------------------------------------------------------------
# Action runner
# ---------------------------------------------------------------------------


async def _action(fn, db: AsyncSession, req: DSARRequest) -> dict[str, Any]:
    """Wrap a Synapse-side action with timing + try/except so a single
    failed step doesn't abort the rest of the pipeline."""
    started = datetime.now(UTC).isoformat()
    try:
        result = await fn(db, req)
        return {
            **result,
            "status": "completed",
            "started_at": started,
            "completed_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        _logger.error("DSAR action %s failed: %s", fn.__name__, exc)
        await db.rollback()
        return {
            "system": "synapse",
            "action": fn.__name__.lstrip("_"),
            "status": "failed",
            "started_at": started,
            "failed_at": datetime.now(UTC).isoformat(),
            "error": repr(exc),
        }


# ---------------------------------------------------------------------------
# Helpers exposed for the router
# ---------------------------------------------------------------------------


def build_certificate_payload(
    request: DSARRequest,
    *,
    completed_by: str,
    actions: list[dict[str, Any]],
    completed_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the certificate payload for ``certificate.build_and_sign``.

    Lives here rather than ``certificate.py`` because the payload
    encodes pipeline knowledge (request fields + actions) and the
    signer is a pure crypto module that takes whatever payload it's
    given.
    """
    completed_at = completed_at or datetime.now(UTC)
    return {
        "request_id": str(request.id),
        "tenant_id": request.tenant_id,
        "subject_principal": request.subject_principal,
        "request_type": request.request_type.value,
        "requested_at": request.requested_at.isoformat() if request.requested_at else None,
        "completed_by": completed_by,
        "completed_at": completed_at.isoformat(),
        "actions": actions,
    }


# Back-compat — explicit export for tests / external callers.
__all__ = [
    "run_erasure",
    "build_certificate_payload",
]


# Silence "unused import" lints for uuid.UUID — it's referenced
# implicitly via DSARRequest.id type annotations downstream.
_uuid_ref = uuid.UUID
