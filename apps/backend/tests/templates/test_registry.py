"""Unit tests for the template registry."""

from __future__ import annotations

from synapse.templates.registry import TemplateDefinition, TemplateRegistry, get_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MEMBER = {"model_id": "openai/gpt-4o", "name": "Test Member", "role": "Think hard."}
_CHAIRMAN = {"model_id": "anthropic/claude-3-7-sonnet-20250219", "name": "Chair", "role": "Decide."}


def _make_tmpl(tid: str, *, extends: str | None = None) -> TemplateDefinition:
    return TemplateDefinition(
        id=tid,
        name=f"Template {tid}",
        description=f"Desc {tid}",
        members=[_MEMBER],
        chairman=_CHAIRMAN,
        council_type="llm",
        topic_tag="test",
        config={"k": tid},
        extends=extends,
    )


# ---------------------------------------------------------------------------
# Built-in loading
# ---------------------------------------------------------------------------


def test_builtin_templates_load():
    """get_registry() must expose the 6 built-in YAML templates."""
    registry = get_registry()
    ids = {t.id for t in registry.list_all()}
    assert ids == {
        "architecture-review",
        "code-review",
        "product-decision",
        "red-team",
        "security-audit",
        "solo",
    }


def test_builtin_templates_have_required_fields():
    registry = get_registry()
    for tmpl in registry.list_all():
        assert tmpl.id
        assert tmpl.name
        assert tmpl.description
        assert len(tmpl.members) >= 1, f"{tmpl.id}: no members"
        assert tmpl.chairman, f"{tmpl.id}: no chairman"
        assert tmpl.chairman.get("model_id"), f"{tmpl.id}: chairman missing model_id"


def test_list_all_sorted():
    registry = get_registry()
    ids = [t.id for t in registry.list_all()]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Registry CRUD
# ---------------------------------------------------------------------------


def test_register_and_get():
    registry = TemplateRegistry()
    tmpl = _make_tmpl("custom-one")
    registry.register(tmpl)
    result = registry.get("custom-one")
    assert result is not None
    assert result.id == "custom-one"


def test_get_unknown_returns_none():
    registry = TemplateRegistry()
    assert registry.get("does-not-exist") is None


def test_exists():
    registry = TemplateRegistry()
    registry.register(_make_tmpl("exists-yes"))
    assert registry.exists("exists-yes")
    assert not registry.exists("exists-no")


def test_register_overrides_builtin():
    registry = get_registry()
    original = registry.get("solo")
    assert original is not None

    override = TemplateDefinition(
        id="solo",
        name="Custom Solo",
        description="Overridden",
        members=[_MEMBER],
        chairman=_CHAIRMAN,
    )
    registry.register(override)
    result = registry.get("solo")
    assert result is not None
    assert result.name == "Custom Solo"

    # Restore original for other tests
    registry.register(original)


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


def test_inheritance_child_overrides_parent():
    registry = TemplateRegistry()
    parent = _make_tmpl("parent")
    child = TemplateDefinition(
        id="child",
        name="Child",
        description="Child desc",
        members=[],  # empty — should fall back to parent
        chairman={},  # empty — should fall back to parent
        config={"k": "child-value", "extra": "yes"},
        extends="parent",
    )
    registry.register(parent)
    registry.register(child)

    resolved = registry.get("child")
    assert resolved is not None
    assert resolved.id == "child"
    assert resolved.name == "Child"
    # members/chairman fall back to parent when empty
    assert resolved.members == parent.members
    assert resolved.chairman == parent.chairman
    # config merged: child wins on conflict, parent value kept for missing keys
    assert resolved.config["k"] == "child-value"
    assert resolved.config["extra"] == "yes"
    # extends cleared after resolution
    assert resolved.extends is None


def test_inheritance_child_members_override_parent():
    registry = TemplateRegistry()
    parent = _make_tmpl("parent2")
    child_member = {"model_id": "openai/gpt-4o-mini", "name": "Mini", "role": "Small."}
    child = TemplateDefinition(
        id="child2",
        name="Child2",
        description="",
        members=[child_member],
        chairman={},
        extends="parent2",
    )
    registry.register(parent)
    registry.register(child)

    resolved = registry.get("child2")
    assert resolved is not None
    assert resolved.members == [child_member]


def test_inheritance_unknown_parent_returns_child():
    registry = TemplateRegistry()
    child = _make_tmpl("orphan", extends="ghost-parent")
    registry.register(child)
    resolved = registry.get("orphan")
    assert resolved is not None
    assert resolved.id == "orphan"
