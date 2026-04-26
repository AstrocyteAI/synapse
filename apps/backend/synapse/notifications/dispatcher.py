"""Notification dispatcher — routes council lifecycle events to enabled channels.

Checks feature flags before every dispatch (no-op if notifications EE feature
is not licensed). Errors are caught and logged; dispatch never raises so it
never blocks the council pipeline.

Usage (from orchestrator or router):
    await dispatcher.dispatch_verdict(
        council_id=str(session.id),
        question=session.question,
        verdict=session.verdict,
        recipient_principal=session.created_by,
        db=db,
    )
"""

from __future__ import annotations

import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.db.models import DeviceToken, NotificationPreferences
from synapse.notifications.ntfy import send_ntfy
from synapse.notifications.smtp import send_email

_logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Stateless dispatcher wired onto app.state by main.py."""

    def __init__(
        self,
        settings,
        http_client: httpx.AsyncClient,
        feature_flags,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._feature_flags = feature_flags

    # ------------------------------------------------------------------
    # High-level dispatch helpers
    # ------------------------------------------------------------------

    async def dispatch_verdict(
        self,
        *,
        council_id: str,
        question: str,
        verdict: str | None,
        recipient_principal: str,
        db: AsyncSession,
        tenant_id: str | None = None,
    ) -> None:
        """Notify the council creator that a verdict has been reached."""
        short_q = question[:80] + ("…" if len(question) > 80 else "")
        subject = f"[Synapse] Verdict ready: {short_q}"
        body = (
            f"Council verdict is ready.\n\n"
            f"Question: {question}\n\n"
            f"Verdict: {verdict or '(no verdict)'}\n\n"
            f"Council ID: {council_id}"
        )
        await self._dispatch(
            event="verdict_ready",
            recipient_principal=recipient_principal,
            subject=subject,
            body=body,
            db=db,
            tenant_id=tenant_id,
        )

    async def dispatch_summon(
        self,
        *,
        council_id: str,
        question: str,
        recipient_principal: str,
        db: AsyncSession,
        tenant_id: str | None = None,
    ) -> None:
        """Notify a participant that they have been summoned to an async council."""
        short_q = question[:80] + ("…" if len(question) > 80 else "")
        subject = f"[Synapse] You've been summoned: {short_q}"
        body = (
            f"You have been summoned to contribute to a Synapse council.\n\n"
            f"Question: {question}\n\n"
            f"Council ID: {council_id}\n\n"
            f"Submit your contribution at: POST /v1/councils/{council_id}/contribute"
        )
        await self._dispatch(
            event="summon_requested",
            recipient_principal=recipient_principal,
            subject=subject,
            body=body,
            db=db,
            tenant_id=tenant_id,
        )

    # ------------------------------------------------------------------
    # Core dispatch
    # ------------------------------------------------------------------

    async def _dispatch(
        self,
        *,
        event: str,
        recipient_principal: str,
        subject: str,
        body: str,
        db: AsyncSession,
        tenant_id: str | None = None,
    ) -> None:
        """Look up preferences and send via all enabled channels."""
        if not self._feature_flags.is_enabled("notifications", tenant_id=tenant_id):
            return

        prefs = await self._load_prefs(recipient_principal, db)
        if prefs is None:
            return  # no preferences row → opted out

        await self._try_email(prefs, subject, body)
        await self._try_ntfy(prefs, recipient_principal, subject, body, db)

    async def _load_prefs(self, principal: str, db: AsyncSession) -> NotificationPreferences | None:
        result = await db.execute(
            select(NotificationPreferences).where(NotificationPreferences.principal == principal)
        )
        return result.scalar_one_or_none()

    async def _try_email(
        self,
        prefs: NotificationPreferences,
        subject: str,
        body: str,
    ) -> None:
        if not prefs.email_enabled or not prefs.email_address:
            return
        if not self._settings.smtp_host:
            _logger.warning("Email notification requested but SMTP_HOST not configured")
            return
        try:
            await send_email(
                to=prefs.email_address,
                subject=subject,
                body=body,
                host=self._settings.smtp_host,
                port=self._settings.smtp_port,
                username=self._settings.smtp_username,
                password=self._settings.smtp_password,
                from_address=self._settings.smtp_from_address,
                use_tls=self._settings.smtp_tls,
            )
        except Exception:
            _logger.exception("SMTP send failed for principal=%s", prefs.principal)

    async def _try_ntfy(
        self,
        prefs: NotificationPreferences,
        principal: str,
        subject: str,
        body: str,
        db: AsyncSession,
    ) -> None:
        if not prefs.ntfy_enabled:
            return
        if not self._settings.ntfy_url:
            _logger.warning("ntfy notification requested but NTFY_URL not configured")
            return

        result = await db.execute(
            select(DeviceToken).where(
                DeviceToken.principal == principal,
                DeviceToken.token_type == "ntfy",
            )
        )
        devices = result.scalars().all()

        for device in devices:
            try:
                await send_ntfy(
                    topic=device.token,
                    title=subject,
                    body=body,
                    http_client=self._http,
                    ntfy_url=self._settings.ntfy_url,
                    token=self._settings.ntfy_token,
                    tags=["synapse"],
                )
            except Exception:
                _logger.exception(
                    "ntfy send failed for device_id=%s principal=%s", device.id, principal
                )
