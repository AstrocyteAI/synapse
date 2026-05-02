"""Unit tests for the HMAC-SHA256 certificate signer.

The signing module is pure crypto — no DB, no network — so the tests
are pure too. They cover the full round-trip plus the failure modes a
verifier needs to handle (tampered payload, swapped secret, malformed
envelope, missing signing secret).
"""

from __future__ import annotations

import json

import pytest

from synapse.dsar import certificate

_PAYLOAD = {
    "request_id": "11111111-1111-1111-1111-111111111111",
    "subject_principal": "user:alice",
    "request_type": "erasure",
    "completed_by": "user:reviewer",
    "completed_at": "2026-05-02T10:00:00+00:00",
    "tenant_id": None,
    "actions": [
        {"system": "synapse", "action": "synapse_audit_events", "deleted": 3},
        {
            "system": "astrocyte",
            "action": "astrocyte_forget_principal",
            "status": "completed",
        },
    ],
}


def test_round_trip_signs_and_verifies():
    cert = certificate.build_and_sign(_PAYLOAD, secret="test-secret")
    assert certificate.verify(cert, secret="test-secret") is True


def test_envelope_carries_format_and_version():
    cert = certificate.build_and_sign(_PAYLOAD, secret="x")
    assert cert["format"] == certificate.FORMAT
    assert cert["version"] == certificate.VERSION
    assert cert["signature"]["alg"] == certificate.ALG
    assert isinstance(cert["signature"]["value"], str)
    assert cert["payload"] == _PAYLOAD


def test_verify_rejects_swapped_secret():
    cert = certificate.build_and_sign(_PAYLOAD, secret="real-secret")
    assert certificate.verify(cert, secret="other-secret") is False


def test_verify_rejects_tampered_payload():
    cert = certificate.build_and_sign(_PAYLOAD, secret="s")
    cert["payload"]["completed_by"] = "user:attacker"
    assert certificate.verify(cert, secret="s") is False


def test_verify_rejects_tampered_signature():
    cert = certificate.build_and_sign(_PAYLOAD, secret="s")
    # Flip the last char of the signature
    cert["signature"]["value"] = cert["signature"]["value"][:-1] + (
        "A" if cert["signature"]["value"][-1] != "A" else "B"
    )
    assert certificate.verify(cert, secret="s") is False


def test_verify_rejects_wrong_format():
    cert = certificate.build_and_sign(_PAYLOAD, secret="s")
    cert["format"] = "synapse-dsar-cert-v999"
    assert certificate.verify(cert, secret="s") is False


def test_verify_rejects_wrong_version():
    cert = certificate.build_and_sign(_PAYLOAD, secret="s")
    cert["version"] = 999
    assert certificate.verify(cert, secret="s") is False


def test_verify_rejects_unknown_alg():
    cert = certificate.build_and_sign(_PAYLOAD, secret="s")
    cert["signature"]["alg"] = "RS256"
    assert certificate.verify(cert, secret="s") is False


def test_verify_rejects_malformed_signature_value():
    cert = certificate.build_and_sign(_PAYLOAD, secret="s")
    cert["signature"]["value"] = "!!!not-base64!!!"
    assert certificate.verify(cert, secret="s") is False


def test_build_rejects_empty_secret():
    with pytest.raises(ValueError, match="signing_secret"):
        certificate.build_and_sign(_PAYLOAD, secret="")


def test_verify_with_empty_secret_returns_false():
    cert = certificate.build_and_sign(_PAYLOAD, secret="real")
    assert certificate.verify(cert, secret="") is False


def test_signature_is_deterministic_under_key_reordering():
    """Reordering keys in a payload must not change the signature.

    This is the canonical-JSON contract — both ends of the wire must
    derive the same byte sequence regardless of insertion order.
    """
    cert_a = certificate.build_and_sign(_PAYLOAD, secret="s")
    reordered = json.loads(json.dumps(_PAYLOAD, sort_keys=False))
    # Force a different insertion order by re-creating the dict
    shuffled = dict(reversed(list(reordered.items())))
    cert_b = certificate.build_and_sign(shuffled, secret="s")
    assert cert_a["signature"]["value"] == cert_b["signature"]["value"]
