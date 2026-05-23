"""LLM client — Pydantic AI-backed wrapper for uniform multi-model access.

Replaces the earlier LiteLLM-only client (v0.x). Pydantic AI brings:

  * Native multi-provider routing (OpenAI / Anthropic / Google / Bedrock /
    Groq / Cerebras / xAI / OpenRouter / Ollama / Mistral / etc.) without
    requiring a separate gateway.
  * Type-safe structured output via Pydantic models (used by stages that
    want typed verdicts / rankings — see ``output_type`` parameter).
  * Built-in Logfire / OpenTelemetry instrumentation hooks for tracing
    every LLM call with GenAI semantic conventions.
  * Stable v1 contract (since September 2025) — replaces the LiteLLM
    cycle-of-breaking-changes problem.

Public API preserved from the LiteLLM-era v0.x:

  * ``LLMClient.complete(model, messages, temperature=, max_tokens=)``
    → returns the text content string.

Tests mock at the ``LLMClient`` level via ``AsyncMock`` (see
``tests/conftest.py::mock_llm``) — the internal swap is invisible to
existing test fixtures.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from synapse.config import Settings

_logger = logging.getLogger(__name__)


class LLMClient:
    """Async LLM client backed by Pydantic AI.

    Public method ``complete`` preserves the v0.x signature and contract:
    pass a model identifier and a list of ``{role, content}`` messages,
    receive the response text. All provider abstraction, retries, and
    error handling are delegated to Pydantic AI.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        """Call a model with a list of messages and return the response text.

        ``model`` accepts the same identifiers Synapse has always used —
        bare names (``"gpt-4o"``, ``"claude-3-5-sonnet-20241022"``) or
        LiteLLM-style prefixed (``"anthropic/claude-..."``, ``"gemini/..."``).
        Translation to Pydantic AI's canonical ``provider:model`` spec is
        handled internally.

        ``messages`` is the standard OpenAI-style list. ``role`` may be one
        of ``system``, ``user``, ``assistant``. The function extracts
        system messages into the agent's system prompt and builds a
        ``ModelMessage`` history for any prior user / assistant turns,
        passing the final user turn as the agent's ``user_prompt``.

        ``temperature`` and ``max_tokens`` are forwarded as model settings.
        Additional kwargs flow into ``model_settings`` as well — e.g.,
        ``top_p``, ``presence_penalty``, etc.

        Returns: the response text content.

        Raises: ``ValueError`` if the model returns an empty response;
                provider-level exceptions propagate uncaught (rate limits,
                auth errors, network issues) so callers can decide retry
                semantics.
        """
        agent_model = self._build_model(model)
        system_prompts, history, user_prompt = _split_messages(messages)

        agent = Agent(
            agent_model,
            system_prompt=system_prompts,
            model_settings={
                "temperature": temperature,
                "max_tokens": max_tokens,
                **kwargs,
            },
        )

        result = await agent.run(user_prompt, message_history=history)
        text = result.output

        if not text:
            raise ValueError(f"Model {model} returned empty response")

        return text

    def _build_model(self, model: str):
        """Translate Synapse's model identifier to a Pydantic AI model.

        Three cases:
          * If ``litellm_api_base`` is set in settings, route every call
            through that endpoint via Pydantic AI's OpenAI-compatible
            provider, preserving the LiteLLM-proxy escape hatch for
            customers who run an upstream gateway.
          * Otherwise, translate to ``provider:model`` format and return
            the string — Pydantic AI's factory resolves it.
          * Bare names default to ``openai:`` (matches LiteLLM behaviour).
        """
        if self._settings.litellm_api_base:
            return OpenAIChatModel(
                _strip_provider_prefix(model),
                provider=OpenAIProvider(
                    base_url=self._settings.litellm_api_base,
                    api_key=self._settings.litellm_api_key or "sk-placeholder",
                ),
            )

        return _to_pydantic_ai_model_spec(model)


def derive_display_name(model_id: str) -> str:
    """Derive a readable display name from a model ID when no name is provided.

    Unchanged from the LiteLLM-era client; the rendering rules don't depend
    on which library actually calls the model.
    """
    lower = model_id.lower()
    if "/" in lower:
        lower = lower.split("/", 1)[1]
    if ":" in lower:
        lower = lower.split(":", 1)[1]

    if lower.startswith("gpt"):
        return "GPT-" + model_id.split("gpt-", 1)[-1].replace("-", " ").title().replace(" ", "-")
    if "claude" in lower:
        return "Claude"
    if "gemini" in lower:
        return "Gemini"
    if "grok" in lower:
        return "Grok"
    if "llama" in lower:
        return "Llama"
    if lower.startswith("agent:"):
        return model_id.split(":", 1)[1]
    return model_id


