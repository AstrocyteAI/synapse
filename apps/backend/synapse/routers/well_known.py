"""Well-known discovery endpoints.

GET /.well-known/jwks.json           — RS256 public key (local auth mode)
GET /.well-known/openid-configuration — minimal OIDC discovery document

These are only meaningful when SYNAPSE_AUTH_MODE=local.  They are registered
unconditionally so that Cerebro's JWTVerifier can auto-discover the JWKS URL
during migration testing without extra config.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from synapse.auth.local import build_jwks

router = APIRouter(tags=["well-known"])


@router.get("/.well-known/jwks.json")
async def jwks(request: Request) -> dict:
    settings = request.app.state.settings
    if not settings.synapse_local_jwt_public_key:
        raise HTTPException(
            status_code=503,
            detail="Local auth not configured (SYNAPSE_LOCAL_JWT_PUBLIC_KEY not set)",
        )
    return build_jwks(settings)


@router.get("/.well-known/openid-configuration")
async def oidc_discovery(request: Request) -> dict:
    settings = request.app.state.settings
    issuer = settings.synapse_local_jwt_issuer
    return {
        "issuer": issuer,
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "token_endpoint": f"{issuer}/v1/auth/login",
        "userinfo_endpoint": f"{issuer}/v1/auth/me",
        "response_types_supported": ["token"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }
