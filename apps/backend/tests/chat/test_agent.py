"""Tests for synapse.chat.agent — the Pydantic AI agent loop.

Uses Pydantic AI's ``TestModel`` to drive the agent without a real provider.
Covers the SSE event emission contract: session_started → optional tokens /
tool_calls / tool_results → message_complete.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai.models.test import TestModel

from synapse.chat.agent import stream_chat_response
from synapse.db.models import ThreadEventType


def _make_chat_session(
    *,
    session_id: uuid.UUID | None = None,
    thread_id: uuid.UUID | None = None,
    tenant_id: str | None = "tenant-test",
    agent_config: dict | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = session_id or uuid.uuid4()
    s.thread_id = thread_id or uuid.uuid4()
    s.tenant_id = tenant_id
    s.created_by = "user:test"
    s.title = "Chat"
    s.status = "active"
    s.council_id = None
    s.agent_config = agent_config or {"model": "test"}
    s.parent_session_id = None
    s.parent_fork_event_id = None
    s.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    s.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return s


class _AppendEventRecorder:
    """Captures every append_event call so tests can assert ordering."""

    def __init__(self):
        self.calls: list[dict] = []
        self._next_id = 1

    async def __call__(self, db, **kwargs):
        self._next_id += 1
        event = MagicMock()
        event.id = self._next_id
        event.thread_id = kwargs.get("thread_id")
        event.event_type = kwargs.get("event_type")
        event.actor_id = kwargs.get("actor_id")
        event.actor_name = kwargs.get("actor_name", "")
        event.content = kwargs.get("content")
        event.event_metadata = kwargs.get("metadata", {}) or {}
        event.created_at = datetime.now(UTC)
        self.calls.append(kwargs | {"_id": event.id})
        return event


def _parse_sse(line: str) -> dict:
    """Strip the ``data: ``/``\\n\\n`` wrapper and return the JSON payload."""
    assert line.startswith("data: ")
    return json.loads(line[len("data: ") :].strip())


@pytest.mark.asyncio
async def test_stream_emits_session_started_then_message_complete(monkeypatch):
    """Happy path: no tool calls, agent returns canned text. Verifies
    the basic SSE envelope + persistence pattern."""

    session = _make_chat_session(agent_config={"model": "test"})

    recorder = _AppendEventRecorder()
    monkeypatch.setattr("synapse.chat.agent.append_event", recorder)

    # Force the LLMClient model translation to leave "test" alone — we
    # then override the Agent's model directly.
    monkeypatch.setattr("synapse.chat.agent._to_pydantic_ai_model_spec", lambda m: m)

    test_model = TestModel(custom_output_text="Here's the answer.")

    # Patch the Agent constructor to inject the TestModel.
    real_agent_cls = __import__("synapse.chat.agent", fromlist=["Agent"]).Agent

    def patched_agent(_model_spec, **kw):
        # Replace whatever model the caller passed with our TestModel.
        return real_agent_cls(test_model, **kw)

    monkeypatch.setattr("synapse.chat.agent.Agent", patched_agent)

    db = AsyncMock()
    astrocyte = MagicMock()

    events = []
    async for line in stream_chat_response(
        db=db,
        astrocyte=astrocyte,
        session=session,
        user_message="hello",
        principal="user:test",
        actor_name="Alice",
    ):
        events.append(_parse_sse(line))

    # Expect at least: session_started → token(s) → message_complete.
    types = [e["type"] for e in events]
    assert types[0] == "session_started"
    assert types[-1] == "message_complete"
    assert events[0]["user_message_event_id"] is not None
    assert events[-1]["message_event_id"] is not None

    # Persistence: user_message + reflection at minimum.
    persisted_types = [c["event_type"] for c in recorder.calls]
    assert ThreadEventType.user_message in persisted_types
    assert ThreadEventType.reflection in persisted_types

    # Reflection content matches what the model returned.
    reflection_calls = [c for c in recorder.calls if c["event_type"] == ThreadEventType.reflection]
    assert len(reflection_calls) == 1
    assert reflection_calls[0]["content"] == "Here's the answer."


@pytest.mark.asyncio
async def test_stream_emits_tool_call_and_tool_result_when_agent_uses_tool(monkeypatch):
    """When the agent invokes a tool, both tool_call and tool_result SSE
    events fire, and both are persisted to the thread_events log."""

    session = _make_chat_session(
        agent_config={"model": "test", "tools": ["synapse_council_recall_precedent"]}
    )

    recorder = _AppendEventRecorder()
    monkeypatch.setattr("synapse.chat.agent.append_event", recorder)
    monkeypatch.setattr("synapse.chat.agent._to_pydantic_ai_model_spec", lambda m: m)

    # TestModel with call_tools=["synapse_council_recall_precedent"] invokes
    # the listed tool exactly once with synthesised args.
    test_model = TestModel(
        custom_output_text="Based on the precedent, proceed.",
        call_tools=["synapse_council_recall_precedent"],
    )

    real_agent_cls = __import__("synapse.chat.agent", fromlist=["Agent"]).Agent

    def patched_agent(_model_spec, **kw):
        return real_agent_cls(test_model, **kw)

    monkeypatch.setattr("synapse.chat.agent.Agent", patched_agent)

    # Astrocyte recall returns a single canned hit.
    hit = MagicMock()
    hit.memory_id = "mem-1"
    hit.content = "Past decision: ship it."
    hit.score = 0.95
    hit.bank_id = "precedents"
    hit.tags = []
    hit.metadata = {}
    astrocyte = MagicMock()
    astrocyte.recall = AsyncMock(return_value=[hit])

    db = AsyncMock()

    events = []
    async for line in stream_chat_response(
        db=db,
        astrocyte=astrocyte,
        session=session,
        user_message="any precedents for this?",
        principal="user:test",
    ):
        events.append(_parse_sse(line))

    types = [e["type"] for e in events]
    # tool_call must appear before tool_result; both before message_complete.
    assert "tool_call" in types
    assert "tool_result" in types
    assert types.index("tool_call") < types.index("tool_result")
    assert types.index("tool_result") < types.index("message_complete")

    # tool_call SSE event carries the tool name and event_id.
    tc = next(e for e in events if e["type"] == "tool_call")
    assert tc["tool_call"]["name"] == "synapse_council_recall_precedent"
    assert tc["event_id"] is not None

    # tool_result SSE event references the same tool_call_id.
    tr = next(e for e in events if e["type"] == "tool_result")
    assert tr["tool_call_id"] == tc["tool_call"]["id"]

    # Both persisted to thread_events.
    persisted_types = [c["event_type"] for c in recorder.calls]
    assert ThreadEventType.tool_call in persisted_types
    assert ThreadEventType.tool_result in persisted_types

    # Astrocyte was called.
    astrocyte.recall.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_emits_error_on_agent_failure(monkeypatch):
    """If the agent run raises, we emit an error SSE event and persist a
    system_event recording the failure — we don't leak the traceback."""

    session = _make_chat_session()

    recorder = _AppendEventRecorder()
    monkeypatch.setattr("synapse.chat.agent.append_event", recorder)
    monkeypatch.setattr("synapse.chat.agent._to_pydantic_ai_model_spec", lambda m: m)

    # Replace Agent with a fake that raises during run.
    class _ExplodingAgent:
        def __init__(self, *_args, **_kwargs):
            pass

        async def run(self, *_args, **_kwargs):
            raise RuntimeError("LLM provider unreachable")

    monkeypatch.setattr("synapse.chat.agent.Agent", _ExplodingAgent)

    db = AsyncMock()
    astrocyte = MagicMock()

    events = []
    async for line in stream_chat_response(
        db=db,
        astrocyte=astrocyte,
        session=session,
        user_message="anything",
        principal="user:test",
    ):
        events.append(_parse_sse(line))

    types = [e["type"] for e in events]
    assert "error" in types
    assert "message_complete" not in types
    # User message persisted before the error; system_event added when it failed.
    persisted_types = [c["event_type"] for c in recorder.calls]
    assert ThreadEventType.user_message in persisted_types
    assert ThreadEventType.system_event in persisted_types
