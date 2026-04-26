"""ntfy push notification sender for Synapse notifications.

ntfy is a self-hostable, open-source notification service (MIT, Go).
- Android: UnifiedPush WebSocket — no Google FCM required
- iOS: relays via APNs (unavoidable at platform level)

Operators self-host ntfy or use ntfy.sh. Topic names are stored as
device_tokens.token values and are user-controlled (treat as secrets).

Docs: https://docs.ntfy.sh/publish/
"""

from __future__ import annotations

import logging

import httpx

_logger = logging.getLogger(__name__)


async def send_ntfy(
    topic: str,
    title: str,
    body: str,
    *,
    http_client: httpx.AsyncClient,
    ntfy_url: str,
    token: str = "",
    priority: str = "default",
    tags: list[str] | None = None,
) -> None:
    """POST a notification to a ntfy topic.

    Args:
        topic: ntfy topic name or full URL (e.g. ``my-topic`` or
            ``https://ntfy.sh/my-topic``). If just a name, it is appended
            to ``ntfy_url``.
        title: Notification title.
        body: Notification body text.
        http_client: Shared async HTTP client.
        ntfy_url: Base URL of the ntfy server (e.g. ``https://ntfy.sh``).
        token: Optional Bearer token for authenticated topics.
        priority: ntfy priority: ``min``, ``low``, ``default``, ``high``, ``urgent``.
        tags: Optional emoji/tag shortcodes (e.g. ``["tada", "synapse"]``).

    Raises:
        httpx.HTTPStatusError: on non-2xx response.
    """
    # If the caller passed a full URL, use it directly; otherwise build one.
    if topic.startswith("http://") or topic.startswith("https://"):
        url = topic
    else:
        url = f"{ntfy_url.rstrip('/')}/{topic}"

    headers: dict[str, str] = {
        "Title": title,
        "Priority": priority,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if tags:
        headers["Tags"] = ",".join(tags)

    resp = await http_client.post(url, content=body.encode("utf-8"), headers=headers)
    resp.raise_for_status()

    _logger.debug("ntfy sent to topic=%r status=%s", topic, resp.status_code)
