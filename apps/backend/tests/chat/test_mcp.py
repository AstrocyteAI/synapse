"""Tests for synapse.chat.mcp — MCP-prefixed tool wiring.

Stubs the MCP session factory so unit coverage doesn't need a live MCP
server. Mirrors Synapse.Chat.MCPTest on the Cerebro side; same naming
conventions (mcp:server.tool canonical, mcp__server__tool LLM-side).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest

from synapse.chat import mcp as mcp_module

# ---------------------------------------------------------------------------
# Stub MCP session — used in place of the real ClientSession.
# ---------------------------------------------------------------------------


class _StubSession:
    """Minimal stand-in for ``mcp.ClientSession`` for the dispatch path."""

    def __init__(self, tools: list[dict[str, Any]] | None = None) -> None:
        self._tools = tools or []
        self.call_log: list[tuple[str, dict[str, Any]]] = []

    async def initialize(self) -> None:
        pass

    async def list_tools(self):  # pragma: no cover — not exercised today
        class _Resp:
            def __init__(self, tools):
                self.tools = tools

        return _Resp(self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None):
        self.call_log.append((name, arguments or {}))

        # Echo back the args as a "TextContent"-shaped dict; the
        # serializer in mcp_module flattens it.
        return {
            "content": [{"type": "text", "text": json.dumps({"echo": arguments})}],
            "isError": False,
        }


def _make_factory(session: _StubSession):
    @asynccontextmanager
    async def _factory(_cfg):
        yield session

    return _factory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Each test starts with no overridden factory and no configured servers."""
    mcp_module.set_client_factory(None)
    monkeypatch.delenv("SYNAPSE_MCP_SERVERS", raising=False)
    yield
    mcp_module.set_client_factory(None)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfiguredServers:
    def test_returns_parsed_env_var(self, monkeypatch):
        monkeypatch.setenv(
            "SYNAPSE_MCP_SERVERS",
            json.dumps({"weather": {"transport": "sse", "url": "http://w/"}}),
        )

        assert mcp_module.configured_servers() == {
            "weather": {"transport": "sse", "url": "http://w/"}
        }

    def test_empty_when_unset(self):
        assert mcp_module.configured_servers() == {}

    def test_empty_when_malformed_json(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_MCP_SERVERS", "{not valid")
        assert mcp_module.configured_servers() == {}


# ---------------------------------------------------------------------------
# build_tools — name mangling, server scope, typo handling
# ---------------------------------------------------------------------------


class TestBuildTools:
    def test_materialises_an_mcp_tool(self, monkeypatch):
        monkeypatch.setenv(
            "SYNAPSE_MCP_SERVERS",
            json.dumps({"weather": {"transport": "sse", "url": "http://w/"}}),
        )

        tools = mcp_module.build_tools(["mcp:weather.get_forecast"])
        assert len(tools) == 1
        # LLM-facing name uses underscores — `mcp:server.tool` doesn't pass
        # OpenAI's [a-zA-Z0-9_-] validation, so we mangle.
        assert tools[0].name == "mcp__weather__get_forecast"

    def test_preserves_server_scope_for_same_named_tools(self, monkeypatch):
        monkeypatch.setenv(
            "SYNAPSE_MCP_SERVERS",
            json.dumps(
                {
                    "github": {"transport": "sse", "url": "http://g/"},
                    "gitlab": {"transport": "sse", "url": "http://l/"},
                }
            ),
        )

        tools = mcp_module.build_tools(["mcp:github.list_repos", "mcp:gitlab.list_repos"])
        names = sorted(t.name for t in tools)
        assert names == ["mcp__github__list_repos", "mcp__gitlab__list_repos"]

    def test_silently_skips_unknown_server(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_MCP_SERVERS", "{}")
        assert mcp_module.build_tools(["mcp:ghost.tool"]) == []

    def test_silently_skips_malformed_names(self):
        # No crash, no tools — same posture as builtin tool typos.
        assert mcp_module.build_tools(["mcp:", "mcp:no_dot", "mcp:.empty_server"]) == []

    def test_ignores_non_mcp_names(self, monkeypatch):
        monkeypatch.setenv(
            "SYNAPSE_MCP_SERVERS",
            json.dumps({"x": {"transport": "sse", "url": "http://x/"}}),
        )

        # `build_tools` is the MCP-only side — caller routes non-mcp names
        # via the built-in registry.
        assert mcp_module.build_tools(["synapse_council_recall_precedent"]) == []


# ---------------------------------------------------------------------------
# dispatch_call — the callback path through the MCP session
# ---------------------------------------------------------------------------


class TestDispatchCall:
    @pytest.mark.asyncio
    async def test_call_tool_returns_serialised_result(self):
        session = _StubSession()
        mcp_module.set_client_factory(_make_factory(session))

        result = await mcp_module.dispatch_call(
            "weather",
            "get_forecast",
            {"location": "SF"},
            {"transport": "sse", "url": "http://w/"},
        )

        # The stub session's `call_tool` was hit with the same args.
        assert session.call_log == [("get_forecast", {"location": "SF"})]

        # Response envelope keeps the server/tool context for the LLM.
        assert result["server"] == "weather"
        assert result["tool"] == "get_forecast"
        # Serializer flattened the content array.
        assert result["result"]["content"][0]["type"] == "text"
        assert "SF" in result["result"]["content"][0]["text"]
        assert result["result"]["isError"] is False

    @pytest.mark.asyncio
    async def test_exception_surfaces_as_error_field(self):
        @asynccontextmanager
        async def _failing_factory(_cfg):
            raise RuntimeError("transport down")
            yield  # pragma: no cover — never reached

        mcp_module.set_client_factory(_failing_factory)

        result = await mcp_module.dispatch_call(
            "weather", "get_forecast", {}, {"transport": "sse", "url": "x"}
        )

        assert result["server"] == "weather"
        assert result["tool"] == "get_forecast"
        assert "transport down" in result["error"]
