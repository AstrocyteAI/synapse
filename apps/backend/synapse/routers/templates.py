"""Templates router — list and fetch council templates."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from synapse.templates.registry import TemplateDefinition, get_registry

router = APIRouter(tags=["templates"])

# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------


def _template_dict(t: TemplateDefinition) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "council_type": t.council_type,
        "topic_tag": t.topic_tag,
        "member_count": len(t.members),
        "config": t.config,
    }


# ---------------------------------------------------------------------------
# GET /v1/templates
# ---------------------------------------------------------------------------


@router.get(
    "/templates",
    summary="List all available council templates",
)
async def list_templates() -> list[dict]:
    """Return all registered templates sorted by id."""
    registry = get_registry()
    return [_template_dict(t) for t in registry.list_all()]


# ---------------------------------------------------------------------------
# GET /v1/templates/{template_id}
# ---------------------------------------------------------------------------


@router.get(
    "/templates/{template_id}",
    summary="Get a council template by ID",
)
async def get_template(template_id: str) -> dict:
    """Return a single resolved template including full member and chairman details."""
    registry = get_registry()
    tmpl = registry.get(template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "description": tmpl.description,
        "council_type": tmpl.council_type,
        "topic_tag": tmpl.topic_tag,
        "members": tmpl.members,
        "chairman": tmpl.chairman,
        "config": tmpl.config,
    }
