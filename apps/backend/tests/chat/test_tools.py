"""Tests for synapse.chat.tools — registry + build_toolset routing.

Targets the Model A surface mirror of Cerebro's Synapse.Chat.Tools tests:
same tool names, same build_toolset semantics (mcp: routes to mcp module,
typo-resilience, builtin registry).
"""

from __future__ import annotations

import json

import pytest

from synapse.chat import mcp as mcp_module
from synapse.chat.tools import build_toolset, builtin_tool_names


@pytest.fixture(autouse=True)
def _reset_mcp_state(monkeypatch):
    mcp_module.set_client_factory(None)
    monkeypatch.delenv("SYNAPSE_MCP_SERVERS", raising=False)
    yield
    mcp_module.set_client_factory(None)


class TestBuiltinRegistry:
    def test_lists_all_documented_tools(self):
        names = builtin_tool_names()
        assert "synapse_council_recall_precedent" in names
        assert "synapse_recall" in names
        assert "synapse_council_start" in names


class TestBuildToolset:
    def test_materialises_known_builtin(self):
        tools = build_toolset(["synapse_council_recall_precedent"])
        assert len(tools) == 1
        assert tools[0].name == "synapse_council_recall_precedent"

    def test_unknown_name_silently_skipped(self):
        # No crash — typo-resilience matches Cerebro behaviour.
        assert build_toolset(["does_not_exist"]) == []

    def test_mcp_name_routes_through_mcp_module(self, monkeypatch):
        monkeypatch.setenv(
            "SYNAPSE_MCP_SERVERS",
            json.dumps({"weather": {"transport": "sse", "url": "http://w/"}}),
        )

        tools = build_toolset(["mcp:weather.get_forecast"])
        assert len(tools) == 1
        # Mangled LLM-facing name.
        assert tools[0].name == "mcp__weather__get_forecast"

    def test_mixes_builtin_and_mcp(self, monkeypatch):
        monkeypatch.setenv(
            "SYNAPSE_MCP_SERVERS",
            json.dumps({"weather": {"transport": "sse", "url": "http://w/"}}),
        )

        tools = build_toolset(["synapse_council_recall_precedent", "mcp:weather.get_forecast"])
        names = sorted(t.name for t in tools)
        assert names == ["mcp__weather__get_forecast", "synapse_council_recall_precedent"]

    def test_mcp_unknown_server_skipped(self, monkeypatch):
        monkeypatch.setenv("SYNAPSE_MCP_SERVERS", "{}")
        assert build_toolset(["mcp:ghost.tool"]) == []

    def test_all_three_builtins_materialise(self):
        tools = build_toolset(
            [
                "synapse_council_recall_precedent",
                "synapse_recall",
                "synapse_council_start",
            ]
        )
        names = sorted(t.name for t in tools)
        assert names == [
            "synapse_council_recall_precedent",
            "synapse_council_start",
            "synapse_recall",
        ]
