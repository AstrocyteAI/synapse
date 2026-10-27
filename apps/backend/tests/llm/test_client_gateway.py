"""LLMClient routing: direct providers by default, an AISIX gateway when configured."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai.models.openai import OpenAIChatModel

from synapse.config import Settings
from synapse.llm.client import LLMClient


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_no_gateway_resolves_provider_spec() -> None:
    client = LLMClient(_settings())
    assert (
        client._build_model("claude-3-5-sonnet-20241022") == "anthropic:claude-3-5-sonnet-20241022"
    )
    assert client._build_model("gemini/gemini-1.5-pro") == "google-gla:gemini-1.5-pro"
    assert client._build_model("gpt-4o") == "openai:gpt-4o"


@pytest.mark.parametrize(
    ("model", "alias"),
    [
        ("chat-default", "chat-default"),
        ("anthropic/claude-sonnet", "claude-sonnet"),
        ("openai:gpt-4o", "gpt-4o"),
    ],
)
def test_gateway_sends_the_bare_alias_to_the_gateway(model: str, alias: str) -> None:
    client = LLMClient(
        _settings(llm_gateway_base_url="http://aisix:4000/v1", llm_gateway_api_key="gw-key")
    )
    built = client._build_model(model)
    assert isinstance(built, OpenAIChatModel)
    assert built.model_name == alias
    assert str(built.client.base_url).rstrip("/") == "http://aisix:4000/v1"
    assert built.client.api_key == "gw-key"


def test_gateway_without_a_key_uses_a_placeholder() -> None:
    client = LLMClient(_settings(llm_gateway_base_url="http://aisix:4000/v1"))
    built = client._build_model("chat-default")
    assert built.client.api_key == "sk-placeholder"


def test_retired_litellm_proxy_setting_stops_startup() -> None:
    with pytest.raises(ValidationError, match="LLM_GATEWAY_BASE_URL"):
        _settings(litellm_api_base="http://litellm:4000")


def test_a_leftover_provider_variable_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNAPSE_LLM_PROVIDER", "litellm")
    assert _settings().llm_gateway_base_url == ""
