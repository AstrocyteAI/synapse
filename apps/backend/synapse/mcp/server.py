"""Synapse MCP server — agent-to-agent council access (B2).

Exposes five tools that let AI agents interact with Synapse councils:

    start_council   — convene a new council and return immediately
    join            — inspect an existing council (status + recent events)
    contribute      — inject a message into an in-progress council (Mode 2)
    recall_precedent — search the precedents bank in Astrocyte memory
    close           — close a council, accepting the deliberation so far

Mount in FastAPI:

    from synapse.mcp.server import mcp
    app.mount("/mcp", mcp.streamable_http_app())

Or run standalone:

    uv run mcp run synapse/mcp/server.py
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

import httpx
from mcp.server.fastmcp import Context, FastMCP

from synapse.config import get_settings
from synapse.council.models import CouncilMember, CreateCouncilRequest
from synapse.council.orchestrator import CouncilOrchestrator
from synapse.council.session import (
    close_session,
    create_session,
    get_session,
    mark_failed,
)
from synapse.council.thread import (
    append_event,
    create_thread,
    get_history,
    get_thread_by_council,
    thread_event_dict,
)
from synapse.db.models import CouncilStatus, ThreadEventType
from synapse.db.session import create_engine_and_sessionmaker
from synapse.llm.client import LLMClient
from synapse.memory.banks import Banks
from synapse.memory.context import AstrocyteContext
from synapse.memory.gateway_client import AstrocyteGatewayClient
from synapse.realtime.centrifugo import CentrifugoClient

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — sets up DB, Astrocyte, and Centrifugo clients
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(server: FastMCP):  # noqa: ARG001
    settings = get_settings()
    _, sessionmaker = create_engine_and_sessionmaker(settings.database_url)

    astrocyte_http = httpx.AsyncClient(timeout=60.0)
    centrifugo_http = httpx.AsyncClient(timeout=10.0)

    astrocyte = AstrocyteGatewayClient(
        base_url=settings.astrocyte_gateway_url,
        api_key=settings.astrocyte_token,
        http_client=astrocyte_http,
    )
    centrifugo = CentrifugoClient(
        api_url=settings.centrifugo_api_url,
        api_key=settings.centrifugo_api_key,
        http_client=centrifugo_http,
    )

    try:
        yield {
            "sessionmaker": sessionmaker,
            "astrocyte": astrocyte,
            "centrifugo": centrifugo,
            "settings": settings,
        }
    finally:
        await astrocyte_http.aclose()
        await centrifugo_http.aclose()


# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("synapse", lifespan=_lifespan)


def _lc(ctx: Context) -> dict[str, Any]:
    """Shorthand for the lifespan context dict."""
    return ctx.request_context.lifespan_context  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tool 1 — start_council
# ---------------------------------------------------------------------------


@mcp.tool()
async def start_council(
    ctx: Context,
    question: str,
    topic_tag: str | None = None,
    template_id: str | None = None,
    council_type: str = "llm",
) -> dict[str, Any]:
    """Convene a new Synapse council to deliberate on a question.

    The council runs autonomously (gather → rank → synthesise) and publishes
    real-time events to ``thread:{thread_id}`` on the Centrifugo channel.

    Use ``join`` to check progress or subscribe to the Centrifugo channel for
    live stage events.

    Args:
        question: The question or decision the council should deliberate on.
        topic_tag: Optional topic tag for grouping related councils (e.g. "product").
        template_id: Optional built-in template name (e.g. "architecture-review").
        council_type: "llm" (default) — the only type supported in open-source.

    Returns:
        session_id: UUID of the council session to track with ``join``.
        thread_id: UUID of the chat thread for event history.
        status: "pending" — the council starts immediately in the background.
    """
    lc = _lc(ctx)
    settings = lc["settings"]
    sessionmaker = lc["sessionmaker"]
    astrocyte = lc["astrocyte"]
    centrifugo = lc["centrifugo"]

    members = [CouncilMember(**m) for m in settings.default_members]
    chairman = CouncilMember(**settings.default_chairman)
    council_context = AstrocyteContext(principal="mcp:agent", tenant_id=None)

    async with sessionmaker() as db:
        session = await create_session(
            db=db,
            request=CreateCouncilRequest(
                question=question,
                topic_tag=topic_tag,
                template_id=template_id,
                council_type=council_type,
            ),
            members=members,
            chairman=chairman,
            created_by="mcp:agent",
        )
        thread = await create_thread(
            db,
            council_id=session.id,
            created_by="mcp:agent",
            title=question[:120],
        )
        await append_event(
            db,
            thread_id=thread.id,
            event_type=ThreadEventType.council_started,
            actor_id="system",
            metadata={
                "council_id": str(session.id),
                "question": question,
                "member_count": len(members),
            },
        )

    session_id = session.id
    thread_id = thread.id

    orchestrator = CouncilOrchestrator(
        astrocyte=astrocyte,
        centrifugo=centrifugo,
        llm=LLMClient(settings),
        settings=settings,
    )

    async def _run() -> None:
        async with sessionmaker() as bg_db:
            try:
                await orchestrator.run(
                    session_id=session_id,
                    question=question,
                    members=members,
                    chairman=chairman,
                    context=council_context,
                    db=bg_db,
                    council_type=council_type,
                    topic_tag=topic_tag,
                )
            except Exception as exc:
                _logger.error("MCP council %s failed: %s", session_id, exc)
                async with sessionmaker() as err_db:
                    await mark_failed(err_db, session_id, error=str(exc))

    asyncio.create_task(_run())

    return {
        "session_id": str(session_id),
        "thread_id": str(thread_id),
        "status": CouncilStatus.pending,
    }


# ---------------------------------------------------------------------------
# Tool 2 — join
# ---------------------------------------------------------------------------


@mcp.tool()
async def join(
    ctx: Context,
    session_id: str,
    recent_event_limit: int = 20,
) -> dict[str, Any]:
    """Inspect a council session and retrieve recent thread events.

    Use this to catch up on a council you started or were told about.
    Returns the current status, verdict (if closed), and the most recent
    thread events in chronological order so you have full deliberation context.

    Args:
        session_id: The UUID returned by ``start_council``.
        recent_event_limit: How many recent events to return (default 20, max 50).

    Returns:
        session_id, status, question, thread_id, verdict (if closed),
        and recent_events list in chronological order.
    """
    lc = _lc(ctx)
    sessionmaker = lc["sessionmaker"]

    sid = uuid.UUID(session_id)
    limit = min(recent_event_limit, 50)

    async with sessionmaker() as db:
        session = await get_session(db, sid)
        if not session:
            return {"error": f"Council session {session_id} not found"}

        thread = await get_thread_by_council(db, sid)
        if not thread:
            return {
                "session_id": session_id,
                "status": session.status,
                "question": session.question,
                "thread_id": None,
                "verdict": session.verdict,
                "recent_events": [],
            }

        events = await get_history(db, thread.id, limit=limit)
        events_asc = list(reversed(events))  # history returns DESC; flip to chronological

    return {
        "session_id": session_id,
        "status": session.status,
        "question": session.question,
        "thread_id": str(thread.id),
        "verdict": session.verdict,
        "confidence_label": session.confidence_label,
        "consensus_score": session.consensus_score,
        "member_count": len(session.members),
        "recent_events": [thread_event_dict(e) for e in events_asc],
    }


# ---------------------------------------------------------------------------
# Tool 3 — contribute
# ---------------------------------------------------------------------------


@mcp.tool()
async def contribute(
    ctx: Context,
    session_id: str,
    content: str,
    actor_name: str = "Agent",
) -> dict[str, Any]:
    """Contribute a message to an in-progress council (Mode 2).

    Appends a ``user_message`` event to the council thread and broadcasts it
    to all Centrifugo subscribers in real time.  Use this to inject additional
    context, facts, or constraints that the council members should consider.

    Most effective when called before or during Stage 1 (gathering).  Messages
    sent after the council closes are still persisted but do not affect the
    verdict.

    Args:
        session_id: The UUID of the council session.
        content: The message to inject into the deliberation.
        actor_name: Display name shown in the thread (default "Agent").

    Returns:
        The persisted thread event dict.
    """
    lc = _lc(ctx)
    sessionmaker = lc["sessionmaker"]
    centrifugo = lc["centrifugo"]

    sid = uuid.UUID(session_id)

    async with sessionmaker() as db:
        session = await get_session(db, sid)
        if not session:
            return {"error": f"Council session {session_id} not found"}

        thread = await get_thread_by_council(db, sid)
        if not thread:
            return {"error": "No thread found for this council session"}

        event = await append_event(
            db,
            thread_id=thread.id,
            event_type=ThreadEventType.user_message,
            actor_id="mcp:agent",
            actor_name=actor_name,
            content=content,
        )

    payload = thread_event_dict(event)

    # Best-effort publish — DB write is already committed
    try:
        await centrifugo.publish(f"thread:{thread.id}", payload)
    except Exception:
        _logger.warning("Centrifugo publish failed after MCP contribute", exc_info=True)

    return payload


# ---------------------------------------------------------------------------
# Tool 4 — recall_precedent
# ---------------------------------------------------------------------------


@mcp.tool()
async def recall_precedent(
    ctx: Context,
    query: str,
    tags: list[str] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Recall relevant past decisions from Synapse's memory.

    Searches the ``precedents`` bank in Astrocyte for past council decisions
    semantically similar to the query.  Call this before ``start_council`` to
    understand what has already been decided on a related topic.

    Args:
        query: Natural language description of what you're looking for.
        tags: Optional list of tags to narrow the search.
        limit: Maximum number of results (1–20, default 5).

    Returns:
        List of memory hits sorted by relevance score (highest first).
        Each hit has: memory_id, content, score, bank_id, metadata.
    """
    lc = _lc(ctx)
    astrocyte = lc["astrocyte"]

    context = AstrocyteContext(principal="mcp:agent", tenant_id=None)

    hits = await astrocyte.recall(
        query=query,
        bank_id=Banks.PRECEDENTS,
        context=context,
        max_results=max(1, min(limit, 20)),
        tags=tags,
    )

    return [
        {
            "memory_id": h.memory_id,
            "content": h.content,
            "score": h.score,
            "bank_id": h.bank_id,
            "metadata": h.metadata,
        }
        for h in hits
    ]


