"""S-Bypass-OIDC — real-localhost JWKS integration tests for ``jwt_oidc`` mode.

Synapse's ``_decode_oidc`` path (``synapse/auth/jwt.py``) verifies tokens
against a remote JWKS endpoint via PyJWKClient. Until now this path had
zero test coverage: HS256 mode was exercised through every router test,
but RS256/JWKS was only covered in production. The risk surface that
mocks miss includes header casing, `kid`-rotation, JWKS caching, network
errors, and PyJWT signature-verification edge cases.

This file spins up a real Werkzeug HTTP server on
``127.0.0.1:<random-port>`` via ``pytest-httpserver``, serves a JWKS
document with a real RSA public key, and exercises ``_decode_oidc``
end-to-end. Tokens are signed by the matching private key with PyJWT.

Same pattern as the OIDCIdPFixture work in Cerebro — process-level
mocks miss bugs that only show up when bytes actually move over the
wire. The full HTTP path is closer to what we'll hit against
Auth0/Keycloak/Okta in production.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from pytest_httpserver import HTTPServer

from synapse.auth.jwt import _decode_oidc, _jwks_client
from synapse.config import Settings

# ---------------------------------------------------------------------------
# Fixtures — JWKS server + matching keypair
# ---------------------------------------------------------------------------


_KID = "test-kid-1"


@pytest.fixture
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    """Fresh RSA-2048 keypair per test.

    Returns ``(private_key, jwk_public)`` — the private key signs tokens;
    the public JWK is what the JWKS endpoint serves.
    """
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()

    def _b64url_uint(value: int) -> str:
        # JWK n / e are base64url-encoded big-endian byte strings of the
        # unsigned integer. Strip leading zeros, then b64url with no
        # padding. Stdlib base64 has no urlsafe-no-padding helper for
        # ints, so we round-trip via int.to_bytes.
        import base64

        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": _KID,
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    return private_key, jwk


@pytest.fixture
def jwks_server(httpserver: HTTPServer, rsa_keypair) -> HTTPServer:
    """Real localhost JWKS endpoint at ``/jwks``."""
    _private, jwk = rsa_keypair
    httpserver.expect_request("/jwks").respond_with_json({"keys": [jwk]})
    return httpserver


@pytest.fixture
def oidc_settings(jwks_server: HTTPServer) -> Settings:
    """Synapse settings configured to verify against the localhost JWKS.

    Each test gets a fresh Settings instance and clears the
    ``_jwks_client`` lru_cache — otherwise the PyJWKClient binding
    leaks between tests because the cache key is the URL string.
    """
    _jwks_client.cache_clear()
    return Settings(
        synapse_auth_mode="jwt_oidc",
        synapse_jwt_audience="synapse",
        synapse_jwt_issuer="https://test-idp.example.com",
        synapse_jwt_jwks_url=jwks_server.url_for("/jwks"),
        # Required scaffolding fields with non-prod values
        synapse_jwt_secret="unused-in-oidc-mode",
        database_url="postgresql+asyncpg://x@x/x",
        astrocyte_gateway_url="http://x",
        astrocyte_token="x",
        centrifugo_api_url="http://x",
        centrifugo_ws_url="ws://x",
        centrifugo_api_key="x",
        centrifugo_token_secret="x" * 32,
    )


def _sign_rs256(
    private_key: rsa.RSAPrivateKey,
    *,
    sub: str = "abc123",
    aud: str | None = "synapse",
    iss: str | None = "https://test-idp.example.com",
    exp_offset: timedelta = timedelta(minutes=10),
    extra_claims: dict[str, Any] | None = None,
    kid: str | None = _KID,
) -> str:
    """Sign a fresh RS256 JWT against the test keypair.

    Defaults match what ``oidc_settings`` expects so the happy-path
    signature/audience/issuer all line up. Tests override individual
    knobs to exercise the failure paths.
    """
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": sub,
        "iat": now,
        "exp": now + exp_offset,
    }
    if aud is not None:
        claims["aud"] = aud
    if iss is not None:
        claims["iss"] = iss
    if extra_claims:
        claims.update(extra_claims)

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    headers = {"kid": kid} if kid is not None else {}
    return pyjwt.encode(claims, pem, algorithm="RS256", headers=headers)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_token_decodes_against_localhost_jwks(rsa_keypair, oidc_settings):
    """End-to-end: PyJWKClient fetches /jwks over real HTTP, finds the
    `kid`, verifies the signature, and returns the claims."""
    private, _ = rsa_keypair
    token = _sign_rs256(
        private, sub="alice", extra_claims={"name": "Alice", "synapse_roles": ["admin"]}
    )

    payload = _decode_oidc(token, oidc_settings)

    assert payload["sub"] == "alice"
    assert payload["aud"] == "synapse"
    assert payload["iss"] == "https://test-idp.example.com"
    assert payload["name"] == "Alice"
    assert payload["synapse_roles"] == ["admin"]


def test_jwks_caching_serves_second_call_without_refetching(
    rsa_keypair, oidc_settings, jwks_server
):
    """PyJWKClient caches the JWKS document. After the first decode,
    a second decode shouldn't hit the JWKS endpoint again — we verify
    by counting requests to ``/jwks`` from the server side."""
    private, _ = rsa_keypair
    t1 = _sign_rs256(private, sub="alice")
    t2 = _sign_rs256(private, sub="bob")

    _decode_oidc(t1, oidc_settings)
    _decode_oidc(t2, oidc_settings)

    # The pytest-httpserver records every matching request. Exactly one
    # JWKS fetch should have happened.
    matching = [req for req, _resp in jwks_server.log if req.path == "/jwks"]
    assert len(matching) == 1, (
        f"Expected JWKS to be fetched exactly once due to caching, got {len(matching)}"
    )


# ---------------------------------------------------------------------------
# Failure paths — what mocks couldn't catch
# ---------------------------------------------------------------------------


def test_wrong_audience_rejected(rsa_keypair, oidc_settings):
    private, _ = rsa_keypair
    token = _sign_rs256(private, aud="some-other-app")
    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401
    assert "Invalid OIDC token" in exc.value.detail


def test_wrong_issuer_rejected(rsa_keypair, oidc_settings):
    """Synapse rejects tokens from an IdP that isn't the configured issuer.

    This catches the IdP-spoof scenario: a valid token from a *different*
    OIDC provider should not authenticate against this deployment.
    """
    private, _ = rsa_keypair
    token = _sign_rs256(private, iss="https://attacker-idp.example.com")
    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401


def test_expired_token_rejected(rsa_keypair, oidc_settings):
    private, _ = rsa_keypair
    # Issued + expired in the past
    token = _sign_rs256(private, exp_offset=timedelta(minutes=-1))
    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401


def test_token_signed_by_different_key_rejected(oidc_settings):
    """An attacker can't forge tokens by swapping the signing key — the
    public key in the JWKS document is the only one that verifies."""
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign_rs256(other_key)
    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401


def test_token_with_unknown_kid_rejected(rsa_keypair, oidc_settings):
    """If the token's `kid` header doesn't match any key in the JWKS,
    PyJWKClient raises and we surface 401."""
    private, _ = rsa_keypair
    token = _sign_rs256(private, kid="some-kid-the-idp-hasnt-published")
    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401


def test_jwks_endpoint_unreachable_rejected(rsa_keypair, oidc_settings, jwks_server):
    """Operator misconfiguration — JWKS URL points at something that's
    down. Synapse must reject the token rather than crash."""
    _jwks_client.cache_clear()
    jwks_server.stop()  # tear down the localhost JWKS server

    private, _ = rsa_keypair
    token = _sign_rs256(private)

    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    # PyJWKClient surfaces network errors as PyJWTError; the wrapper
    # converts to 401. (A more aggressive impl could 503 on
    # network_error specifically — separate ticket.)
    assert exc.value.status_code == 401


def test_jwks_url_not_configured_returns_500(rsa_keypair, oidc_settings):
    """Misconfigured deployment: jwt_oidc auth mode but no JWKS URL.
    The wrapper surfaces this as 500 — distinct from the 401 token-
    rejection path so operators can grep for the misconfig signature
    in their error logs."""
    private, _ = rsa_keypair
    token = _sign_rs256(private)

    settings = oidc_settings.model_copy(update={"synapse_jwt_jwks_url": ""})
    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, settings)
    assert exc.value.status_code == 500
    assert "JWKS_URL" in exc.value.detail


def test_jwks_returns_500_rejected(rsa_keypair, oidc_settings, jwks_server):
    """JWKS endpoint reachable but broken (e.g., IdP outage returning
    error pages). Token verification must fail closed — a 500 from the
    IdP is not authorisation."""
    _jwks_client.cache_clear()
    httpserver = jwks_server
    # Override the existing JWKS handler with a 500 response
    httpserver.clear()
    httpserver.expect_request("/jwks").respond_with_data("Internal Server Error", status=500)

    private, _ = rsa_keypair
    token = _sign_rs256(private)

    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401


def test_jwks_returns_malformed_json_rejected(rsa_keypair, oidc_settings, jwks_server):
    """JWKS endpoint returns malformed JSON — PyJWKClient raises and
    we surface 401."""
    _jwks_client.cache_clear()
    httpserver = jwks_server
    httpserver.clear()
    httpserver.expect_request("/jwks").respond_with_data(
        "<html>not jwks</html>", content_type="text/html"
    )

    private, _ = rsa_keypair
    token = _sign_rs256(private)

    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401


def test_token_missing_kid_header_rejected(rsa_keypair, oidc_settings):
    """The JWKS contains exactly one key. Even so, if the token's
    header has no `kid`, PyJWKClient cannot pick a key deterministically
    and rejects — Synapse surfaces 401.

    This is intentional behaviour — IdPs are expected to set `kid` on
    every issued token; tokens without `kid` are likely forgeries or
    misconfigured non-OIDC clients."""
    private, _ = rsa_keypair
    token = _sign_rs256(private, kid=None)

    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# Sanity: tokens of completely the wrong shape
# ---------------------------------------------------------------------------


def test_garbage_token_rejected(oidc_settings):
    with pytest.raises(HTTPException) as exc:
        _decode_oidc("not.a.jwt", oidc_settings)
    assert exc.value.status_code == 401


def test_token_missing_exp_rejected(rsa_keypair, oidc_settings):
    """A token without an exp claim is treated as never-expiring;
    PyJWT's default behaviour is to reject. Verifies that default
    isn't disabled."""
    private, _ = rsa_keypair

    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Hand-build a token with no exp — Synapse's PyJWT call has the
    # default require-exp behaviour, so this should still fail closed.
    # (Some IdPs omit exp on long-lived service tokens; Synapse rejects
    # those by design — service-to-service auth uses API keys, not OIDC.)
    token = pyjwt.encode(
        {"sub": "x", "aud": "synapse", "iss": "https://test-idp.example.com"},
        pem,
        algorithm="RS256",
        headers={"kid": _KID},
    )
    with pytest.raises(HTTPException) as exc:
        _decode_oidc(token, oidc_settings)
    assert exc.value.status_code == 401
