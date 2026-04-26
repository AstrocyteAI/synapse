"""JWT validation — HS256 (dev) and RS256 OIDC (production).

Also handles API key authentication for machine-to-machine access (B9).
API keys start with "sk-" and are validated by SHA-256 hash lookup.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, Request
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.config import Settings
from synapse.db.session import get_session as get_db_session

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    sub: str
    principal: str  # e.g. "user:abc123"
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


async def _authenticate_api_key(token: str, db: AsyncSession) -> AuthenticatedUser:
    """Look up an API key by its SHA-256 hash and return an AuthenticatedUser."""
    # Import here to avoid circular imports at module load time
    from synapse.db.models import ApiKey

    key_hash = hashlib.sha256(token.encode()).hexdigest()
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.revoked_at.is_(None))
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    # Update last_used_at
    api_key.last_used_at = datetime.now(UTC)
    await db.commit()
    return AuthenticatedUser(
        sub=api_key.created_by,
        principal=api_key.created_by,
        tenant_id=api_key.tenant_id,
        roles=list(api_key.roles or ["member"]),
        raw_claims={"sub": api_key.created_by, "api_key_id": str(api_key.id)},
    )


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns (raw_key, key_hash, key_prefix).
    raw_key is shown once and never stored.
    key_hash is the SHA-256 hex digest stored in the DB.
    key_prefix is "sk-" + first 8 hex chars (display only).
    """
    raw = "sk-" + secrets.token_hex(32)  # "sk-" + 64 hex = 67 chars
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    key_prefix = raw[:11]  # "sk-" + first 8 chars
    return raw, key_hash, key_prefix


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db_session),
) -> AuthenticatedUser:
    """FastAPI dependency — validates Bearer JWT or API key and returns the authenticated user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = authorization.removeprefix("Bearer ").strip()

    # API key path — tokens starting with "sk-" are hashed and looked up in the DB
    if token.startswith("sk-"):
        return await _authenticate_api_key(token, db)

    settings: Settings = request.app.state.settings

    if settings.synapse_auth_mode == "jwt_hs256":
        payload = _decode_hs256(token, settings)
    else:
        payload = _decode_oidc(token, settings)

    return _build_user(payload)
