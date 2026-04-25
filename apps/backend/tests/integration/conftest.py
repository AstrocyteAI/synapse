"""Integration test fixtures — requires a live Astrocyte gateway.

Run with:
    docker compose up -d astrocyte-postgres astrocyte-gateway
    pytest -m integration

Or set ASTROCYTE_GATEWAY_URL to point at a running instance.
"""

from __future__ import annotations

import os
import uuid

import httpx
import pytest
import pytest_asyncio

from synapse.memory.context import AstrocyteContext
from synapse.memory.gateway_client import AstrocyteGatewayClient

GATEWAY_URL = os.environ.get("ASTROCYTE_GATEWAY_URL", "http://localhost:8080")
GATEWAY_API_KEY = os.environ.get("ASTROCYTE_TOKEN", "dev-astrocyte-api-key")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring a live Astrocyte gateway (skipped without --integration flag)",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration", default=False):
        skip = pytest.mark.skip(reason="pass --integration to run integration tests")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip)


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests against a live Astrocyte gateway",
    )


@pytest_asyncio.fixture(scope="session")
async def http_client():
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def gateway(http_client):
    """Real AstrocyteGatewayClient — requires gateway at ASTROCYTE_GATEWAY_URL."""
    return AstrocyteGatewayClient(
        base_url=GATEWAY_URL,
        api_key=GATEWAY_API_KEY,
        http_client=http_client,
    )


@pytest.fixture
def run_id() -> str:
    """Unique tag per test run — prevents cross-test memory pollution."""
    return f"integration-test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def context(run_id) -> AstrocyteContext:
    """Each test run gets an isolated principal so retained memories don't bleed."""
    return AstrocyteContext(
        principal=f"test-user:{run_id}",
        tenant_id=f"test-tenant:{run_id}",
    )
