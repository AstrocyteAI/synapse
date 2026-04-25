"""Tests for B3 async council flow — contribution accumulation and quorum-triggered resume."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synapse.council.models import CouncilMember, CouncilResult
from synapse.council.orchestrator import CouncilOrchestrator
from synapse.council.session import quorum_met
from synapse.db.models import CouncilSession, CouncilStatus
from synapse.memory.context import AstrocyteContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NO_CONFLICT = patch(
    "synapse.council.orchestrator.check_conflict",
    new=AsyncMock(return_value=MagicMock(detected=False)),
)
_NO_THREAD = patch(
    "synapse.council.orchestrator.get_thread_by_council",
    new=AsyncMock(return_value=None),
)


def _make_session(
    *,
    council_type: str = "async",
    members: list[dict] | None = None,
    quorum: int | None = None,
    contributions: list[dict] | None = None,
    contribution_deadline: datetime | None = None,
) -> CouncilSession:
    if members is None:
        members = [
            {"model_id": "openai/gpt-4o", "name": "GPT", "member_type": "llm"},
            {
                "model_id": "anthropic/claude-3-5-sonnet-20241022",
                "name": "Claude",
                "member_type": "human",
            },
        ]
    session = MagicMock(spec=CouncilSession)
    session.id = uuid.uuid4()
    session.question = "What should we build?"
    session.status = CouncilStatus.waiting_contributions
    session.council_type = council_type
    session.members = members
    session.chairman = {
        "model_id": "anthropic/claude-opus-4-5",
        "name": "Chair",
        "member_type": "llm",
    }
    session.contributions = contributions or []
    session.quorum = quorum
    session.contribution_deadline = contribution_deadline
    session.topic_tag = None
    session.created_by = "user-1"
    session.tenant_id = "tenant-test"
    return session


@pytest.fixture
def orchestrator(mock_astrocyte, mock_centrifugo, mock_llm):
    settings = MagicMock()
    settings.stage1_timeout_seconds = 10
    settings.stage2_timeout_seconds = 10
    settings.stage3_timeout_seconds = 10
    settings.max_precedents = 3
    settings.deliberation_enabled = False
    settings.max_deliberation_rounds = 1
    settings.convergence_threshold = 0.72
    settings.critique_timeout_seconds = 10
    settings.revise_timeout_seconds = 10
    return CouncilOrchestrator(
        astrocyte=mock_astrocyte,
        centrifugo=mock_centrifugo,
        llm=mock_llm,
        settings=settings,
    )


@pytest.fixture
def context():
    return AstrocyteContext(principal="user-1", tenant_id="tenant-test")


# ---------------------------------------------------------------------------
# quorum_met helper
# ---------------------------------------------------------------------------


def test_quorum_met_explicit():
    session = _make_session(quorum=2, contributions=[{"c": 1}, {"c": 2}])
    assert quorum_met(session) is True


def test_quorum_not_met_explicit():
    session = _make_session(quorum=2, contributions=[{"c": 1}])
    assert quorum_met(session) is False


def test_quorum_met_default_all_members():
    """No explicit quorum — all members must contribute."""
    members = [
        {"model_id": "m1", "name": "A", "member_type": "llm"},
        {"model_id": "m2", "name": "B", "member_type": "human"},
    ]
    session = _make_session(
        members=members,
        contributions=[{"c": 1}, {"c": 2}],
    )
    assert quorum_met(session) is True


def test_quorum_not_met_default_all_members():
    members = [
        {"model_id": "m1", "name": "A", "member_type": "llm"},
        {"model_id": "m2", "name": "B", "member_type": "human"},
    ]
    session = _make_session(members=members, contributions=[{"c": 1}])
    assert quorum_met(session) is False


# ---------------------------------------------------------------------------
# Orchestrator run() — async council parks in waiting_contributions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_council_parks_when_human_members_pending(orchestrator, context):
    """run() returns None for async councils with human members not yet contributed."""
    members = [
        CouncilMember(model_id="openai/gpt-4o", name="GPT", member_type="llm"),
        CouncilMember(
            model_id="anthropic/claude-3-5-sonnet-20241022", name="Claude", member_type="human"
        ),
    ]
    chairman = CouncilMember(model_id="anthropic/claude-opus-4-5", name="Chair")

    session_id = uuid.uuid4()

    # Session: initially has no contributions
    session_obj = MagicMock(spec=CouncilSession)
    session_obj.id = session_id
    session_obj.status = CouncilStatus.pending
    session_obj.contributions = []
    session_obj.quorum = None
    session_obj.members = [m.model_dump() for m in members]
    session_obj.contribution_deadline = None

    db = AsyncMock()
    db.get = AsyncMock(return_value=session_obj)
    db.commit = AsyncMock()

    with (
        patch("synapse.council.orchestrator.asyncio.create_task"),
        patch(
            "synapse.council.orchestrator.run_gather",
            new=AsyncMock(
                return_value=[
                    MagicMock(
                        member_id="openai/gpt-4o",
                        member_name="GPT",
                        content="LLM response",
                        error=None,
                    ),
                ]
            ),
        ),
        _NO_THREAD,
    ):
        result = await orchestrator.run(
            session_id=session_id,
            question="Q?",
            members=members,
            chairman=chairman,
            context=context,
            db=db,
            council_type="async",
        )

    # Should return None — parked waiting for human contribution
    assert result is None


@pytest.mark.asyncio
async def test_async_council_completes_immediately_when_all_llm(orchestrator, context):
    """All-LLM async council: quorum met immediately → returns CouncilResult."""
    members = [
        CouncilMember(model_id="openai/gpt-4o", name="GPT", member_type="llm"),
        CouncilMember(
            model_id="anthropic/claude-3-5-sonnet-20241022", name="Claude", member_type="llm"
        ),
    ]
    chairman = CouncilMember(model_id="anthropic/claude-opus-4-5", name="Chair")
    session_id = uuid.uuid4()

    # After contributions are saved, session has 2 contributions (both LLM)
    session_after = MagicMock(spec=CouncilSession)
    session_after.id = session_id
    session_after.status = CouncilStatus.stage_1
    session_after.contributions = [
        {
            "member_id": "openai/gpt-4o",
            "member_name": "GPT",
            "content": "resp A",
            "member_type": "llm",
        },
        {
            "member_id": "anthropic/claude-3-5-sonnet-20241022",
            "member_name": "Claude",
            "content": "resp B",
            "member_type": "llm",
        },
    ]
    session_after.quorum = None
    session_after.members = [m.model_dump() for m in members]
    session_after.contribution_deadline = None

    db = AsyncMock()
    db.get = AsyncMock(return_value=session_after)
    db.commit = AsyncMock()

    from synapse.council.models import StageOneResponse

    mock_responses = [
        StageOneResponse(member_id="openai/gpt-4o", member_name="GPT", content="resp A"),
        StageOneResponse(
            member_id="anthropic/claude-3-5-sonnet-20241022",
            member_name="Claude",
            content="resp B",
        ),
    ]

    with (
        patch("synapse.council.orchestrator.asyncio.create_task"),
        patch(
            "synapse.council.orchestrator.run_gather", new=AsyncMock(return_value=mock_responses)
        ),
        _NO_THREAD,
        _NO_CONFLICT,
    ):
        result = await orchestrator.run(
            session_id=session_id,
            question="Q?",
            members=members,
            chairman=chairman,
            context=context,
            db=db,
            council_type="async",
        )

    assert isinstance(result, CouncilResult)
    assert result.verdict is not None


# ---------------------------------------------------------------------------
# orchestrator.resume() — completes Stage 2+3 from contributions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_runs_stage2_3_from_contributions(orchestrator):
    """resume() loads contributions and produces a CouncilResult."""
    session_id = uuid.uuid4()
    session_obj = _make_session(
        contributions=[
            {"member_id": "openai/gpt-4o", "member_name": "GPT", "content": "My take."},
            {"member_id": "user:alice", "member_name": "Alice", "content": "Mine too."},
        ]
    )
    session_obj.id = session_id

    db = AsyncMock()
    db.get = AsyncMock(return_value=session_obj)
    db.commit = AsyncMock()

    with (
        patch("synapse.council.orchestrator.asyncio.create_task"),
        _NO_THREAD,
        _NO_CONFLICT,
    ):
        result = await orchestrator.resume(session_id, db)

    assert isinstance(result, CouncilResult)
    assert result.verdict is not None
    assert result.consensus_score == 1.0  # 2-response ranking falls back to solo path


@pytest.mark.asyncio
async def test_resume_returns_none_for_non_waiting_session(orchestrator):
    """resume() is a no-op if the session is not in waiting_contributions."""
    session_id = uuid.uuid4()
    session_obj = MagicMock(spec=CouncilSession)
    session_obj.id = session_id
    session_obj.status = CouncilStatus.closed  # already done

    db = AsyncMock()
    db.get = AsyncMock(return_value=session_obj)

    result = await orchestrator.resume(session_id, db)
    assert result is None


# ---------------------------------------------------------------------------
# B7 — ScheduledCouncilRunner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_fires_after_delay():
    """schedule() task fires _fire_council after the configured delay."""
    from synapse.scheduling.runner import ScheduledCouncilRunner

    fired: list[uuid.UUID] = []

    async def fake_fire(app, sid):
        fired.append(sid)

    runner = ScheduledCouncilRunner()
    session_id = uuid.uuid4()
    run_at = datetime.now(UTC)  # immediate

    app = MagicMock()

    with patch("synapse.scheduling.runner._fire_council", new=AsyncMock(side_effect=fake_fire)):
        runner.schedule(app, session_id, run_at)
        # Wait briefly for the task to complete
        import asyncio

        await asyncio.sleep(0.05)

    assert session_id in fired


@pytest.mark.asyncio
async def test_scheduler_cancel_stops_pending_task():
    import asyncio

    from synapse.scheduling.runner import ScheduledCouncilRunner

    runner = ScheduledCouncilRunner()
    session_id = uuid.uuid4()
    run_at = datetime.now(UTC) + timedelta(hours=1)  # far future

    app = MagicMock()
    runner.schedule(app, session_id, run_at)
    assert str(session_id) in runner._tasks

    runner.cancel(session_id)
    await asyncio.sleep(0.01)
    task = runner._tasks.get(str(session_id))
    assert task is None or task.cancelled()


@pytest.mark.asyncio
async def test_scheduler_resume_fires_after_delay():
    """schedule_resume() task fires _fire_resume after deadline."""
    from synapse.scheduling.runner import ScheduledCouncilRunner

    fired: list[uuid.UUID] = []

    async def fake_resume(app, sid):
        fired.append(sid)

    runner = ScheduledCouncilRunner()
    session_id = uuid.uuid4()
    deadline = datetime.now(UTC)  # immediate

    app = MagicMock()

    with patch("synapse.scheduling.runner._fire_resume", new=AsyncMock(side_effect=fake_resume)):
        runner.schedule_resume(app, session_id, deadline)
        import asyncio

        await asyncio.sleep(0.05)

    assert session_id in fired
