"""X-1 — response shape parity with the OpenAPI contract.

Validates that actual responses from public endpoints conform to the schemas
declared in `synapse-v1.openapi.json`. This is the Synapse half of the X-1
parity test pair — Cerebro has a mirror version (`contract_parity_test.exs`)
that runs the same checks against its own implementation.

When both backends pass these tests, clients written against the contract
work against either backend without surprise.

Currently covers /v1/info as the canonical case. Add new endpoints here as
they ship in both backends.
"""

from __future__ import annotations

from unittest.mock import patch

import jsonschema
import pytest
from fastapi.testclient import TestClient

from synapse.main import create_app
from synapse.openapi_contract import load_contract
from tests.conftest import TEST_SETTINGS


@pytest.fixture
def contract():
    return load_contract()


def _get(path: str) -> dict:
    """Hit the backend with a fresh app + TestClient and return JSON."""
    app = create_app()
    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(app, raise_server_exceptions=True) as c,
    ):
        return c.get(path).json()


def _schema_for(contract: dict, path: str, method: str, status: str) -> dict:
    """Resolve the response schema for `path`+`method`+`status` from the contract."""
    op = contract["paths"][path][method]
    response = op["responses"][status]
    schema = response["content"]["application/json"]["schema"]
    # If the schema is a $ref, resolve it
    if "$ref" in schema:
        ref_name = schema["$ref"].rsplit("/", 1)[-1]
        return contract["components"]["schemas"][ref_name]
    return schema


def _build_resolver(contract: dict) -> jsonschema.RefResolver:
    """Lets schemas reference each other via #/components/schemas/..."""
    return jsonschema.RefResolver.from_schema(contract)


# ---------------------------------------------------------------------------
# /v1/info
# ---------------------------------------------------------------------------


def test_info_response_conforms_to_BackendInfo_schema(contract):
    """The /v1/info response must validate against the BackendInfo schema."""
    body = _get("/v1/info")
    schema = _schema_for(contract, "/v1/info", "get", "200")
    resolver = _build_resolver(contract)
    jsonschema.validate(body, schema, resolver=resolver)


def test_info_response_has_no_extra_top_level_fields(contract):
    """Catch fields that drift in without being declared in the contract.

    We don't enforce additionalProperties=false in the schema (it's noisy and
    hostile to extension), but we DO check that production responses don't
    accidentally leak internal fields.
    """
    body = _get("/v1/info")
    schema = _schema_for(contract, "/v1/info", "get", "200")

    declared = set(schema["properties"].keys())
    actual = set(body.keys())
    extra = actual - declared
    assert not extra, (
        f"/v1/info returned undeclared fields: {extra}. Either add them to "
        f"the BackendInfo schema or stop returning them."
    )


def test_info_features_object_matches_declared_keys(contract):
    """The features sub-object's keys are the X-1 contract — both backends
    must return the same key set."""
    body = _get("/v1/info")
    schema = _schema_for(contract, "/v1/info", "get", "200")

    declared_features = set(schema["properties"]["features"]["properties"].keys())
    actual_features = set(body["features"].keys())
    assert declared_features == actual_features, (
        f"features keys drifted from contract.\n"
        f"  Declared: {sorted(declared_features)}\n"
        f"  Actual:   {sorted(actual_features)}"
    )
