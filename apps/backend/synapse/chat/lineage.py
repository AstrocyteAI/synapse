"""Chat-session lineage operations — fork, edit, regenerate.

Mirrors Cerebro's ``Synapse.Chat.Lineage`` Elixir module. The three
operations share the same shape: validate the cursor event, persist a
marker event in the thread (``message_edited``, ``message_regenerated``,
``conversation_forked``), and then the caller resumes the agent loop
with the new context.

Wire contract: ``priv/contracts/chat-api-v1.openapi.json`` §§ fork,
edit, regenerate.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.chat.api_models import AgentConfig, ChatSessionCreate
from synapse.chat.sessions import create_session
from synapse.council.thread import append_event
from synapse.db.models import ChatSession, ThreadEvent


class LineageError(Exception):
    """Base class for lineage-validation failures."""

    code: Literal[
        "event_not_in_thread",
        "wrong_event_type",
        "no_preceding_user_message",
    ]

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


async def fork_session(
    db: AsyncSession,
    *,
    parent: ChatSession,
    from_event_id: int,
    principal: str,
    tenant_id: str | None,
    title: str | None = None,
) -> ChatSession:
    """Fork ``parent`` at ``from_event_id``.

    Creates a new session whose thread holds a copy of the parent thread's
    events up to and including ``from_event_id``. Persists a
    ``conversation_forked`` marker event on the **parent** thread pointing
    at the new session.
    """
    await _validate_event_in_thread(db, parent.thread_id, from_event_id)

    request = ChatSessionCreate(
        title=title or f"Fork of {parent.title}",
        council_id=parent.council_id,
        agent_config=AgentConfig.model_validate(parent.agent_config or {}),
    )
    child = await create_session(
        db,
        request=request,
        created_by=principal,
        tenant_id=tenant_id,
    )

    # Link lineage. create_session doesn't carry these fields through, so
    # we set them in a follow-up update — they live on ChatSession directly,
    # not in ChatSessionCreate.
    child.parent_session_id = parent.id
    child.parent_fork_event_id = from_event_id
    await db.commit()
    await db.refresh(child)

    # Copy parent thread's events up to the cursor into the child thread.
    await _copy_events_to(db, parent.thread_id, child.thread_id, from_event_id)

    # Persist the fork marker on the PARENT thread so its log shows where
    # the branch happened, with a pointer to the child session.
    await append_event(
        db,
        thread_id=parent.thread_id,
        event_type="conversation_forked",
        actor_id=principal,
        actor_name=principal,
        metadata={
            "forked_at_event_id": from_event_id,
            "new_session_id": str(child.id),
            "new_thread_id": str(child.thread_id),
        },
    )

    return child


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


async def edit_message(
    db: AsyncSession,
    *,
    session: ChatSession,
    message_id: int,
    new_content: str,
    principal: str,
) -> str:
    """Persist a ``message_edited`` marker. Returns the new content the
    caller should hand to the agent loop.

    The original ``user_message`` row stays in the log — the view layer
    surfaces the latest version, but the audit trail is preserved.

    Raises:
        LineageError("event_not_in_thread"): ``message_id`` is not a
            thread_event belonging to this session's thread.
        LineageError("wrong_event_type"): only ``user_message`` events
            can be edited.
    """
    original = await _fetch_event(db, session.thread_id, message_id, "user_message")

    await append_event(
        db,
        thread_id=session.thread_id,
        event_type="message_edited",
        actor_id=principal,
        actor_name=principal,
        content=new_content,
        metadata={
            "original_event_id": original.id,
            "original_content": original.content,
        },
    )

    return new_content


# ---------------------------------------------------------------------------
# Regenerate
# ---------------------------------------------------------------------------


async def regenerate_message(
    db: AsyncSession,
    *,
    session: ChatSession,
    message_id: int,
    principal: str,
) -> str:
    """Persist a ``message_regenerated`` marker. Returns the user message
    that triggered the original assistant response, ready to be re-run
    through the agent loop.

    The original ``reflection`` event stays in the log — the UI can
    surface multiple regenerations as a carousel (ChatGPT-style swipe).

    Raises:
        LineageError("event_not_in_thread"): event id does not belong
            to this session's thread.
        LineageError("wrong_event_type"): only ``reflection`` events
            can be regenerated.
        LineageError("no_preceding_user_message"): the reflection has no
            ``user_message`` before it in the thread, so there's nothing
            to re-feed the agent.
    """
    reflection = await _fetch_event(db, session.thread_id, message_id, "reflection")
    user_msg = await _fetch_preceding_user_message(db, session.thread_id, reflection.id)

    await append_event(
        db,
        thread_id=session.thread_id,
        event_type="message_regenerated",
        actor_id=principal,
        actor_name=principal,
        content=user_msg.content,
        metadata={
            "original_event_id": reflection.id,
            "source_user_event_id": user_msg.id,
        },
    )

    return user_msg.content or ""


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _validate_event_in_thread(db: AsyncSession, thread_id: uuid.UUID, event_id: int) -> None:
    stmt = select(ThreadEvent.id).where(
        ThreadEvent.thread_id == thread_id, ThreadEvent.id == event_id
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise LineageError("event_not_in_thread", "from_event_id not in parent thread")


async def _fetch_event(
    db: AsyncSession,
    thread_id: uuid.UUID,
    event_id: int,
    expected_type: str,
) -> ThreadEvent:
    stmt = select(ThreadEvent).where(ThreadEvent.id == event_id, ThreadEvent.thread_id == thread_id)
    event = (await db.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise LineageError("event_not_in_thread", "event not found in thread")
    if event.event_type != expected_type:
        raise LineageError(
            "wrong_event_type",
            f"expected {expected_type}, got {event.event_type}",
        )
    return event


async def _fetch_preceding_user_message(
    db: AsyncSession, thread_id: uuid.UUID, reflection_event_id: int
) -> ThreadEvent:
    stmt = (
        select(ThreadEvent)
        .where(
            ThreadEvent.thread_id == thread_id,
            ThreadEvent.id < reflection_event_id,
            ThreadEvent.event_type == "user_message",
        )
        .order_by(ThreadEvent.id.desc())
        .limit(1)
    )
    event = (await db.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise LineageError(
            "no_preceding_user_message",
            "no user_message precedes the target reflection",
        )
    return event


async def _copy_events_to(
    db: AsyncSession,
    src_thread_id: uuid.UUID,
    dst_thread_id: uuid.UUID,
    up_to_event_id: int,
) -> None:
    """Copy events from the parent thread to the child via a single
    INSERT…SELECT so we don't pull thousands of rows into Python memory
    for long threads. ``created_at`` is preserved so the fork's history
    matches the parent's timeline.
    """
    from sqlalchemy import text

    # The Python attribute is `event_metadata` but the actual DB column is
    # `metadata` — `metadata` is reserved by SQLAlchemy's Declarative API
    # so the model remaps it. The raw SQL here uses the actual column name.
    await db.execute(
        text(
            """
            INSERT INTO thread_events
              (thread_id, event_type, actor_id, actor_name, content, metadata, created_at)
            SELECT :dst, event_type, actor_id, actor_name, content, metadata, created_at
            FROM thread_events
            WHERE thread_id = :src AND id <= :cursor
            ORDER BY id ASC
            """
        ),
        {
            "dst": dst_thread_id,
            "src": src_thread_id,
            "cursor": up_to_event_id,
        },
    )
    await db.commit()
