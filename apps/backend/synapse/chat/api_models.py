"""Pydantic API models for the chat-with-tools surface.

Shapes match ``priv/contracts/chat-api-v1.openapi.json`` § components/schemas
(the cross-backend contract). Both Synapse OSS and Cerebro EE produce JSON
that conforms to this contract; conformance tests in ``cerebro/e2e/`` verify.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    """Per-session agent configuration.

    All fields optional — workspace defaults apply when omitted.
    """

    model: str | None = None
    """Provider-prefixed model identifier (e.g., ``openai:gpt-4o``,
    ``cerebro:standard`` for platform-mediated tokens).

    Synapse's existing model strings (``"gpt-4o"``, ``"anthropic/claude-..."``)
    are accepted and translated by ``synapse.llm.client``.
    """

    instructions: str | None = None
    """System prompt / instructions for the agent."""

    tools: list[str] = Field(default_factory=list)
    """Enabled tool identifiers — built-ins (``code_interpreter``, ``web_search``,
    ``image_generate``, ``audio_generate``) and MCP tool names
    (``mcp:{server}.{tool}``)."""

    memory_banks: list[str] = Field(default_factory=list)
    """Astrocyte memory banks this agent has read/write access to."""

    sandbox_runtime_preference: Literal["auto", "server", "client", "local"] = "auto"
    """Sandbox runtime selection per ``sandbox.md``. Defaults to auto;
    the dispatcher picks based on transport + policy + capability."""


class ChatSessionCreate(BaseModel):
    """Request body for ``POST /v1/chat/sessions``."""

    title: str | None = None
    council_id: uuid.UUID | None = None
    """Optional — chat with a closed council's verdict (Mode 3)."""

    agent_config: AgentConfig = Field(default_factory=AgentConfig)


class ChatSessionUpdate(BaseModel):
    """Request body for ``PATCH /v1/chat/sessions/{id}``.

    All fields optional; only the provided ones update.
    """

    title: str | None = None
    status: Literal["active", "archived"] | None = None
    agent_config: AgentConfig | None = None


class ChatSession(BaseModel):
    """Chat session response. Mirrors ChatSession in chat-api-v1.openapi.json."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: uuid.UUID
    tenant_id: str | None
    created_by: str
    title: str | None
    status: Literal["active", "archived"]
    council_id: uuid.UUID | None = None
    agent_config: dict[str, Any] = Field(default_factory=dict)
    parent_session_id: uuid.UUID | None = None
    parent_fork_event_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ChatSessionList(BaseModel):
    """Response body for ``GET /v1/chat/sessions``.

    Cursor pagination via ``next_before_id`` matching the migration-bundle /
    thread-events convention — use the cursor in a subsequent request's
    ``before_id`` query param to fetch older sessions.
    """

    data: list[ChatSession]
    next_before_id: datetime | None = None
    """Created-at cursor for the next page (older). Null when no more results."""


class ForkRequest(BaseModel):
    """Request body for ``POST /v1/chat/sessions/{id}/fork``.

    Implemented in the next chat-with-tools commit. Included here so the
    contract surface is complete from the start.
    """

    from_event_id: int
    """Event id in the parent thread to fork from."""

    title: str | None = None


class MessageSendRequest(BaseModel):
    """Request body for ``POST /v1/chat/sessions/{id}/messages``.

    Phase 1A commit covers session CRUD only; the actual messages endpoint
    + SSE stream ships in the next commit. Defining the request shape here
    keeps the contract surface coherent.
    """

    content: str


class MessageEditRequest(BaseModel):
    """Request body for ``POST /v1/chat/sessions/{id}/messages/{message_id}/edit``."""

    content: str


class MessageRegenerateRequest(BaseModel):
    """Request body for ``POST /v1/chat/sessions/{id}/messages/{message_id}/regenerate``."""

    agent_config_override: AgentConfig | None = None
