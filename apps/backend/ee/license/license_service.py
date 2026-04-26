"""LicenseService — runtime license validation with OSS / offline / online modes."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ee.license.license_fns import (
    features_from_license_dict,
    get_default_features,
    verify_offline_license,
)
from ee.license.license_types import FeatureSet

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cerebro dev signing public key — ML-DSA-65 (CRYSTALS-Dilithium3, FIPS 204).
# Base64-encoded raw public key bytes (1952 bytes).
# The corresponding private key is held exclusively by the Cerebro license
# server (Odeon-internal).  Self-hosted Synapse instances only embed this
# public key — they can verify licenses but never forge them.
# ---------------------------------------------------------------------------
_CEREBRO_DEV_PUBLIC_KEY_B64 = (
    "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"
)

# TTL constants
_CACHE_TTL_SECONDS = 300  # 5 minutes per tenant
_GRACE_PERIOD_SECONDS = 86_400  # 24 hours before degrading to OSS


class LicenseService:
    """Detect license mode at init; provide get_plan(tenant_id) synchronously."""

    def __init__(
        self,
        license_key_offline: str | None = None,
        license_key_online: str | None = None,
        license_server_url: str = "https://cerebro.odeoncg.ai",
        public_key_b64: str | None = None,
    ) -> None:
        self._license_server_url = license_server_url
        self._public_key_b64 = public_key_b64 or _CEREBRO_DEV_PUBLIC_KEY_B64

        # Mode detection: offline > online > oss
        if license_key_offline:
            self._mode = "offline"
            self._offline_key = license_key_offline
            self._offline_features: FeatureSet = get_default_features()
        elif license_key_online:
            self._mode = "online"
            self._online_key = license_key_online
            self._cache: dict[str, tuple[FeatureSet, datetime]] = {}
            self._cache_lock = asyncio.Lock()
            self._last_server_contact: datetime | None = None
            self._cached_features: FeatureSet = get_default_features()
            self._cron_task: asyncio.Task | None = None
        else:
            self._mode = "oss"

        self._http_client = None  # injected by start()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, app: FastAPI) -> None:
        """Initialise license on startup; called from lifespan."""
        if self._mode == "offline":
            self._offline_features = self._validate_offline_license()
        elif self._mode == "online":
            self._http_client = app.state.http_client
            await self._fetch_online_features()
            self._cron_task = asyncio.create_task(self._renewal_cron())
        # oss mode: nothing to do

    async def stop(self) -> None:
        """Cancel background cron on shutdown."""
        if self._mode == "online" and self._cron_task is not None:
            self._cron_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cron_task

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_plan(self, tenant_id: str | None = None) -> FeatureSet:
        """Return FeatureSet for the given tenant. Always synchronous."""
        if self._mode == "oss":
            return get_default_features()
        if self._mode == "offline":
            return self._offline_features
        # online
        return self._get_cached_features(tenant_id)

    # ------------------------------------------------------------------
    # Offline mode
    # ------------------------------------------------------------------

    def _validate_offline_license(self) -> FeatureSet:
        """Parse, verify signature, check expiry. Return features or OSS fallback."""
        try:
            payload = json.loads(base64.b64decode(self._offline_key).decode())
        except Exception:
            logger.warning("license: offline key is not valid base64-JSON — using OSS features")
            return get_default_features()

        license_json: str = payload.get("license", "")
        signature_hex: str = payload.get("signature", "")

        if not verify_offline_license(license_json, signature_hex, self._public_key_b64):
            logger.warning("license: offline license signature invalid — using OSS features")
            return get_default_features()

        try:
            license_dict = json.loads(license_json)
        except Exception:
            logger.warning("license: offline license JSON malformed — using OSS features")
            return get_default_features()

        expires_at_str = license_dict.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
                if datetime.now(UTC) > expires_at:
                    logger.warning(
                        "license: offline license expired at %s — using OSS features",
                        expires_at_str,
                    )
                    return get_default_features()
            except ValueError:
                logger.warning(
                    "license: cannot parse expires_at '%s' — treating as no expiry",
                    expires_at_str,
                )

        features = features_from_license_dict(license_dict)
        logger.info(
            "license: offline license validated — plan=%s", license_dict.get("plan", "custom")
        )
        return features

    # ------------------------------------------------------------------
    # Online mode
    # ------------------------------------------------------------------

    async def _fetch_online_features(self) -> None:
        """POST to Cerebro; update cached features. Degrades to OSS after 24h."""
        if self._http_client is None:
            logger.warning("license: HTTP client not available — using cached features")
            return
        try:
            resp = await self._http_client.post(
                f"{self._license_server_url}/api/license/v1/auth",
                json={"license_key": self._online_key},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            features = features_from_license_dict(data)
            self._cached_features = features
            self._last_server_contact = datetime.now(UTC)
            logger.info("license: online license refreshed from Cerebro")
        except Exception as exc:
            logger.warning("license: Cerebro unreachable (%s) — using cached features", exc)
            self._maybe_degrade()

    def _maybe_degrade(self) -> None:
        """After 24h without server contact, fall back to OSS features."""
        if self._last_server_contact is None:
            self._cached_features = get_default_features()
            return
        elapsed = (datetime.now(UTC) - self._last_server_contact).total_seconds()
        if elapsed > _GRACE_PERIOD_SECONDS:
            logger.warning(
                "license: no Cerebro contact for %.0f hours — degrading to OSS features",
                elapsed / 3600,
            )
            self._cached_features = get_default_features()

    async def _renewal_cron(self) -> None:
        """Re-validate every 10 minutes in the background."""
        while True:
            await asyncio.sleep(600)
            await self._fetch_online_features()

    def _get_cached_features(self, tenant_id: str | None) -> FeatureSet:
        """Return cached features; per-tenant cache is populated by _fetch."""
        if tenant_id and tenant_id in self._cache:
            features, cached_at = self._cache[tenant_id]
            elapsed = (datetime.now(UTC) - cached_at).total_seconds()
            if elapsed < _CACHE_TTL_SECONDS:
                return features
        return self._cached_features
