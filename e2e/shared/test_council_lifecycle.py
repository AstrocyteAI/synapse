"""E2E: Council lifecycle — backend-agnostic.

Runs against either synapse-backend (Path A) or cerebro-backend (Paths B/C)
via the BACKEND_URL env var consumed in conftest.py. Assertions cover only
the public REST contract; AI quality is out of scope here.
"""

from __future__ import annotations

import time

import httpx
import pytest


def _wait_for_status(
    backend: httpx.Client,
    council_id: str,
    target: str,
    timeout: int = 30,
    interval: float = 1.0,
) -> dict:
    deadline = time.monotonic() + timeout
    last_body: dict | None = None
    while time.monotonic() < deadline:
        r = backend.get(f"/v1/councils/{council_id}")
        assert r.status_code == 200, r.text
        last_body = r.json().get("data", r.json())
        if last_body.get("status") == target:
            return last_body
        time.sleep(interval)
    pytest.fail(
        f"Council {council_id} did not reach status={target!r} within {timeout}s "
        f"(last body: {last_body!r})"
    )


class TestCouncilLifecycle:
    def test_create_council(self, backend: httpx.Client) -> None:
        r = backend.post(
            "/v1/councils",
            json={"question": "E2E: Is the deployment safe?"},
        )
        assert r.status_code in (200, 201), r.text
        body = r.json().get("data", r.json())
        assert body.get("status") in ("draft", "running", "open")
        assert body.get("id") or body.get("session_id")

    def test_council_reachable_after_create(self, backend: httpx.Client) -> None:
        r = backend.post("/v1/councils", json={"question": "E2E reachability test"})
        assert r.status_code in (200, 201), r.text
        body = r.json().get("data", r.json())
        council_id = body.get("id") or body.get("session_id")

        r2 = backend.get(f"/v1/councils/{council_id}")
        assert r2.status_code == 200
        echoed = r2.json().get("data", r2.json())
        assert (echoed.get("id") or echoed.get("session_id")) == council_id

    def test_council_closes_with_verdict(self, backend: httpx.Client) -> None:
        """With SYNAPSE_LLM_PROVIDER=mock the council should close fast."""
        r = backend.post(
            "/v1/councils",
            json={"question": "E2E: Proceed with migration?"},
        )
        assert r.status_code in (200, 201), r.text
        body = r.json().get("data", r.json())
        council_id = body.get("id") or body.get("session_id")

        closed = _wait_for_status(backend, council_id, "closed", timeout=60)
        assert closed.get("verdict"), "Expected non-empty verdict after close"
