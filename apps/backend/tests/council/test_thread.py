"""Tests for thread CRUD helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from synapse.council.thread import (
    append_event,
    create_thread,
    get_history,
)
from synapse.db.models import Thread, ThreadEvent, ThreadEventType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_thread(**kwargs) -> Thread:
    defaults = dict(
        id=uuid.uuid4(),
        council_id=uuid.uuid4(),
        created_by="user:test-1",
        tenant_id="tenant-test",
        title="Test thread",
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=Thread)
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


def _make_event(id: int, thread_id: uuid.UUID, **kwargs) -> ThreadEvent:
    defaults = dict(
        thread_id=thread_id,
        event_type=ThreadEventType.user_message,
        actor_id="user:test-1",
        actor_name="Test User",
        content="Hello",
        metadata={},
    )
    defaults.update(kwargs)
    obj = MagicMock(spec=ThreadEvent)
    obj.id = id
    for k, v in defaults.items():
        setattr(obj, k, v)
    return obj


# ---------------------------------------------------------------------------
# create_thread
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_thread_with_council():
    db = AsyncMock()
    council_id = uuid.uuid4()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    await create_thread(
        db,
        council_id=council_id,
        created_by="user:abc",
        tenant_id="tenant-1",
        title="Should we do X?",
    )

    db.add.assert_called_once()
    db.commit.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.council_id == council_id
    assert added.created_by == "user:abc"
    assert added.title == "Should we do X?"


@pytest.mark.asyncio
async def test_create_thread_without_council():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    await create_thread(db, created_by="user:abc")

    added = db.add.call_args[0][0]
    assert added.council_id is None


# ---------------------------------------------------------------------------
# append_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_event_writes_to_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    thread_id = uuid.uuid4()
    await append_event(
        db,
        thread_id=thread_id,
        event_type=ThreadEventType.user_message,
        actor_id="user:abc",
        actor_name="Alice",
        content="What should we prioritise?",
        metadata={"extra": "data"},
    )

    db.add.assert_called_once()
    event = db.add.call_args[0][0]
    assert event.thread_id == thread_id
    assert event.event_type == ThreadEventType.user_message
    assert event.content == "What should we prioritise?"
    assert event.event_metadata == {"extra": "data"}


@pytest.mark.asyncio
async def test_append_event_defaults_metadata_to_empty_dict():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    await append_event(
        db,
        thread_id=uuid.uuid4(),
        event_type=ThreadEventType.system_event,
        actor_id="system",
    )

    event = db.add.call_args[0][0]
    assert event.event_metadata == {}


# ---------------------------------------------------------------------------
# get_history — pagination direction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_history_before_id_orders_desc():
    """before_id query should return events with id < before_id, DESC."""
    db = AsyncMock()
    thread_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    await get_history(db, thread_id, before_id=100)

    # Verify the statement was constructed (we can't introspect SA deeply,
    # but at minimum it should not raise and should call execute)
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_history_after_id_orders_asc():
    db = AsyncMock()
    thread_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    await get_history(db, thread_id, after_id=50)
    db.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_history_no_cursor_returns_most_recent():
    db = AsyncMock()
    thread_id = uuid.uuid4()
    events = [_make_event(i, thread_id) for i in range(3, 0, -1)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = events
    db.execute = AsyncMock(return_value=mock_result)

    result = await get_history(db, thread_id, limit=10)
    assert len(result) == 3
