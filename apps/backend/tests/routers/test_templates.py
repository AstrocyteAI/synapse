"""Tests for the /v1/templates router."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from synapse.main import create_app
from tests.conftest import TEST_SETTINGS


@pytest.fixture
def client():
    app = create_app()
    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as c,
    ):
        yield c


# ---------------------------------------------------------------------------
# GET /v1/templates
# ---------------------------------------------------------------------------


def test_list_templates_returns_all_builtins(client):
    resp = client.get("/v1/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = {t["id"] for t in data}
    assert ids == {
        "architecture-review",
        "code-review",
        "product-decision",
        "red-team",
        "security-audit",
        "solo",
    }


def test_list_templates_sorted_by_id(client):
    resp = client.get("/v1/templates")
    assert resp.status_code == 200
    ids = [t["id"] for t in resp.json()]
    assert ids == sorted(ids)


def test_list_templates_shape(client):
    resp = client.get("/v1/templates")
    assert resp.status_code == 200
    for tmpl in resp.json():
        assert "id" in tmpl
        assert "name" in tmpl
        assert "description" in tmpl
        assert "council_type" in tmpl
        assert "member_count" in tmpl
        assert tmpl["member_count"] >= 1


# ---------------------------------------------------------------------------
# GET /v1/templates/{template_id}
# ---------------------------------------------------------------------------


def test_get_template_returns_full_detail(client):
    resp = client.get("/v1/templates/solo")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "solo"
    assert "members" in data
    assert "chairman" in data
    assert len(data["members"]) >= 1
    assert data["chairman"].get("model_id")


def test_get_template_architecture_review(client):
    resp = client.get("/v1/templates/architecture-review")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "architecture-review"
    assert data["council_type"] == "llm"
    assert data["topic_tag"] == "architecture"
    assert len(data["members"]) == 3


def test_get_template_not_found(client):
    resp = client.get("/v1/templates/does-not-exist")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()
