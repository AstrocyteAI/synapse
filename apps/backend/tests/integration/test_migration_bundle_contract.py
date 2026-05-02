"""End-to-end contract test for the Synapse → Cerebro migration bundle.

This test exercises the *Synapse half* of the cross-backend migration
flow:

  1. Stand up a respx-mocked Synapse REST API (the export tool reads via
     the public API, never the database).
  2. Run `synapse.scripts.migrate_export.export()` against it.
  3. Validate the produced `bundle.json` against the shared JSON schema
     committed at `synapse/contracts/migration-bundle-v1.schema.json`.
  4. Spot-check fields the Cerebro importer relies on.

The matching Cerebro half lives at
`cerebro/apps/backend/test/synapse/migration_bundle_contract_test.exs`
and uses the SAME schema. If either side drifts, exactly one of the two
tests fails — and the failure tells you which side broke the contract.

The full docker-compose CI version (real Synapse + real Cerebro + real
Astrocyte, subprocess `migrate_export` → HTTP POST → DB assertion) is
tracked as a follow-up. This contract test catches the highest-leverage
regression (wire-shape drift) without the operational cost.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import jsonschema
import pytest
import respx

from synapse.scripts import migrate_export

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "synapse"
    / "contracts"
    / "migration-bundle-v1.schema.json"
)


@pytest.fixture
def bundle_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


@pytest.fixture
def synapse_base_url() -> str:
    return "http://synapse-mock"


@pytest.fixture
def admin_token() -> str:
    return "test-admin-jwt"


def _council(session_id: str, status: str = "closed") -> dict:
    return {
        "session_id": session_id,
        "question": "Should we migrate to Cerebro?",
        "status": status,
        "council_type": "llm",
        "members": [{"model_id": "openai/gpt-4o", "name": "GPT-4o"}],
        "chairman": {"model_id": "anthropic/claude-opus-4-5", "name": "Chair"},
        "verdict": "Yes — migrate.",
        "consensus_score": 0.92,
        "confidence_label": "high",
        "dissent_detected": False,
        "topic_tag": "infrastructure",
        "created_by": "user:alice",
        "created_at": "2026-04-01T10:00:00Z",
        "closed_at": "2026-04-01T10:05:00Z",
        "tenant_id": "synapse-source-tenant",
    }


def _audit_event(seq: int) -> dict:
    return {
        "id": seq,
        "event_type": "council.created",
        "actor_principal": "user:alice",
        "tenant_id": "synapse-source-tenant",
        "resource_type": "council",
        "resource_id": f"cncl_{seq}",
        "metadata": {"role": "admin"},
        "created_at": "2026-04-01T10:00:00Z",
    }


@respx.mock
def test_export_produces_schema_valid_bundle(
    tmp_path: Path,
    bundle_schema: dict,
    synapse_base_url: str,
    admin_token: str,
):
    """Happy path: export against a healthy mocked Synapse → schema-valid bundle."""

    # /v1/info — the export tool refuses to run unless this reports backend=synapse.
    respx.get(f"{synapse_base_url}/v1/info").mock(
        return_value=httpx.Response(200, json={"backend": "synapse", "version": "0.1.0"})
    )

    # /v1/councils — paginated. Return a small page on the first call, then empty.
    councils_page_1 = [
        _council("11111111-1111-1111-1111-111111111111"),
        _council("22222222-2222-2222-2222-222222222222", status="pending_approval"),
    ]
    respx.get(f"{synapse_base_url}/v1/councils").mock(
        side_effect=[
            httpx.Response(200, json={"data": councils_page_1}),
            httpx.Response(200, json={"data": []}),
        ]
    )

    # /v1/admin/audit-log — cursor paginated; return one page then nil cursor.
    respx.get(f"{synapse_base_url}/v1/admin/audit-log").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [_audit_event(1), _audit_event(2)],
                "next_before_id": None,
            },
        )
    )

    output = tmp_path / "dump"
    counts = migrate_export.export(synapse_base_url, admin_token, output)

    # Sanity on the Python return value
    assert counts["councils.jsonl"] == 2
    assert counts["audit_events.jsonl"] == 2

    # The bundle.json is the wire artifact Cerebro consumes — validate against schema
    bundle = json.loads((output / "bundle.json").read_text())
    jsonschema.validate(bundle, bundle_schema)

    # Spot-check the contract fields the Cerebro importer relies on
    assert bundle["manifest"]["format_version"] == 1
    assert bundle["manifest"]["source_backend"]["backend"] == "synapse"
    assert len(bundle["councils"]) == 2
    assert {c["session_id"] for c in bundle["councils"]} == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    }
    # Status mapping is the Cerebro side's responsibility — but the source
    # status MUST be present so the importer can map it.
    assert all("status" in c for c in bundle["councils"])


@respx.mock
def test_export_refuses_when_backend_is_not_synapse(
    tmp_path: Path, synapse_base_url: str, admin_token: str
):
    """The export tool's first action is `/v1/info`; if the backend is not
    Synapse it bails out instead of producing a bogus bundle. This is the
    safety check that keeps an operator from accidentally exporting from
    Cerebro into a Synapse-shaped bundle."""

    respx.get(f"{synapse_base_url}/v1/info").mock(
        return_value=httpx.Response(200, json={"backend": "cerebro", "version": "0.1.0"})
    )

    output = tmp_path / "dump"
    with pytest.raises(SystemExit, match="backend"):
        migrate_export.export(synapse_base_url, admin_token, output)


@respx.mock
def test_export_with_empty_synapse_produces_minimal_valid_bundle(
    tmp_path: Path,
    bundle_schema: dict,
    synapse_base_url: str,
    admin_token: str,
):
    """A brand-new Synapse with no councils still produces a schema-valid
    bundle (manifest only) — the importer should accept it as a no-op."""

    respx.get(f"{synapse_base_url}/v1/info").mock(
        return_value=httpx.Response(200, json={"backend": "synapse", "version": "0.1.0"})
    )
    respx.get(f"{synapse_base_url}/v1/councils").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
    respx.get(f"{synapse_base_url}/v1/admin/audit-log").mock(
        return_value=httpx.Response(200, json={"data": [], "next_before_id": None})
    )

    output = tmp_path / "dump"
    migrate_export.export(synapse_base_url, admin_token, output)

    bundle = json.loads((output / "bundle.json").read_text())
    jsonschema.validate(bundle, bundle_schema)
    assert bundle["councils"] == []