# ---------------------------------------------------------------------------
# Model identifier translation
# ---------------------------------------------------------------------------


# Map LiteLLM-style provider prefixes (used in Synapse's existing default
# model list) to Pydantic AI's canonical provider IDs.
_PROVIDER_PREFIX_MAP = {
    "openai": "openai",
    "anthropic": "anthropic",
    "google": "google-gla",
    "gemini": "google-gla",
    "groq": "groq",
    "cerebras": "cerebras",
    "openrouter": "openrouter",
    "mistral": "mistral",
    "deepseek": "deepseek",
    "grok": "grok",
    "xai": "grok",
}


def _to_pydantic_ai_model_spec(model: str) -> str:
    """Translate Synapse's model string to Pydantic AI's ``provider:model`` format.

      * ``"openai:gpt-4o"``           → ``"openai:gpt-4o"`` (pass-through)
      * ``"gpt-4o"``                  → ``"openai:gpt-4o"`` (default vendor)
      * ``"anthropic/claude-3-5"``    → ``"anthropic:claude-3-5"``
      * ``"gemini/gemini-1.5-pro"``   → ``"google-gla:gemini-1.5-pro"``
      * ``"claude-3-5-sonnet-..."``   → ``"anthropic:claude-3-5-sonnet-..."`` (inferred from name)
      * ``"o1-preview"``              → ``"openai:o1-preview"`` (inferred OpenAI o-series)

    Bare-name inference matches LiteLLM's behaviour where it could —
    "claude" / "gemini" / "grok" / "llama" names route to their canonical
    providers without explicit prefix.
    """
    # Already in pydantic-ai canonical form.
    if ":" in model:
        return model

    # LiteLLM-style "provider/model" prefix.
    if "/" in model:
        provider, name = model.split("/", 1)
        canonical = _PROVIDER_PREFIX_MAP.get(provider.lower(), provider.lower())
        return f"{canonical}:{name}"

    # Bare model name — infer provider from the name.
    lower = model.lower()
    if lower.startswith(("gpt", "o1", "o3", "text-")):
        return f"openai:{model}"
    if "claude" in lower:
        return f"anthropic:{model}"
    if "gemini" in lower:
        return f"google-gla:{model}"
    if "grok" in lower:
        return f"grok:{model}"
    if "llama" in lower:
        return f"openrouter:meta-llama/{model}"

    # Default — assume OpenAI-style.
    return f"openai:{model}"


def _strip_provider_prefix(model: str) -> str:
    """Strip vendor prefix from a model string.

    Used when routing through a custom OpenAI-compatible endpoint that
    expects bare model names (e.g., a LiteLLM proxy).
    """
    if ":" in model:
        return model.split(":", 1)[1]
    if "/" in model:
        return model.split("/", 1)[1]
    return model


# ---------------------------------------------------------------------------
# Message-list translation
# ---------------------------------------------------------------------------


def _split_messages(
    messages: list[dict[str, str]],
) -> tuple[list[str], list[ModelMessage], str]:
    """Split a Synapse-style message list into Pydantic AI components.

    Returns ``(system_prompts, history, user_prompt)`` where:
      * ``system_prompts`` — every system message's content, in order.
        Passed as ``Agent(system_prompt=...)``.
      * ``history`` — every user/assistant turn EXCEPT the final user
        message. Built as ``ModelMessage`` list for ``agent.run(message_history=...)``.
      * ``user_prompt`` — the final user message's content (the prompt
        actually being asked).

    Edge cases:
      * If the message list contains no user message (only system),
        the user_prompt is an empty string and Pydantic AI will rely on
        the system prompt alone — matches LiteLLM behaviour.
      * If the final message is an assistant turn (rare — partial
        completion), it goes into history and user_prompt is empty.
    """
    system_prompts: list[str] = []
    turns: list[tuple[str, str]] = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "") or ""
        if role == "system":
            system_prompts.append(content)
        elif role in ("user", "assistant"):
            turns.append((role, content))

    if not turns:
        return system_prompts, [], ""

    # Last user turn becomes the prompt; everything before is history.
    user_prompt = ""
    last_user_idx = None
    for idx in range(len(turns) - 1, -1, -1):
        if turns[idx][0] == "user":
            last_user_idx = idx
            user_prompt = turns[idx][1]
            break

    # If there's no user turn at all (assistant-only history, empty prompt),
    # keep every turn in history; otherwise everything before the last user
    # turn is history and the last user turn is the prompt.
    history_turns = turns if last_user_idx is None else turns[:last_user_idx]

    history: list[ModelMessage] = []
    for role, content in history_turns:
        if role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:  # assistant
            history.append(ModelResponse(parts=[TextPart(content=content)]))

    return system_prompts, history, user_prompt
