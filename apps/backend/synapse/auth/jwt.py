"""JWT validation — HS256 (dev) and RS256 OIDC (production)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Header, HTTPException, Request
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from synapse.config import Settings

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    sub: str
    principal: str           # e.g. "user:abc123"
    tenant_id: str | None
    roles: list[str]
    raw_claims: dict[str, Any]


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _decode_hs256(token: str, settings: Settings) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.synapse_jwt_secret,
            algorithms=["HS256"],
            audience=settings.synapse_jwt_audience or None,
        )
    except PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e


def _decode_oidc(token: str, settings: Settings) -> dict[str, Any]:
    if not settings.synapse_jwt_jwks_url:
        raise HTTPException(status_code=500, detail="SYNAPSE_JWT_JWKS_URL is not configured")
    try:
        client = _jwks_client(settings.synapse_jwt_jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        decode_kwargs: dict[str, Any] = {
            "algorithms": ["RS256"],
            "audience": settings.synapse_jwt_audience or None,
        }
        if settings.synapse_jwt_issuer:
            decode_kwargs["issuer"] = settings.synapse_jwt_issuer
        return jwt.decode(token, signing_key.key, **decode_kwargs)
    except PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid OIDC token: {e}") from e


def _build_user(payload: dict[str, Any]) -> AuthenticatedUser:
    sub = payload.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    roles_claim = payload.get("synapse_roles", [])
    roles = roles_claim if isinstance(roles_claim, list) else [roles_claim]

    tenant_raw = payload.get("synapse_tenant")
    tenant_id = str(tenant_raw).strip() if tenant_raw else None

    return AuthenticatedUser(
        sub=sub,
        principal=f"user:{sub}",
        tenant_id=tenant_id,
        roles=[str(r) for r in roles],
        raw_claims=payload,
    )


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser:
    """FastAPI dependency — validates Bearer JWT and returns the authenticated user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization.removeprefix("Bearer ").strip()
    settings: Settings = request.app.state.settings

    if settings.synapse_auth_mode == "jwt_hs256":
        payload = _decode_hs256(token, settings)
    else:
        payload = _decode_oidc(token, settings)

    return _build_user(payload)
