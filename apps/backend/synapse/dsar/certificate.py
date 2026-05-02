"""HMAC-SHA256 fulfilment certificate signing.

Synapse single-tenant signs DSAR fulfilment certificates with a single
HMAC-SHA256 key. An auditor verifies a certificate by re-canonicalising
the payload and recomputing the HMAC against the deployment's signing
secret.

Why HMAC instead of RS256/JWS? Single-tenant deployments rarely have a
JWKS endpoint and rarely need an auditor who lacks the signing secret.
HMAC keeps the dependency surface minimal (``hmac`` + ``hashlib`` —
both stdlib). Cerebro Enterprise additionally supports detached RS256
JWS for externally-verifiable attestation against a published JWKS;
upgrade there if you need that.

## Wire shape (v1)

::

    {
      "version": 1,
      "format": "synapse-dsar-cert-v1",
      "payload": {
        "request_id": "<uuid>",
        "subject_principal": "user:abc",
        "request_type": "erasure",
        "tenant_id": "tenant-1" | null,
        "completed_by": "user:reviewer",
        "completed_at": "2026-05-02T10:00:00+00:00",
        "actions": [...]    # see worker.run_erasure
      },
      "signature": {
        "alg": "HMAC-SHA256",
        "value": "<base64url(HMAC(secret, canonical_json(payload)))>"
      }
    }

The signature covers a *canonical* JSON encoding of ``payload`` with
sorted keys and ``(", ", ": ")`` separators dropped to ``(",", ":")``
so whitespace differences don't break verification across languages.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

# Format identifier — bumped if the canonicalisation rules or payload
# shape change so verifiers can short-circuit on mismatch.
FORMAT = "synapse-dsar-cert-v1"
VERSION = 1
ALG = "HMAC-SHA256"


def build_and_sign(payload: dict[str, Any], *, secret: str) -> dict[str, Any]:
    """Wrap ``payload`` in the certificate envelope and sign.

    Raises ``ValueError`` if the secret is empty — operators must supply
    ``synapse_dsar_signing_secret`` before approving requests; the
    router already guards on this but the signing path enforces it as
    a second line of defense.
    """
    if not secret:
        raise ValueError(
            "synapse_dsar_signing_secret is not configured — DSAR "
            "fulfilment certificates cannot be signed. Set the env var "
            "before approving DSAR requests."
        )
    canonical = _canonical_json(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).digest()
    return {
        "version": VERSION,
        "format": FORMAT,
        "payload": payload,
        "signature": {
            "alg": ALG,
            "value": base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii"),
        },
    }


def verify(certificate: dict[str, Any], *, secret: str) -> bool:
    """Constant-time signature verification against ``secret``.

    Returns ``False`` on any structural problem (wrong format, missing
    fields, malformed base64) rather than raising — verifiers usually
    want a boolean for audit reports, not stack traces.
    """
    if not secret:
        return False
    try:
        if certificate.get("format") != FORMAT or certificate.get("version") != VERSION:
            return False
        sig_block = certificate.get("signature") or {}
        if sig_block.get("alg") != ALG:
            return False
        provided_b64 = sig_block.get("value")
        if not isinstance(provided_b64, str):
            return False
        # urlsafe_b64decode requires correct padding — reattach it.
        padding = "=" * (-len(provided_b64) % 4)
        provided = base64.urlsafe_b64decode(provided_b64 + padding)
        canonical = _canonical_json(certificate["payload"]).encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).digest()
        return hmac.compare_digest(provided, expected)
    except (KeyError, ValueError, TypeError, base64.binascii.Error):
        return False


def _canonical_json(payload: dict[str, Any]) -> str:
    """Deterministic JSON: sorted keys, no whitespace, NaN-safe.

    The same canonicalisation must be used on both ends of the wire so
    a verifier in any language re-derives the same byte sequence. The
    Cerebro Elixir signer uses the equivalent rules — see
    ``Synapse.DSAR.canonical_json/1``.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )
