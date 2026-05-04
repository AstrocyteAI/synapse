"""Shared E2E fixtures for Path A (and reusable by downstream consumers).

The fixtures here are deliberately backend-agnostic: tests in `shared/` consume
them via `BACKEND_URL` and an `auth` strategy. Path-A defaults to HS256 against
synapse-backend; downstream consumers (e.g. cerebro Path B/C) can override
`BACKEND_URL` and `AUTH_MODE=oidc` without touching the tests.

Auth modes
──────────
hs256 (default)
    HS256 JWTs signed with SYNAPSE_JWT_SECRET. Used by Path A where Synapse
    runs in jwt_hs256 mode.

oidc
    Real OIDC code flow against an issuer (e.g. Casdoor). Used by Cerebro
    Paths B/C — wired in by the cerebro repo's e2e harness.

Tenancy
───────
Path A is single-tenant. The TEST_TENANT_ID constant exists so tenant-aware
tests can be parametrized identically across paths; on Path A it is simply
threaded through but ignored by the backend.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
import jwt
import pytest


# ---------------------------------------------------------------------------
# Environment knobs — set by the path-specific compose / workflow
# ---------------------------------------------------------------------------

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
WEBHOOK_SINK_URL = os.environ.get("WEBHOOK_SINK_URL", "http://localhost:9999")
ASTROCYTE_GATEWAY_URL = os.environ.get("ASTROCYTE_GATEWAY_URL", "http://localhost:8080")
ASTROCYTE_TOKEN = os.environ.get("ASTROCYTE_TOKEN", "e2e-astrocyte-api-key")

AUTH_MODE = os.environ.get("AUTH_MODE", "hs256")
SYNAPSE_JWT_SECRET = os.environ.get(
    "SYNAPSE_JWT_SECRET", "e2e-synapse-jwt-secret-for-testing-only"
)
SYNAPSE_JWT_AUDIENCE = os.environ.get("SYNAPSE_JWT_AUDIENCE", "synapse")

TEST_TENANT_ID = os.environ.get(
    "TEST_TENANT_ID", "00000000-0000-0000-0000-000000000001"
)

MULTI_TENANT = os.environ.get("MULTI_TENANT", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Auth strategy — abstracts over HS256 (Path A) and OIDC (Path B/C)
# ---------------------------------------------------------------------------


class AuthStrategy(Protocol):
    def token(self, role: str = "admin", tenant_id: str = TEST_TENANT_ID, sub: str = "e2e-admin") -> str: ...


@dataclass
class HS256Strategy:
    secret: str
    audience: str

    def token(
        self,
        role: str = "admin",
        tenant_id: str = TEST_TENANT_ID,
        sub: str = "e2e-admin",
    ) -> str:
        now = int(time.time())
        payload = {
            "sub": sub,
            "aud": self.audience,
            "roles": [role],
            "tenant_id": tenant_id,
            "iat": now,
            "exp": now + 3600,
        }
        return jwt.encode(payload, self.secret, algorithm="HS256")


def _build_auth() -> AuthStrategy:
    if AUTH_MODE == "hs256":
        return HS256Strategy(secret=SYNAPSE_JWT_SECRET, audience=SYNAPSE_JWT_AUDIENCE)
    raise NotImplementedError(
        f"AUTH_MODE={AUTH_MODE!r} not supported in synapse e2e. "
        "OIDC strategy lives in the cerebro e2e harness."
    )


# ---------------------------------------------------------------------------
# Pytest markers
# ---------------------------------------------------------------------------


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_multi_tenant: skip unless MULTI_TENANT=true (Cerebro Path B/C only)",
    )
    config.addinivalue_line("markers", "slow: long-running, nightly only")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if MULTI_TENANT:
        return
    skip_multi = pytest.mark.skip(reason="MULTI_TENANT=false (Path A is single-tenant)")
    for item in items:
        if "requires_multi_tenant" in item.keywords:
            item.add_marker(skip_multi)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def auth() -> AuthStrategy:
    return _build_auth()


@pytest.fixture(scope="session")
def backend(auth: AuthStrategy) -> httpx.Client:
    """Admin client against the backend under test."""
    return httpx.Client(
        base_url=BACKEND_URL,
        headers={"Authorization": f"Bearer {auth.token()}"},
        timeout=30.0,
    )


@pytest.fixture(scope="session")
def astrocyte() -> httpx.Client:
    """Direct client to the Astrocyte gateway — for round-trip assertions."""
    return httpx.Client(
        base_url=ASTROCYTE_GATEWAY_URL,
        headers={"Authorization": f"Bearer {ASTROCYTE_TOKEN}"},
        timeout=30.0,
    )


@pytest.fixture(scope="session")
def webhook_sink() -> httpx.Client:
    return httpx.Client(base_url=WEBHOOK_SINK_URL, timeout=10.0)


@pytest.fixture(autouse=True)
def _clear_webhook_sink(webhook_sink: httpx.Client) -> None:
    """Wipe recorded webhooks before each test so assertions are test-local."""
    try:
        webhook_sink.delete("/recorded")
    except httpx.HTTPError:
        # Sink isn't required for every test; tolerate it being absent.
        pass
