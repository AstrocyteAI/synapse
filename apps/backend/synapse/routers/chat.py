"""Chat sessions router — CRUD endpoints + SSE messages endpoint.

Implements ``priv/contracts/chat-api-v1.openapi.json`` § /v1/chat/sessions/*
(the cross-backend contract; Cerebro EE Elixir mirrors).

Covers:

  * Session lifecycle: ``POST/GET/PATCH/DELETE /v1/chat/sessions{,/id}``
  * Send message + SSE agent loop: ``POST /v1/chat/sessions/{id}/messages``
  * Phase 1B conversation editing:

      - ``POST /v1/chat/sessions/{id}/fork``
      - ``POST /v1/chat/sessions/{id}/messages/{message_id}/edit``
      - ``POST /v1/chat/sessions/{id}/messages/{message_id}/regenerate``
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.chat.agent import stream_chat_response
from synapse.chat.api_models import (
    ChatSession as ChatSessionResponse,
)
from synapse.chat.api_models import (
    ChatSessionCreate,
    ChatSessionList,
    ChatSessionUpdate,
    ForkRequest,
    MessageEditRequest,
    MessageRegenerateRequest,
    MessageSendRequest,
)
from synapse.chat.lineage import (
    LineageError,
    fork_session,
)
from synapse.chat.lineage import (
    edit_message as lineage_edit,
)
from synapse.chat.lineage import (
    regenerate_message as lineage_regenerate,
)
from synapse.chat.sessions import (
    archive_session,
    create_session,
    get_session,
    list_sessions,
    update_session,
)
from synapse.db.session import get_session as get_db_session

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post(
    "/chat/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatSessionResponse,
    summary="Create a new chat session",
)
async def create_chat_session(
    body: ChatSessionCreate,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ChatSessionResponse:
    session = await create_session(
        db,
        request=body,
        created_by=user.principal,
        tenant_id=user.tenant_id,
    )
    return ChatSessionResponse.model_validate(session)


@router.get(
    "/chat/sessions",
    response_model=ChatSessionList,
    summary="List chat sessions (cursor-paginated, newest first)",
)
async def list_chat_sessions(
    status_filter: Literal["active", "archived", "all"] = Query(
        default="active",
        alias="status",
        description="Filter by session status; default 'active'.",
    ),
    before: datetime | None = Query(
        default=None,
        description="Cursor: return sessions created before this timestamp.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ChatSessionList:
    rows, next_cursor = await list_sessions(
        db,
        tenant_id=user.tenant_id,
        created_by=None if "admin" in (user.roles or []) else user.principal,
        status=status_filter,
        before_created_at=before,
        limit=limit,
    )

    return ChatSessionList(
        data=[ChatSessionResponse.model_validate(row) for row in rows],
        next_before_id=next_cursor,
    )


@router.get(
    "/chat/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Get a chat session by id",
)
async def get_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ChatSessionResponse:
    session = await _load_session(db, session_id, user)
    return ChatSessionResponse.model_validate(session)


@router.patch(
    "/chat/sessions/{session_id}",
    response_model=ChatSessionResponse,
    summary="Update chat session metadata (title, status, agent_config)",
)
async def patch_chat_session(
    session_id: uuid.UUID,
    body: ChatSessionUpdate,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ChatSessionResponse:
    session = await _load_session(db, session_id, user)
    updated = await update_session(db, session, request=body)
    return ChatSessionResponse.model_validate(updated)


@router.delete(
    "/chat/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a chat session (soft-delete; thread + events preserved)",
)
async def delete_chat_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> None:
    session = await _load_session(db, session_id, user)
    await archive_session(db, session)


# ---------------------------------------------------------------------------
# POST /v1/chat/sessions/{id}/messages — SSE-streaming agent loop
# ---------------------------------------------------------------------------


@router.post(
    "/chat/sessions/{session_id}/messages",
    summary="Send a message to a chat session; SSE stream of agent response",
    response_class=StreamingResponse,
)
async def send_chat_message(
    session_id: uuid.UUID,
    body: MessageSendRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    """Send a user message; stream the agent's response as SSE.

    Event taxonomy follows ``priv/contracts/chat-api-v1.openapi.json``
    § ChatStreamEvent: ``session_started`` → (``token`` | ``tool_call`` |
    ``tool_result``)* → ``message_complete`` (or ``error``).

    The endpoint persists the user message, runs the Pydantic AI agent
    with the session's configured tools, and appends tool_call /
    tool_result / reflection events to the thread as the loop proceeds.
    All events are durable in ``thread_events`` — clients can replay via
    the thread events endpoint after reconnect.
    """
    session = await _load_session(db, session_id, user)
    if session.status != "active":
        raise HTTPException(status_code=422, detail="Chat session is not active")

    astrocyte = request.app.state.astrocyte
    actor_name = (
        user.raw_claims.get("name") or user.raw_claims.get("preferred_username") or user.sub
    )

    generator = stream_chat_response(
        db=db,
        astrocyte=astrocyte,
        session=session,
        user_message=body.content,
        principal=user.principal,
        actor_name=actor_name,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Conversation editing (Phase 1B): fork, edit, regenerate.
# Mirrors Cerebro's `SynapseWeb.ChatSessionController` actions; both backends
# serve the same OpenAPI surface so clients can target either.
# ---------------------------------------------------------------------------


@router.post(
    "/chat/sessions/{session_id}/fork",
    status_code=status.HTTP_201_CREATED,
    response_model=ChatSessionResponse,
    summary="Fork a conversation at a specific cursor",
)
async def fork_chat_session(
    session_id: uuid.UUID,
    body: ForkRequest,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> ChatSessionResponse:
    parent = await _load_session(db, session_id, user)
    try:
        child = await fork_session(
            db,
            parent=parent,
            from_event_id=body.from_event_id,
            principal=user.principal,
            tenant_id=user.tenant_id,
            title=body.title,
        )
    except LineageError as e:
        # `event_not_in_thread` is the only LineageError fork can raise
        # today, but switch on `.code` for future-proofing.
        if e.code == "event_not_in_thread":
            raise HTTPException(status_code=422, detail=str(e)) from e
        raise HTTPException(status_code=422, detail=str(e)) from e
    return ChatSessionResponse.model_validate(child)


@router.post(
    "/chat/sessions/{session_id}/messages/{message_id}/edit",
    summary="Edit a user message; SSE stream of new agent response",
    response_class=StreamingResponse,
)
async def edit_chat_message(
    session_id: uuid.UUID,
    message_id: int,
    body: MessageEditRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    session = await _load_session(db, session_id, user)
    if session.status != "active":
        raise HTTPException(status_code=422, detail="Chat session is not active")

    try:
        new_content = await lineage_edit(
            db,
            session=session,
            message_id=message_id,
            new_content=body.content,
            principal=user.principal,
        )
    except LineageError as e:
        if e.code == "event_not_in_thread":
            raise HTTPException(status_code=404, detail=str(e)) from e
        # wrong_event_type — only user_message can be edited
        raise HTTPException(status_code=422, detail=str(e)) from e

    return _stream_agent_turn(
        request=request,
        db=db,
        session=session,
        user_message=new_content,
        principal=user.principal,
        actor_name=_actor_name(user),
    )


@router.post(
    "/chat/sessions/{session_id}/messages/{message_id}/regenerate",
    summary="Regenerate an agent response; SSE stream of new turn",
    response_class=StreamingResponse,
)
async def regenerate_chat_message(
    session_id: uuid.UUID,
    message_id: int,
    request: Request,
    body: MessageRegenerateRequest | None = None,
    db: AsyncSession = Depends(get_db_session),
    user: AuthenticatedUser = Depends(get_current_user),
) -> StreamingResponse:
    session = await _load_session(db, session_id, user)
    if session.status != "active":
        raise HTTPException(status_code=422, detail="Chat session is not active")

    try:
        user_content = await lineage_regenerate(
            db,
            session=session,
            message_id=message_id,
            principal=user.principal,
        )
    except LineageError as e:
        if e.code == "event_not_in_thread":
            raise HTTPException(status_code=404, detail=str(e)) from e
        # wrong_event_type or no_preceding_user_message — both client-side
        # contract violations, surfaced as 422.
        raise HTTPException(status_code=422, detail=str(e)) from e

    # agent_config_override is applied for this turn only — the session row
    # is NOT mutated. Matches the Cerebro behaviour: regeneration is a
    # one-shot experiment with a different model, not a config change.
    override = body.agent_config_override if body else None
    return _stream_agent_turn(
        request=request,
        db=db,
        session=session,
        user_message=user_content,
        principal=user.principal,
        actor_name=_actor_name(user),
        agent_config_override=override,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _actor_name(user: AuthenticatedUser) -> str:
    return user.raw_claims.get("name") or user.raw_claims.get("preferred_username") or user.sub


def _stream_agent_turn(
    *,
    request: Request,
    db: AsyncSession,
    session,  # ChatSession (DB model)
    user_message: str,
    principal: str,
    actor_name: str,
    agent_config_override=None,
) -> StreamingResponse:
    """Shared SSE writer for send / edit / regenerate.

    The caller has already persisted the user-side marker event; this
    function just runs the agent loop with the prepared content. If an
    `agent_config_override` is given, it merges into the session's stored
    config for this turn only — the DB row is not mutated.
    """
    astrocyte = request.app.state.astrocyte

    # Apply the override in-memory only. `agent_config` is a Pydantic
    # model on the request side and a plain dict on the model side.
    if agent_config_override is not None:
        merged = {
            **(session.agent_config or {}),
            **agent_config_override.model_dump(exclude_none=True),
        }
        session_for_turn = session
        session_for_turn.agent_config = merged  # in-memory only; not persisted
    else:
        session_for_turn = session

    generator = stream_chat_response(
        db=db,
        astrocyte=astrocyte,
        session=session_for_turn,
        user_message=user_message,
        principal=principal,
        actor_name=actor_name,
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _load_session(db: AsyncSession, session_id: uuid.UUID, user: AuthenticatedUser):
    """Tenant-scoped session fetch — admins bypass the filter.

    Mirrors ``synapse.routers.threads._load_thread`` posture: cross-tenant
    rows return 404, not 403. Service-layer fetch already enforces scoping;
    this helper centralises the admin-bypass path so all chat endpoints
    apply it identically.
    """
    if "admin" in (user.roles or []):
        session = await get_session(db, session_id)
    else:
        session = await get_session(db, session_id, tenant_id=user.tenant_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session
