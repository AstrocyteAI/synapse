"""Issue short-lived Centrifugo connection JWTs."""

from __future__ import annotations

import time

import jwt

from synapse.config import Settings


def issue_connection_token(
    user_id: str,
    settings: Settings,
    channels: list[str] | None = None,
) -> str:
    """
    Sign a Centrifugo connection JWT for the given user.

    The token is validated by Centrifugo using CENTRIFUGO_TOKEN_HMAC_SECRET_KEY.
    See: https://centrifugal.dev/docs/server/authentication
    """
    now = int(time.time())
    claims: dict = {
        "sub": user_id,
        "iat": now,
        "exp": now + settings.centrifugo_token_ttl_seconds,
    }
    # Optional: restrict which channels this token can subscribe to
    if channels:
        claims["channels"] = channels

    return jwt.encode(
        claims,
        settings.centrifugo_token_secret,
        algorithm="HS256",
    )
