"""Firebase Cloud Messaging (HTTP v1) sender for Synapse notifications.

Uses a Google service-account JSON to mint OAuth2 access tokens and POST
to ``projects/{project_id}/messages:send``. FCM relays to APNs on iOS when
the Firebase project has APNs credentials configured.

Env: ``SYNAPSE_FCM_SERVICE_ACCOUNT_JSON`` — full service-account JSON string.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
import jwt

_logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# module-level cache: project_id -> (access_token, expires_at)
_token_cache: dict[str, tuple[str, float]] = {}


def _parse_service_account(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    for key in ("project_id", "client_email", "private_key"):
        if key not in data:
            raise ValueError(f"FCM service account JSON missing {key!r}")
    return data


def _build_jwt_assertion(service_account: dict[str, Any]) -> str:
    now = int(time.time())
    payload = {
        "iss": service_account["client_email"],
        "sub": service_account["client_email"],
        "aud": _TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
        "scope": _FCM_SCOPE,
    }
    return jwt.encode(payload, service_account["private_key"], algorithm="RS256")


async def _access_token(
    http_client: httpx.AsyncClient,
    service_account: dict[str, Any],
) -> str:
    project_id = service_account["project_id"]
    cached = _token_cache.get(project_id)
    if cached and cached[1] > time.time() + 60:
        return cached[0]

    assertion = _build_jwt_assertion(service_account)
    resp = await http_client.post(
        _TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
    )
    resp.raise_for_status()
    body = resp.json()
    token = body["access_token"]
    expires_in = int(body.get("expires_in", 3600))
    _token_cache[project_id] = (token, time.time() + expires_in)
    return token


async def send_fcm(
    device_token: str,
    title: str,
    body: str,
    *,
    http_client: httpx.AsyncClient,
    service_account_json: str,
) -> None:
    """Deliver a notification to one FCM registration token."""
    service_account = _parse_service_account(service_account_json)
    project_id = service_account["project_id"]
    access_token = await _access_token(http_client, service_account)

    url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
    payload = {
        "message": {
            "token": device_token,
            "notification": {"title": title, "body": body},
            "data": {"title": title, "body": body},
        }
    }

    resp = await http_client.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    resp.raise_for_status()
    _logger.debug("FCM sent token=%r… status=%s", device_token[:12], resp.status_code)
