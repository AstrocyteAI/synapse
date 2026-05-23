"""Chat sessions router — CRUD endpoints + SSE messages endpoint.

Implements ``priv/contracts/chat-api-v1.openapi.json`` § /v1/chat/sessions/*
(the cross-backend contract; Cerebro EE Elixir mirrors).

Covers:

  * Session lifecycle: ``POST/GET/PATCH/DELETE /v1/chat/sessions{,/id}``
  * Send message + SSE agent loop: ``POST /v1/chat/sessions/{id}/messages``

Not in this router (deferred to next chat-with-tools commit):

  * ``POST /v1/chat/sessions/{id}/messages/{message_id}/edit``
  * ``POST /v1/chat/sessions/{id}/messages/{message_id}/regenerate``
  * ``POST /v1/chat/sessions/{id}/fork``
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
    MessageSendRequest,
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
# Private helpers
# ---------------------------------------------------------------------------


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
