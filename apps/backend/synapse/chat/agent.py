"""Chat-with-tools agent loop — Pydantic AI Agent + tools + SSE streaming.

This module implements the agent loop behind ``POST /v1/chat/sessions/{id}/messages``.
The endpoint returns a ``text/event-stream`` of ``ChatStreamEvent`` shapes per
``priv/contracts/chat-api-v1.openapi.json``:

  * ``session_started``   — emitted before the agent runs; carries the
                            persisted ``user_message`` event id
  * ``tool_call``         — emitted when the agent invokes a tool
  * ``tool_result``       — emitted when a tool returns
  * ``message_complete``  — emitted once the agent finishes; carries the
                            persisted ``reflection`` event id
  * ``error``             — emitted if anything raises

The ``token`` event (incremental text deltas) is wired up but only emitted
for providers Pydantic AI exposes ``PartDeltaEvent`` for — most providers
return text via stream deltas, so this works out of the box for OpenAI /
Anthropic / Groq / etc.

Tool-call and tool-result events are also persisted to ``thread_events``
(via ``ThreadEventType.tool_call`` / ``tool_result``) as the agent
runs, so the full trace is durable + replayable later via ``thread_events``
cursor pagination.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    FinalResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPartDelta,
)
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.chat.tools import build_toolset
from synapse.council.thread import append_event
from synapse.db.models import ChatSession, ThreadEventType
from synapse.llm.client import _to_pydantic_ai_model_spec
from synapse.memory.gateway_client import AstrocyteGatewayClient

_logger = logging.getLogger(__name__)


@dataclass
class AgentDeps:
    """Runtime dependencies a tool can resolve via ``RunContext.deps``."""

    db: AsyncSession
    astrocyte: AstrocyteGatewayClient
    tenant_id: str | None
    principal: str
    session: ChatSession


async def stream_chat_response(
    *,
    db: AsyncSession,
    astrocyte: AstrocyteGatewayClient,
    session: ChatSession,
    user_message: str,
    principal: str,
    actor_name: str = "",
) -> AsyncIterator[str]:
    """Async generator yielding SSE-formatted event lines for one chat turn.

    Each yield is a complete SSE record (``"data: {...json...}\\n\\n"``) ready
    to be written to a ``text/event-stream`` response.

    The agent loop:
      1. Append the user message as ``user_message`` to the thread.
      2. Emit ``session_started``.
      3. Run the Pydantic AI agent with the configured tools + model.
         As tool_call / tool_result events fire, persist them to
         ``thread_events`` and emit corresponding SSE events.
      4. On completion, append a ``reflection`` event with the final text;
         emit ``message_complete``.
      5. On any exception, append a ``system_event`` recording the failure
         and emit ``error``.
    """
    # 1. Persist the user message before doing anything else — that way
    # the user_message event id is stable in the session_started payload
    # even if the agent loop fails partway through.
    user_event = await append_event(
        db,
        thread_id=session.thread_id,
        event_type=ThreadEventType.user_message,
        actor_id=principal,
        actor_name=actor_name,
        content=user_message,
    )

    # 2. session_started — clients hold this event id as the cursor for
    # any "show me what just happened" history scroll.
    yield _sse(
        {
            "type": "session_started",
            "session_id": str(session.id),
            "user_message_event_id": user_event.id,
        }
    )

    deps = AgentDeps(
        db=db,
        astrocyte=astrocyte,
        tenant_id=session.tenant_id,
        principal=principal,
        session=session,
    )

    agent_config = session.agent_config or {}
    model = agent_config.get("model") or "openai:gpt-4o"
    instructions = agent_config.get("instructions") or None
    tool_names = agent_config.get("tools") or []

    agent = Agent(
        _to_pydantic_ai_model_spec(model),
        deps_type=AgentDeps,
        instructions=instructions,
        tools=build_toolset(tool_names),
    )

    # 3. Queue-based bridge from Pydantic AI's event_stream_handler into
    # our SSE generator. The handler is an async callable invoked by the
    # agent; we put events on the queue, the generator drains and yields.
    queue: asyncio.Queue[Any] = asyncio.Queue()
    DONE = object()

    async def handler(ctx, stream):
        async for event in stream:
            await queue.put(event)

    final_text = ""

    async def run_and_signal():
        nonlocal final_text
        try:
            result = await agent.run(
                user_message,
                deps=deps,
                event_stream_handler=handler,
            )
            final_text = result.output or ""
        finally:
            await queue.put(DONE)

    runner = asyncio.create_task(run_and_signal())

    try:
        while True:
            event = await queue.get()
            if event is DONE:
                break
            async for sse_chunk in _translate_event(
                event=event,
                db=db,
                thread=session,
                principal=principal,
                actor_name=actor_name,
            ):
                yield sse_chunk
    except Exception as exc:  # pragma: no cover — defensive
        _logger.exception("chat agent loop failed: session_id=%s", session.id)
        await append_event(
            db,
            thread_id=session.thread_id,
            event_type=ThreadEventType.system_event,
            actor_id="system",
            content=f"Agent loop error: {exc}",
            metadata={"category": "agent_failure", "severity": "error"},
        )
        yield _sse({"type": "error", "error": str(exc)})
        runner.cancel()
        return

    # Surface any exception raised inside the agent run itself.
    try:
        await runner
    except Exception as exc:
        _logger.exception("chat agent run raised: session_id=%s", session.id)
        await append_event(
            db,
            thread_id=session.thread_id,
            event_type=ThreadEventType.system_event,
            actor_id="system",
            content=f"Agent run error: {exc}",
            metadata={"category": "agent_failure", "severity": "error"},
        )
        yield _sse({"type": "error", "error": str(exc)})
        return

    # 4. Persist the final response as a reflection event.
    reflection_event = await append_event(
        db,
        thread_id=session.thread_id,
        event_type=ThreadEventType.reflection,
        actor_id=f"agent:{model}",
        actor_name=_agent_display_name(agent_config),
        content=final_text,
        metadata={
            "model_id": model,
            "finish_reason": "stop",
        },
    )

    yield _sse(
        {
            "type": "message_complete",
            "message_event_id": reflection_event.id,
            "finish_reason": "stop",
        }
    )


# ---------------------------------------------------------------------------
# Pydantic AI event → SSE event translation
# ---------------------------------------------------------------------------


async def _translate_event(
    *,
    event: Any,
    db: AsyncSession,
    thread,
    principal: str,
    actor_name: str,
) -> AsyncIterator[str]:
    """Map a Pydantic AI streaming event to ChatStreamEvent SSE lines.

    Persists tool_call and tool_result events to ``thread_events`` so the
    durable log captures the full agent trace. Text deltas (``PartDeltaEvent``
    on a text part) are emitted as ``token`` SSE events but not persisted —
    the cumulative text is captured by the final ``reflection`` event.
    """
    # Streaming token deltas (incremental text) — best-effort; some
    # providers stream the whole part in one shot, in which case we get
    # a single PartStartEvent with the full content and no deltas.
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        yield _sse({"type": "token", "token": event.delta.content_delta})
        return

    if isinstance(event, PartStartEvent):
        # Initial text in a part — emit as a token so clients see something
        # immediately even if no deltas follow.
        from pydantic_ai.messages import TextPart  # local import — avoid cycle

        if isinstance(event.part, TextPart) and event.part.content:
            yield _sse({"type": "token", "token": event.part.content})
        return

    if isinstance(event, FunctionToolCallEvent):
        tool_call = event.part
        tool_call_id = tool_call.tool_call_id
        tool_name = tool_call.tool_name
        args = _coerce_tool_args(tool_call.args)

        # Persist the call to the durable log.
        persisted = await append_event(
            db,
            thread_id=thread.thread_id,
            event_type=ThreadEventType.tool_call,
            actor_id="system",
            actor_name="agent_tool_call",
            metadata={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "arguments": args,
            },
        )

        yield _sse(
            {
                "type": "tool_call",
                "event_id": persisted.id,
                "tool_call": {
                    "id": tool_call_id,
                    "name": tool_name,
                    "arguments": args,
                },
            }
        )
        return

    if isinstance(event, FunctionToolResultEvent):
        # PydAI v1.99+ exposes the tool-result content on .part;
        # .result is deprecated but kept as a fallback for older versions.
        tool_result = getattr(event, "part", None) or event.result
        tool_call_id = tool_result.tool_call_id
        tool_name = getattr(tool_result, "tool_name", None) or ""
        result_payload = _coerce_tool_result(tool_result.content)

        persisted = await append_event(
            db,
            thread_id=thread.thread_id,
            event_type=ThreadEventType.tool_result,
            actor_id=f"tool:{tool_name}" if tool_name else "tool",
            actor_name=tool_name,
            content=str(result_payload)[:1000] if result_payload is not None else None,
            metadata={
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "result": result_payload,
            },
        )

        yield _sse(
            {
                "type": "tool_result",
                "event_id": persisted.id,
                "tool_call_id": tool_call_id,
                "result": result_payload,
            }
        )
        return

    if isinstance(event, FinalResultEvent):
        # We emit message_complete after the agent.run() returns with the
        # persisted reflection event id — not here. Suppress to avoid a
        # duplicate emission.
        return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse(payload: dict[str, Any]) -> str:
    """Format a payload as a single SSE record."""
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _coerce_tool_args(args: Any) -> dict[str, Any]:
    """Tool args come through as either a JSON string or a dict depending on
    the provider. Normalise to dict for the wire payload."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {"_raw": args}
    return {"_raw": str(args)}


def _coerce_tool_result(content: Any) -> Any:
    """Tool result content varies wildly (string, dict, dataclass, etc.).
    Pass through dicts / lists / scalars; stringify everything else."""
    if content is None:
        return None
    if isinstance(content, (dict, list, str, int, float, bool)):
        return content
    return str(content)


def _agent_display_name(agent_config: dict[str, Any]) -> str:
    """Human-readable name surfaced on reflection events."""
    name = agent_config.get("name")
    if isinstance(name, str) and name:
        return name
    model = agent_config.get("model") or "agent"
    return model
