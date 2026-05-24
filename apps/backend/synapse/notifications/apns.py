"""Apple Push Notification service (HTTP/2) sender for Synapse notifications.

Uses a token-based (.p8) auth key. Required for iOS delivery when the app
registers a native APNs device token (``token_type='apns'``).

Env:
  SYNAPSE_APNS_KEY_ID, SYNAPSE_APNS_TEAM_ID, SYNAPSE_APNS_KEY (PEM),
  SYNAPSE_APNS_BUNDLE_ID, SYNAPSE_APNS_USE_SANDBOX (optional, default false)
"""

from __future__ import annotations

import logging
import time

import httpx
import jwt

_logger = logging.getLogger(__name__)

_APNS_PRODUCTION = "https://api.push.apple.com"
_APNS_SANDBOX = "https://api.development.push.apple.com"

# team_id -> (jwt, expires_at)
_jwt_cache: dict[str, tuple[str, float]] = {}


def _apns_jwt(key_id: str, team_id: str, private_key: str) -> str:
    cached = _jwt_cache.get(team_id)
    if cached and cached[1] > time.time() + 60:
        return cached[0]

    now = int(time.time())
    token = jwt.encode(
        {"iss": team_id, "iat": now},
        private_key,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id},
    )
    _jwt_cache[team_id] = (token, now + 3000)
    return token


async def send_apns(
    device_token: str,
    title: str,
    body: str,
    *,
    http_client: httpx.AsyncClient,
    key_id: str,
    team_id: str,
    private_key: str,
    bundle_id: str,
    use_sandbox: bool = False,
) -> None:
    """Deliver an alert notification to one APNs device token."""
    auth = _apns_jwt(key_id, team_id, private_key)
    host = _APNS_SANDBOX if use_sandbox else _APNS_PRODUCTION
    url = f"{host}/3/device/{device_token}"

    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        }
    }

    resp = await http_client.post(
        url,
        json=payload,
        headers={
            "authorization": f"bearer {auth}",
            "apns-topic": bundle_id,
            "apns-push-type": "alert",
            "apns-priority": "10",
        },
        http2=True,
    )
    resp.raise_for_status()
    _logger.debug("APNs sent token=%r… status=%s", device_token[:12], resp.status_code)
