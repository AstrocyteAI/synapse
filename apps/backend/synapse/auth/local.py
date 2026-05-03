"""Local email/password auth — password hashing and RS256 JWT issuance.

Used when SYNAPSE_AUTH_MODE=local.  The issued tokens are standard RS256 JWTs
with a JWKS endpoint, so Cerebro's JWTVerifier can validate them unchanged
during migration.  The ``synapse_role`` claim name matches the Casdoor token
template — zero Flutter code change on upgrade.
"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import bcrypt
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from synapse.config import Settings

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Key loading — cached so PEM parsing happens once per process
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _private_key(pem: str) -> RSAPrivateKey:
    return load_pem_private_key(pem.encode(), password=None)  # type: ignore[return-value]


@lru_cache(maxsize=1)
def _public_key(pem: str) -> RSAPublicKey:
    return load_pem_public_key(pem.encode())  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# JWT issuance
# ---------------------------------------------------------------------------


def issue_token(user_id: str, email: str, role: str, settings: Settings) -> str:
    """Sign and return a short-lived RS256 access token."""
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        # Claim name matches Casdoor token template — no Flutter change on migration
        "synapse_role": role,
        "iss": settings.synapse_local_jwt_issuer,
        "aud": settings.synapse_jwt_audience,
        "iat": now,
        "exp": now + timedelta(seconds=settings.synapse_local_jwt_ttl_seconds),
    }
    return jwt.encode(
        payload, _private_key(settings.synapse_local_jwt_private_key), algorithm="RS256"
    )


# ---------------------------------------------------------------------------
# JWKS
# ---------------------------------------------------------------------------


def _b64url(n: int) -> str:
    length = (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()


def build_jwks(settings: Settings) -> dict:
    """Return the RS256 public key as a JWK Set for /.well-known/jwks.json."""
    pub = _public_key(settings.synapse_local_jwt_public_key)
    nums = pub.public_numbers()
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "synapse-local-1",
                "n": _b64url(nums.n),
                "e": _b64url(nums.e),
            }
        ]
    }
