"""Integration smoke tests for the Centrifugo publish pipeline.

These tests verify that the CentrifugoClient can successfully publish events
to a live Centrifugo instance via the HTTP API.  They do NOT subscribe via
WebSocket — that subscriber-side coverage is deferred to the W1 test suite.

Run with:
    docker compose up -d centrifugo
    pytest -m integration tests/integration/test_centrifugo.py
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_centrifugo_publish_thread_event(centrifugo_client, run_id):
    """Publishing to a thread channel succeeds (HTTP 200, no exception)."""
    thread_id = uuid.uuid4()
    await centrifugo_client.publish(
        channel=f"thread:{thread_id}",
        data={
            "id": 1,
            "thread_id": str(thread_id),
            "event_type": "user_message",
            "actor_id": f"user:{run_id}",
            "actor_name": "Integration Test",
            "content": f"smoke test message [{run_id}]",
            "metadata": {},
            "created_at": "2026-01-01T12:00:00+00:00",
        },
    )


@pytest.mark.asyncio
async def test_centrifugo_publish_council_event(centrifugo_client, run_id):
    """Publishing a structured council stage event succeeds."""
    council_id = str(uuid.uuid4())
    await centrifugo_client.publish_council_event(
        council_id=council_id,
        event_type="stage_started",
        payload={"stage": "gather", "run_id": run_id},
    )


@pytest.mark.asyncio
async def test_centrifugo_publish_multiple_events_same_channel(centrifugo_client, run_id):
    """Multiple publishes to the same channel all succeed."""
    thread_id = uuid.uuid4()
    channel = f"thread:{thread_id}"

    for i in range(3):
        await centrifugo_client.publish(
            channel=channel,
            data={
                "id": i + 1,
                "thread_id": str(thread_id),
                "event_type": "user_message",
                "actor_id": f"user:{run_id}",
                "actor_name": "Integration Test",
                "content": f"message {i + 1} [{run_id}]",
                "metadata": {},
                "created_at": "2026-01-01T12:00:00+00:00",
            },
        )


@pytest.mark.asyncio
async def test_centrifugo_publish_council_started(centrifugo_client, run_id):
    """council_started event shape matches what councils.py emits."""
    thread_id = uuid.uuid4()
    council_id = str(uuid.uuid4())
    await centrifugo_client.publish(
        channel=f"thread:{thread_id}",
        data={
            "id": 1,
            "thread_id": str(thread_id),
            "event_type": "council_started",
            "actor_id": "system",
            "actor_name": "",
            "content": None,
            "metadata": {
                "council_id": council_id,
                "question": f"Should we proceed? [{run_id}]",
                "member_count": 3,
            },
            "created_at": "2026-01-01T12:00:00+00:00",
        },
    )
