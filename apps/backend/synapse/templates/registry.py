"""Council template registry — load, inherit, and resolve built-in + custom templates.

Built-in templates live in ``synapse/templates/builtin/*.yaml``.
Custom templates can be registered at runtime via ``registry.register()``.

Inheritance is single-level (``extends: <parent_id>``).  The child's fields
override the parent's; ``config`` dicts are merged (child wins on conflict).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_logger = logging.getLogger(__name__)

_BUILTIN_DIR = Path(__file__).parent / "builtin"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class TemplateDefinition:
    id: str
    name: str
    description: str
    members: list[dict[str, Any]]
    chairman: dict[str, Any]
    council_type: str = "llm"
    topic_tag: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    extends: str | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TemplateRegistry:
    """Lazy-loading registry for council templates."""

    def __init__(self) -> None:
        self._templates: dict[str, TemplateDefinition] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        for yaml_path in sorted(_BUILTIN_DIR.glob("*.yaml")):
            try:
                data = yaml.safe_load(yaml_path.read_text())
                tmpl = TemplateDefinition(
                    id=data["id"],
                    name=data["name"],
                    description=data.get("description", ""),
                    members=data.get("members", []),
                    chairman=data.get("chairman", {}),
                    council_type=data.get("council_type", "llm"),
                    topic_tag=data.get("topic_tag"),
                    config=data.get("config", {}),
                    extends=data.get("extends"),
                )
                self._templates[tmpl.id] = tmpl
            except Exception:
                _logger.warning("Failed to load template %s", yaml_path, exc_info=True)
        self._loaded = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, template: TemplateDefinition) -> None:
        """Register a custom template (or override a built-in)."""
        self._ensure_loaded()
        self._templates[template.id] = template

    def get(self, template_id: str) -> TemplateDefinition | None:
        """Return the resolved template (inheritance applied), or None."""
        self._ensure_loaded()
        tmpl = self._templates.get(template_id)
        if tmpl is None:
            return None
        if not tmpl.extends:
            return tmpl
        parent = self._templates.get(tmpl.extends)
        if parent is None:
            _logger.warning("Template %s extends unknown parent %s", tmpl.id, tmpl.extends)
            return tmpl
        return TemplateDefinition(
            id=tmpl.id,
            name=tmpl.name,
            description=tmpl.description or parent.description,
            members=tmpl.members if tmpl.members else parent.members,
            chairman=tmpl.chairman if tmpl.chairman else parent.chairman,
            council_type=tmpl.council_type or parent.council_type,
            topic_tag=tmpl.topic_tag or parent.topic_tag,
            config={**parent.config, **tmpl.config},
            extends=None,
        )

    def list_all(self) -> list[TemplateDefinition]:
        """Return all templates (resolved), sorted by id."""
        self._ensure_loaded()
        return sorted(
            (self.get(tid) for tid in self._templates),  # type: ignore[misc]
            key=lambda t: t.id,
        )

    def exists(self, template_id: str) -> bool:
        self._ensure_loaded()
        return template_id in self._templates


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry = TemplateRegistry()


def get_registry() -> TemplateRegistry:
    return _registry
