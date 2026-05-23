"""MCP (Model Context Protocol) client integration for the chat agent loop.

Mirror of `Synapse.Chat.MCP` on the Cerebro EE Elixir side. Bridges between
a configured set of MCP servers and the agent's tool registry: any tool
name shaped like ``mcp:<server>.<tool>`` in
``ChatSession.agent_config["tools"]`` is resolved against the configured
MCP server, materialised as a Pydantic AI ``Tool`` with an async callable
that proxies ``tools/call`` to the MCP transport.

## Configuration

Set the ``SYNAPSE_MCP_SERVERS`` env var to a JSON object keyed by server
name. Each value is a transport-spec dict:

    SYNAPSE_MCP_SERVERS='{
      "weather": {"transport": "stdio", "command": ["node", "weather-mcp/server.js"]},
      "github":  {"transport": "sse",   "url": "https://mcp.github.com/sse"}
    }'

## LLM-facing name mangling

OpenAI's tool-name validator only accepts ``[a-zA-Z0-9_-]{1,64}``, so we
can't send ``mcp:server.tool`` to the model directly. The Pydantic AI
``Tool`` we materialise has name ``mcp__server__tool`` (underscore-safe).
The user-facing ``agent_config.tools`` keeps the canonical colon-dot form
— Cerebro matches this discipline.

## Testability

The MCP client class is resolved via ``_client_factory()`` which can be
monkey-patched in tests to a stub session that doesn't require a live
MCP server.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from pydantic_ai import RunContext, Tool

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config — reads SYNAPSE_MCP_SERVERS at import time + on each lookup so
# tests can monkey-patch the env var.
# ---------------------------------------------------------------------------


def configured_servers() -> dict[str, dict[str, Any]]:
    """Return the configured MCP server map.

    Source of truth is the ``SYNAPSE_MCP_SERVERS`` env var (JSON-encoded
    ``{name: {transport: ..., ...}}``). Returns an empty dict if unset or
    malformed.
    """
    raw = os.getenv("SYNAPSE_MCP_SERVERS")
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        _logger.warning("SYNAPSE_MCP_SERVERS is not valid JSON: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Public API — used by synapse.chat.tools.build_toolset
# ---------------------------------------------------------------------------


def build_tools(mcp_tool_names: list[str]) -> list[Tool]:
    """Build a Pydantic AI ``Tool`` list for the given ``mcp:server.tool``
    names. Unknown servers or tools are silently skipped (and logged) so a
    typo in a session's ``agent_config["tools"]`` doesn't crash the agent
    loop — same posture as the built-in tool registry.
    """
    tools: list[Tool] = []
    servers = configured_servers()

    for raw_name in mcp_tool_names:
        parsed = _parse_qualified_name(raw_name)
        if parsed is None:
            continue
        server, tool_name = parsed

        if server not in servers:
            _logger.warning("MCP tool skipped: unknown server %r in %r", server, raw_name)
            continue

        # We avoid making a live tools/list call at build time — that would
        # require an event loop in a sync-ish code path and could block the
        # request thread. Instead we materialise a permissive callback that
        # forwards args to tools/call; the MCP server validates at call time.
        tools.append(_materialize_tool(server, tool_name, servers[server]))

    return tools


def _parse_qualified_name(raw_name: str) -> tuple[str, str] | None:
    """Parse ``mcp:server.tool`` into ``(server, tool)`` or return None."""
    if not raw_name.startswith("mcp:"):
        return None

    rest = raw_name[len("mcp:") :]
    if "." not in rest:
        _logger.warning("MCP tool skipped: malformed name %r (missing '.')", raw_name)
        return None

    server, tool = rest.split(".", 1)
    if not server or not tool:
        _logger.warning("MCP tool skipped: malformed name %r (empty server or tool)", raw_name)
        return None

    return server, tool


def _materialize_tool(server: str, tool_name: str, server_cfg: dict[str, Any]) -> Tool:
    """Build a Pydantic AI ``Tool`` whose callable proxies to the MCP server."""

    async def _proxy(
        _ctx: RunContext[Any], arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = await dispatch_call(server, tool_name, arguments or {}, server_cfg)
        return result

    return Tool(
        _proxy,
        # LLM-facing name uses ``__`` separators so it passes OpenAI's
        # ``[a-zA-Z0-9_-]`` tool-name validation. The user's
        # ``agent_config.tools`` keeps the canonical ``mcp:server.tool``.
        name=f"mcp__{server}__{tool_name}",
        description=(
            f"MCP tool '{tool_name}' on server '{server}'. Pass arguments as "
            f"defined by the server's input_schema."
        ),
        takes_ctx=True,
    )


async def dispatch_call(
    server: str,
    tool_name: str,
    arguments: dict[str, Any],
    server_cfg: dict[str, Any],
) -> dict[str, Any]:
    """Open an MCP session against ``server_cfg`` and call ``tool_name``."""
    factory = _client_factory()

    try:
        async with factory(server_cfg) as session:
            await session.initialize()
            result = await session.call_tool(name=tool_name, arguments=arguments)
            return {
                "server": server,
                "tool": tool_name,
                "result": _serialize_result(result),
            }
    except Exception as exc:
        _logger.warning("MCP tools/call failed: server=%s tool=%s err=%s", server, tool_name, exc)
        return {
            "server": server,
            "tool": tool_name,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Client factory (override in tests)
# ---------------------------------------------------------------------------

# Sentinel for the default client factory; tests can replace this with an
# async context manager that yields a stub session. Kept as a module-level
# variable rather than a class attribute so monkey-patching is local to
# each test.
_OVERRIDE_FACTORY: Callable[[dict[str, Any]], Any] | None = None


def _client_factory() -> Callable[[dict[str, Any]], Any]:
    """Return the active MCP-session factory.

    Default uses the official ``mcp`` SDK (stdio or sse transport per the
    server config). Tests inject a stub via ``set_client_factory``.
    """
    if _OVERRIDE_FACTORY is not None:
        return _OVERRIDE_FACTORY

    return _default_client_factory


def set_client_factory(factory: Callable[[dict[str, Any]], Any] | None) -> None:
    """Override the MCP-session factory. Pass ``None`` to restore default.

    Used in unit tests to swap a stub session in. The factory takes the
    server config dict and returns an async context manager yielding an
    object with ``initialize()``, ``list_tools()``, and
    ``call_tool(name, arguments)`` coroutines.
    """
    global _OVERRIDE_FACTORY
    _OVERRIDE_FACTORY = factory


def _default_client_factory(server_cfg: dict[str, Any]):
    """Build a real MCP client session for ``server_cfg``.

    The ``mcp`` SDK exposes two transports we care about:

      * stdio — spawn the server as a child process. Use when the MCP
        server ships as a CLI you can exec.
      * sse — connect to an HTTP/SSE endpoint. Use for remote / containerised
        MCP servers (the E2E test stack pattern).

    Returns an async context manager that wraps connection + session
    setup so the caller can ``async with factory(cfg) as session:``.
    """
    # Imports kept local: when the mcp package is missing (some test envs),
    # ``configured_servers()`` returns {} and ``_default_client_factory``
    # is never called — so we don't want to fail at import time.
    transport = server_cfg.get("transport", "sse")

    if transport == "stdio":
        return _stdio_session(server_cfg)
    elif transport == "sse":
        return _sse_session(server_cfg)
    else:
        raise ValueError(f"Unsupported MCP transport: {transport!r}")


class _StdioSession:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._stack: Any = None
        self._session: Any = None

    async def __aenter__(self):
        from contextlib import AsyncExitStack

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=self._cfg["command"][0],
            args=self._cfg["command"][1:] if len(self._cfg["command"]) > 1 else [],
        )

        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        if self._stack is not None:
            await self._stack.__aexit__(exc_type, exc, tb)


class _SseSession:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self._cfg = cfg
        self._stack: Any = None
        self._session: Any = None

    async def __aenter__(self):
        from contextlib import AsyncExitStack

        from mcp import ClientSession
        from mcp.client.sse import sse_client

        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(sse_client(self._cfg["url"]))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        if self._stack is not None:
            await self._stack.__aexit__(exc_type, exc, tb)


def _stdio_session(cfg: dict[str, Any]) -> _StdioSession:
    return _StdioSession(cfg)


def _sse_session(cfg: dict[str, Any]) -> _SseSession:
    return _SseSession(cfg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_result(result: Any) -> Any:
    """Convert an MCP CallToolResult into a JSON-serialisable dict.

    The SDK returns a structured object with ``content`` (list of content
    items) and ``isError``. We flatten the textual parts into a list so the
    LLM gets something useful to read back, preserving the isError flag.
    """
    if result is None:
        return None

    # mcp.types.CallToolResult has attributes; fall back to dict-style on
    # custom test doubles.
    content = getattr(result, "content", None)
    if content is None and isinstance(result, dict):
        content = result.get("content")

    is_error = getattr(result, "isError", None)
    if is_error is None and isinstance(result, dict):
        is_error = result.get("isError", False)

    return {
        "content": [_serialize_content_item(c) for c in (content or [])],
        "isError": bool(is_error),
    }


def _serialize_content_item(item: Any) -> dict[str, Any]:
    """Flatten an MCP content item (TextContent/ImageContent/...) to a dict."""
    if isinstance(item, dict):
        return item

    # TextContent has .type and .text; ImageContent has .type and .data/.mimeType.
    out: dict[str, Any] = {"type": getattr(item, "type", "unknown")}
    for attr in ("text", "data", "mimeType"):
        val = getattr(item, attr, None)
        if val is not None:
            out[attr] = val
    return out
