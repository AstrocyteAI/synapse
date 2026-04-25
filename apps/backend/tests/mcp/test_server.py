"""Unit tests for the Synapse MCP server tools.

Tests exercise each tool function directly (not via the MCP protocol wire)
by constructing a minimal fake Context that exposes the lifespan_context dict.
This keeps tests fast and avoids standing up a real MCP server or DB.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synapse.db.models import CouncilStatus, ThreadEventType
from synapse.mcp.server import (
    close,
    contribute,
    join,
    recall_precedent,
    start_council,
)

# ---------------------------------------------------------------------------
# Fake Context helper
# ---------------------------------------------------------------------------


def _make_ctx(
    sessionmaker=None,
    astrocyte=None,
    centrifugo=None,
    settings=None,
) -> MagicMock:
    """Build a minimal Context substitute that exposes lifespan_context."""
    lc = {
        "sessionmaker": sessionmaker or MagicMock(),
        "astrocyte": astrocyte or AsyncMock(),
        "centrifugo": centrifugo or AsyncMock(),
        "settings": settings or _make_settings(),
    }
    ctx = MagicMock()
    ctx.request_context.lifespan_context = lc
    return ctx


def _make_settings() -> MagicMock:
    s = MagicMock()
    s.default_members = [{"model_id": "gpt-4o", "name": "GPT-4o"}]
    s.default_chairman = {"model_id": "claude-opus-4-5", "name": "Chair"}
    s.astrocyte_gateway_url = "http://localhost:8080"
    s.astrocyte_token = "test-token"
    s.centrifugo_api_url = "http://localhost:8002"
    s.centrifugo_api_key = "test-key"
    s.stage1_timeout_seconds = 60
    s.stage2_timeout_seconds = 60
    s.stage3_timeout_seconds = 90
    s.max_precedents = 5
    s.litellm_api_base = ""
    s.litellm_api_key = ""
    s.synapse_llm_provider = "litellm"
    return s


def _make_session(
    session_id: uuid.UUID | None = None,
    status: str = CouncilStatus.pending,
    verdict: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.id = session_id or uuid.uuid4()
    s.status = status
    s.verdict = verdict
    s.question = "What should we do?"
    s.members = [{"model_id": "gpt-4o", "name": "GPT-4o"}]
    s.chairman = {"model_id": "claude-opus-4-5", "name": "Chair"}
    s.consensus_score = None
    s.confidence_label = None
    return s


def _make_thread(thread_id: uuid.UUID | None = None, council_id: uuid.UUID | None = None):
    t = MagicMock()
    t.id = thread_id or uuid.uuid4()
    t.council_id = council_id
    return t


def _make_event(
    event_id: int = 1,
    thread_id: uuid.UUID | None = None,
    event_type: str = ThreadEventType.user_message,
    actor_id: str = "mcp:agent",
    actor_name: str = "Agent",
    content: str = "test message",
) -> MagicMock:
    e = MagicMock()
    e.id = event_id
    e.thread_id = thread_id or uuid.uuid4()
    e.event_type = event_type
    e.actor_id = actor_id
    e.actor_name = actor_name
    e.content = content
    e.event_metadata = {}
    e.created_at = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return e


def _make_sessionmaker(session: AsyncMock) -> MagicMock:
    sm = MagicMock()
    sm.return_value.__aenter__ = AsyncMock(return_value=session)
    sm.return_value.__aexit__ = AsyncMock(return_value=None)
    return sm


# ---------------------------------------------------------------------------
# start_council
# ---------------------------------------------------------------------------


class TestStartCouncil:
    @pytest.mark.asyncio
    async def test_returns_session_and_thread_ids(self):
        session_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        mock_session = _make_session(session_id=session_id)
        mock_thread = _make_thread(thread_id=thread_id)
        mock_event = _make_event(thread_id=thread_id, event_type=ThreadEventType.council_started)

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with (
            patch("synapse.mcp.server.create_session", AsyncMock(return_value=mock_session)),
            patch("synapse.mcp.server.create_thread", AsyncMock(return_value=mock_thread)),
            patch("synapse.mcp.server.append_event", AsyncMock(return_value=mock_event)),
            patch("synapse.mcp.server.asyncio.create_task"),
            patch("synapse.mcp.server.CouncilOrchestrator"),
            patch("synapse.mcp.server.LLMClient"),
        ):
            result = await start_council(ctx, question="Should we migrate to microservices?")

        assert result["session_id"] == str(session_id)
        assert result["thread_id"] == str(thread_id)
        assert result["status"] == CouncilStatus.pending

    @pytest.mark.asyncio
    async def test_fires_background_task(self):
        mock_session = _make_session()
        mock_thread = _make_thread()
        mock_event = _make_event(event_type=ThreadEventType.council_started)

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)
        create_task_mock = MagicMock()

        with (
            patch("synapse.mcp.server.create_session", AsyncMock(return_value=mock_session)),
            patch("synapse.mcp.server.create_thread", AsyncMock(return_value=mock_thread)),
            patch("synapse.mcp.server.append_event", AsyncMock(return_value=mock_event)),
            patch("synapse.mcp.server.asyncio.create_task", create_task_mock),
            patch("synapse.mcp.server.CouncilOrchestrator"),
            patch("synapse.mcp.server.LLMClient"),
        ):
            await start_council(ctx, question="Should we scale horizontally?")

        create_task_mock.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_topic_tag(self):
        mock_session = _make_session()
        mock_thread = _make_thread()
        mock_event = _make_event(event_type=ThreadEventType.council_started)

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)
        create_session_mock = AsyncMock(return_value=mock_session)

        with (
            patch("synapse.mcp.server.create_session", create_session_mock),
            patch("synapse.mcp.server.create_thread", AsyncMock(return_value=mock_thread)),
            patch("synapse.mcp.server.append_event", AsyncMock(return_value=mock_event)),
            patch("synapse.mcp.server.asyncio.create_task"),
            patch("synapse.mcp.server.CouncilOrchestrator"),
            patch("synapse.mcp.server.LLMClient"),
        ):
            await start_council(ctx, question="Q?", topic_tag="infrastructure")

        kwargs = create_session_mock.call_args.kwargs
        assert kwargs["request"].topic_tag == "infrastructure"


# ---------------------------------------------------------------------------
# join
# ---------------------------------------------------------------------------


class TestJoin:
    @pytest.mark.asyncio
    async def test_returns_session_state(self):
        session_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        mock_session = _make_session(session_id=session_id, status=CouncilStatus.stage_1)
        mock_thread = _make_thread(thread_id=thread_id)
        events = [_make_event(i, thread_id) for i in range(1, 4)]

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with (
            patch("synapse.mcp.server.get_session", AsyncMock(return_value=mock_session)),
            patch("synapse.mcp.server.get_thread_by_council", AsyncMock(return_value=mock_thread)),
            patch("synapse.mcp.server.get_history", AsyncMock(return_value=events)),
        ):
            result = await join(ctx, session_id=str(session_id))

        assert result["session_id"] == str(session_id)
        assert result["status"] == CouncilStatus.stage_1
        assert result["thread_id"] == str(thread_id)
        assert len(result["recent_events"]) == 3

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_session(self):
        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with patch("synapse.mcp.server.get_session", AsyncMock(return_value=None)):
            result = await join(ctx, session_id=str(uuid.uuid4()))

        assert "error" in result

    @pytest.mark.asyncio
    async def test_events_are_chronological(self):
        """get_history returns DESC; join should reverse to chronological."""
        session_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        mock_session = _make_session(session_id=session_id)
        mock_thread = _make_thread(thread_id=thread_id)
        # DESC order (as returned by get_history)
        events_desc = [_make_event(i, thread_id) for i in range(10, 7, -1)]

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with (
            patch("synapse.mcp.server.get_session", AsyncMock(return_value=mock_session)),
            patch("synapse.mcp.server.get_thread_by_council", AsyncMock(return_value=mock_thread)),
            patch("synapse.mcp.server.get_history", AsyncMock(return_value=events_desc)),
        ):
            result = await join(ctx, session_id=str(session_id))

        ids = [e["id"] for e in result["recent_events"]]
        assert ids == sorted(ids)  # ascending = chronological


# ---------------------------------------------------------------------------
# contribute
# ---------------------------------------------------------------------------


class TestContribute:
    @pytest.mark.asyncio
    async def test_appends_event_and_returns_payload(self):
        session_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        mock_session = _make_session(session_id=session_id)
        mock_thread = _make_thread(thread_id=thread_id)
        mock_event = _make_event(thread_id=thread_id, content="Important context")

        centrifugo = AsyncMock()
        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm, centrifugo=centrifugo)

        with (
            patch("synapse.mcp.server.get_session", AsyncMock(return_value=mock_session)),
            patch("synapse.mcp.server.get_thread_by_council", AsyncMock(return_value=mock_thread)),
            patch("synapse.mcp.server.append_event", AsyncMock(return_value=mock_event)),
        ):
            result = await contribute(ctx, session_id=str(session_id), content="Important context")

        assert result["content"] == "Important context"
        assert result["event_type"] == ThreadEventType.user_message
        centrifugo.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_centrifugo_failure_does_not_raise(self):
        """Best-effort publish — Centrifugo failure must not propagate."""
        session_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        mock_session = _make_session(session_id=session_id)
        mock_thread = _make_thread(thread_id=thread_id)
        mock_event = _make_event(thread_id=thread_id)

        centrifugo = AsyncMock()
        centrifugo.publish.side_effect = Exception("Centrifugo down")
        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm, centrifugo=centrifugo)

        with (
            patch("synapse.mcp.server.get_session", AsyncMock(return_value=mock_session)),
            patch("synapse.mcp.server.get_thread_by_council", AsyncMock(return_value=mock_thread)),
            patch("synapse.mcp.server.append_event", AsyncMock(return_value=mock_event)),
        ):
            result = await contribute(ctx, session_id=str(session_id), content="msg")

        assert "event_type" in result  # DB write succeeded, no exception raised

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_session(self):
        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with patch("synapse.mcp.server.get_session", AsyncMock(return_value=None)):
            result = await contribute(ctx, session_id=str(uuid.uuid4()), content="msg")

        assert "error" in result


# ---------------------------------------------------------------------------
# recall_precedent
# ---------------------------------------------------------------------------


class TestRecallPrecedent:
    @pytest.mark.asyncio
    async def test_returns_hits(self):
        hit = SimpleNamespace(
            memory_id="mem-1",
            content="Past decision about monorepos.",
            score=0.92,
            bank_id="precedents",
            metadata={"council_id": "old-1"},
        )
        astrocyte = AsyncMock()
        astrocyte.recall = AsyncMock(return_value=[hit])
        ctx = _make_ctx(astrocyte=astrocyte)

        result = await recall_precedent(ctx, query="monorepo governance")

        assert len(result) == 1
        assert result[0]["memory_id"] == "mem-1"
        assert result[0]["score"] == 0.92

    @pytest.mark.asyncio
    async def test_limit_is_clamped_to_20(self):
        astrocyte = AsyncMock()
        astrocyte.recall = AsyncMock(return_value=[])
        ctx = _make_ctx(astrocyte=astrocyte)

        await recall_precedent(ctx, query="anything", limit=999)

        call_kwargs = astrocyte.recall.call_args.kwargs
        assert call_kwargs["max_results"] == 20

    @pytest.mark.asyncio
    async def test_empty_result_on_no_matches(self):
        astrocyte = AsyncMock()
        astrocyte.recall = AsyncMock(return_value=[])
        ctx = _make_ctx(astrocyte=astrocyte)

        result = await recall_precedent(ctx, query="something with no matches")

        assert result == []


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    @pytest.mark.asyncio
    async def test_closes_running_session(self):
        session_id = uuid.uuid4()
        mock_session = _make_session(session_id=session_id, status=CouncilStatus.stage_1)
        closed_session = _make_session(
            session_id=session_id, status=CouncilStatus.closed, verdict="Closed by agent."
        )

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with (
            patch("synapse.mcp.server.get_session", AsyncMock(return_value=mock_session)),
            patch("synapse.mcp.server.close_session", AsyncMock(return_value=closed_session)),
        ):
            result = await close(ctx, session_id=str(session_id))

        assert result["status"] == CouncilStatus.closed
        assert result["already_closed"] is False

    @pytest.mark.asyncio
    async def test_already_closed_returns_verdict(self):
        session_id = uuid.uuid4()
        mock_session = _make_session(
            session_id=session_id,
            status=CouncilStatus.closed,
            verdict="Use microservices.",
        )

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with patch("synapse.mcp.server.get_session", AsyncMock(return_value=mock_session)):
            result = await close(ctx, session_id=str(session_id))

        assert result["already_closed"] is True
        assert result["verdict"] == "Use microservices."

    @pytest.mark.asyncio
    async def test_already_failed_returns_flag(self):
        session_id = uuid.uuid4()
        mock_session = _make_session(session_id=session_id, status=CouncilStatus.failed)

        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with patch("synapse.mcp.server.get_session", AsyncMock(return_value=mock_session)):
            result = await close(ctx, session_id=str(session_id))

        assert result.get("already_failed") is True

    @pytest.mark.asyncio
    async def test_returns_error_for_missing_session(self):
        db = AsyncMock()
        sm = _make_sessionmaker(db)
        ctx = _make_ctx(sessionmaker=sm)

        with patch("synapse.mcp.server.get_session", AsyncMock(return_value=None)):
            result = await close(ctx, session_id=str(uuid.uuid4()))

        assert "error" in result
