"""LLM client — wraps LiteLLM for uniform multi-model access."""

from __future__ import annotations

import logging
from typing import Any

import litellm

from synapse.config import Settings

_logger = logging.getLogger(__name__)

# Suppress LiteLLM's verbose logging in production
litellm.suppress_debug_info = True


def _configure_litellm(settings: Settings) -> None:
    """Apply LiteLLM global config from settings."""
    if settings.litellm_api_base:
        litellm.api_base = settings.litellm_api_base
    if settings.litellm_api_key:
        litellm.api_key = settings.litellm_api_key


class LLMClient:
    """Async LLM client backed by LiteLLM."""

    def __init__(self, settings: Settings) -> None:
        _configure_litellm(settings)
        self._settings = settings

    async def complete(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> str:
        """Call a model and return the response text."""
        response = await litellm.acompletion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError(f"Model {model} returned empty response")
        return content


def derive_display_name(model_id: str) -> str:
    """Derive a readable display name from a model ID when no name is provided."""
    lower = model_id.lower()
    # Strip provider prefix if present (e.g. "anthropic/claude-..." -> "claude-...")
    if "/" in lower:
        lower = lower.split("/", 1)[1]

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
