"""Unit tests for synapse.webhooks.delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synapse.webhooks.delivery import WEBHOOK_EVENTS, deliver_webhook

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_client(status_code: int = 200) -> AsyncMock:
    """Return a mock httpx.AsyncClient with the given response status."""
    response = MagicMock()
    response.status_code = status_code
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    return client


def _verify_signature(payload_bytes: bytes, secret: str, header_value: str) -> bool:
    """Verify the X-Synapse-Signature header value against the payload."""
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return header_value == f"sha256={expected}"


# ---------------------------------------------------------------------------
# WEBHOOK_EVENTS constant
# ---------------------------------------------------------------------------


def test_webhook_events_contains_expected_types():
    assert "council_closed" in WEBHOOK_EVENTS
    assert "conflict_detected" in WEBHOOK_EVENTS
    assert "waiting_contributions" in WEBHOOK_EVENTS
    assert "pending_approval" in WEBHOOK_EVENTS


# ---------------------------------------------------------------------------
# deliver_webhook — signature verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_webhook_signs_payload_correctly():
    """Payload is signed with HMAC-SHA256 and sent in X-Synapse-Signature header."""
    http_client = _make_http_client(200)
    secret = "test-signing-secret"
    event = "council_closed"
    data = {"council_id": "abc-123", "verdict": "proceed"}

    result = await deliver_webhook(
        url="https://example.com/hook",
        secret=secret,
        event=event,
        data=data,
        http_client=http_client,
    )

    assert result is True
    assert http_client.post.called

    call_kwargs = http_client.post.call_args
    sent_bytes = call_kwargs.kwargs.get("content") or call_kwargs.args[1]
    sent_headers = call_kwargs.kwargs["headers"]

    # Verify signature
    sig_header = sent_headers["X-Synapse-Signature"]
    assert _verify_signature(sent_bytes, secret, sig_header)

    # Payload must include event and timestamp
    payload = json.loads(sent_bytes)
    assert payload["event"] == event
    assert "timestamp" in payload
    assert payload["council_id"] == "abc-123"


# ---------------------------------------------------------------------------
# deliver_webhook — success / failure behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deliver_webhook_returns_true_on_2xx():
    http_client = _make_http_client(201)
    result = await deliver_webhook("https://example.com/h", "s", "council_closed", {}, http_client)
    assert result is True


@pytest.mark.asyncio
async def test_deliver_webhook_returns_false_on_non_2xx_after_retries():
    http_client = _make_http_client(500)

    with patch("synapse.webhooks.delivery.asyncio.sleep", new=AsyncMock()):
        result = await deliver_webhook(
            "https://example.com/h",
            "s",
            "council_closed",
            {},
            http_client,
            max_attempts=3,
        )

    assert result is False
    assert http_client.post.call_count == 3


@pytest.mark.asyncio
async def test_deliver_webhook_retries_on_exception():
    """Network errors trigger retries; eventually returns False."""
    http_client = AsyncMock()
    http_client.post = AsyncMock(side_effect=ConnectionError("timeout"))

    with patch("synapse.webhooks.delivery.asyncio.sleep", new=AsyncMock()):
        result = await deliver_webhook(
            "https://example.com/h",
            "s",
            "council_closed",
            {},
            http_client,
            max_attempts=2,
        )

    assert result is False
    assert http_client.post.call_count == 2


@pytest.mark.asyncio
async def test_deliver_webhook_succeeds_on_second_attempt():
    """If first attempt fails and second succeeds, returns True."""
    fail_response = MagicMock()
    fail_response.status_code = 503
    ok_response = MagicMock()
    ok_response.status_code = 200

    http_client = AsyncMock()
    http_client.post = AsyncMock(side_effect=[fail_response, ok_response])

    with patch("synapse.webhooks.delivery.asyncio.sleep", new=AsyncMock()):
        result = await deliver_webhook(
            "https://example.com/h",
            "s",
            "council_closed",
            {},
            http_client,
            max_attempts=3,
        )

    assert result is True
    assert http_client.post.call_count == 2