# ---------------------------------------------------------------------------
# Tool 5 — close
# ---------------------------------------------------------------------------


@mcp.tool()
async def close(
    ctx: Context,
    session_id: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Close a council session immediately.

    If the council is already closed (fully synthesised verdict available),
    returns the existing verdict.

    If the council is still running, closes it immediately with the provided
    ``reason`` as the verdict placeholder.  The orchestrator may still be
    running stages in the background — if it completes normally it will
    overwrite this placeholder with the real synthesised verdict.

    Args:
        session_id: UUID of the council session to close.
        reason: Optional text to use as the interim verdict (e.g. "Closed early
                — agent decided the question was answered by Stage 1 responses.").

    Returns:
        session_id, status, verdict (current or newly set), and already_closed flag.
    """
    lc = _lc(ctx)
    sessionmaker = lc["sessionmaker"]

    sid = uuid.UUID(session_id)
    interim_verdict = reason or "Council closed by agent request."

    async with sessionmaker() as db:
        session = await get_session(db, sid)
        if not session:
            return {"error": f"Council session {session_id} not found"}

        if session.status == CouncilStatus.closed:
            return {
                "session_id": session_id,
                "status": session.status,
                "verdict": session.verdict,
                "already_closed": True,
            }

        if session.status == CouncilStatus.failed:
            return {
                "session_id": session_id,
                "status": session.status,
                "verdict": None,
                "already_failed": True,
            }

        updated = await close_session(db, sid, verdict=interim_verdict)

    return {
        "session_id": session_id,
        "status": updated.status if updated else CouncilStatus.closed,
        "verdict": updated.verdict if updated else interim_verdict,
        "already_closed": False,
    }
