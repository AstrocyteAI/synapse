"""Centrifugo HTTP publish client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

_logger = logging.getLogger(__name__)


class CentrifugoClient:
    """Publishes events to Centrifugo channels via the HTTP API."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._http = http_client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"apikey {self._api_key}",
            "Content-Type": "application/json",
        }

    async def publish(self, channel: str, data: dict[str, Any]) -> None:
        """Publish an event to a Centrifugo channel."""
        payload = {"channel": channel, "data": data}
        try:
            resp = await self._http.post(
                f"{self._api_url}/api/publish",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            _logger.error("Centrifugo publish failed for channel %s: %s", channel, e)
            raise

    async def publish_council_event(self, council_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Publish a structured council stage event."""
        await self.publish(
            channel=f"council:{council_id}",
            data={"type": event_type, **payload},
        )
