"""Built-in tools the chat-with-tools agent loop can call.

This module defines the registry of built-in tools and the function that
materialises a Pydantic AI ``Tool`` list from a list of tool name strings
(as configured per chat session in ``ChatSession.agent_config["tools"]``).

Each tool is an ordinary ``async`` function that takes
``RunContext[AgentDeps]`` as its first parameter. Pydantic AI inspects
the function signature + docstring + type hints to build the JSON Schema
the LLM sees.

Tools currently shipped:

* ``synapse_council_recall_precedent`` — search precedents bank specifically
* ``synapse_recall`` — generic memory recall from any bank
* ``synapse_council_start`` — open a new council deliberation from chat
* ``mcp:server.tool`` — proxies through ``synapse.chat.mcp`` to a configured
  MCP server (see ``MCP_SERVERS`` env var)

Deferred (intentionally not registered yet):

* ``web_search`` — needs a provider (Brave / Serper / Tavily).
* ``code_interpreter`` — needs Firecracker sandbox per sandbox.md.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import RunContext, Tool

from synapse.chat import mcp as mcp_module
from synapse.memory.banks import Banks
from synapse.memory.context import AstrocyteContext

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Built-in tools
# ---------------------------------------------------------------------------


async def synapse_council_recall_precedent(
    ctx: RunContext[Any],
    query: str,
    max_results: int = 5,
) -> dict[str, Any]:
    """Search the precedents bank for past decisions similar to the query.

    Returns a list of memory hits, each with `content`, `score`, and source
    metadata. Use this when the user asks "have we decided something like this
    before?" or when you want to ground a response in prior institutional
    decisions before answering.

    Args:
        query: A natural-language description of what you're looking for.
        max_results: Maximum number of memories to return (1-25). Defaults to 5.

    Returns:
        ``{"memories": [{"id": ..., "content": ..., "score": ..., "metadata": ...}, ...]}``
    """
    return await _recall_in_bank(ctx, query, Banks.PRECEDENTS, max_results)


async def synapse_recall(
    ctx: RunContext[Any],
    bank: str,
    query: str,
    max_results: int = 5,
) -> dict[str, Any]:
    """Recall memories from a named bank.

    Use this when you need context from a specific knowledge area
    (e.g. ``'products'``, ``'policies'``, ``'team_decisions'``). Prefer
    ``synapse_council_recall_precedent`` when the question is about past
    council decisions specifically.

    Args:
        bank: Memory bank to search.
        query: Natural-language description of what to recall.
        max_results: Maximum number of memories to return (1-25). Defaults to 5.

    Returns:
        ``{"bank": ..., "memories": [...]}``
    """
    result = await _recall_in_bank(ctx, query, bank, max_results)
    return {"bank": bank, **result}


async def synapse_council_start(
    ctx: RunContext[Any],
    question: str,
    title: str | None = None,
) -> dict[str, Any]:
    """Start a new council deliberation about a question.

    Use this when the user wants the team to weigh in on a decision, not
    just a one-shot answer. Returns the new council's id and a link the
    model can mention back to the user.

    Args:
        question: The question the council should deliberate on.
        title: Optional short title (defaults to the first 80 chars of the question).
    """
    # Imported lazily so this module doesn't pull the councils domain into
    # every tool-discovery code path.
    from synapse.council.session import create_minimal_session

    deps = ctx.deps
    council = await create_minimal_session(
        db=deps.db,
        tenant_id=deps.tenant_id,
        created_by=deps.principal,
        question=question,
        title=title or question[:80],
    )

    effective_title = title or question[:80]

    return {
        "council_id": str(council.id),
        "title": effective_title,
        "status": (
            council.status.value if hasattr(council.status, "value") else str(council.status)
        ),
        "url": f"/councils/{council.id}",
    }


# ---------------------------------------------------------------------------
# Shared recall helper
# ---------------------------------------------------------------------------


async def _recall_in_bank(
    ctx: RunContext[Any],
    query: str,
    bank_id: str,
    max_results: int,
) -> dict[str, Any]:
    max_results = max(1, min(25, max_results))
    deps = ctx.deps
    astrocyte_ctx = AstrocyteContext(
        principal=deps.principal,
        tenant_id=deps.tenant_id,
    )

    try:
        hits = await deps.astrocyte.recall(
            query=query,
            bank_id=bank_id,
            context=astrocyte_ctx,
            max_results=max_results,
        )
    except Exception as exc:  # pragma: no cover — surfaced as tool error
        _logger.exception("recall(%s) failed: %s", bank_id, exc)
        return {"memories": [], "error": str(exc)}

    return {
        "memories": [
            {
                "id": h.memory_id,
                "content": h.content,
                "score": h.score,
                "tags": h.tags,
                "metadata": h.metadata,
            }
            for h in hits
        ],
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, Any] = {
    "synapse_council_recall_precedent": synapse_council_recall_precedent,
    "synapse_recall": synapse_recall,
    "synapse_council_start": synapse_council_start,
}


def build_toolset(tool_names: list[str]) -> list[Tool]:
    """Materialise a list of Pydantic AI ``Tool`` objects for the agent.

    Names starting with ``mcp:server.tool`` are dispatched to
    ``synapse.chat.mcp``, which proxies through the configured MCP server's
    ``tools/call``. Built-in names (no prefix) are looked up in
    ``_REGISTRY`` below.

    Unknown names — built-in or MCP — are silently skipped (with a warning
    logged) so a typo in ``agent_config["tools"]`` doesn't crash the agent
    loop. The LLM just won't see that tool in its schema.
    """
    mcp_names = [n for n in tool_names if n.startswith("mcp:")]
    builtin_names = [n for n in tool_names if not n.startswith("mcp:")]

    tools: list[Tool] = []

    for name in builtin_names:
        func = _REGISTRY.get(name)
        if func is None:
            _logger.warning("Unknown chat tool requested: %s", name)
            continue
        tools.append(Tool(func, name=name, takes_ctx=True))

    tools.extend(mcp_module.build_tools(mcp_names))
    return tools


def builtin_tool_names() -> list[str]:
    """Return the canonical list of built-in tool names for discovery."""
    return list(_REGISTRY.keys())
