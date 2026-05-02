"""DSAR erasure worker — Synapse-side cleanup + Astrocyte forget.

Tests cover the action-record shape (every action declares system,
status, timestamps), the no-op path for non-erasure requests, and the
three Astrocyte response paths: success, ``astrocyte_pending``
(NotImplementedError), and hard ``failed``.

The Synapse-side actions delegate to SQL ``delete`` / ``update``
statements; we mock ``db.execute`` so the action shape is verifiable
without standing up a real Postgres.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from synapse.db.models import DSARRequest, DSARStatus, DSARType
from synapse.dsar import worker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _request(*, request_type: DSARType = DSARType.erasure) -> MagicMock:
    req = MagicMock(spec=DSARRequest)
    req.id = uuid.uuid4()
    req.subject_principal = "user:alice"
    req.tenant_id = None
    req.request_type = request_type
    req.status = DSARStatus.approved
    from datetime import UTC, datetime

    req.requested_at = datetime.now(UTC)
    return req


def _ok_db(rowcount: int = 0):
    """AsyncMock db whose execute() returns a result with `.rowcount`
    and `.scalars().all()`."""
    db = AsyncMock()
    result = MagicMock()
    result.rowcount = rowcount
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[])
    result.scalars = MagicMock(return_value=scalars)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _ok_astrocyte(body: dict | None = None):
    astro = MagicMock()
    astro.forget_principal = AsyncMock(
        return_value=body or {"banks_processed": 1, "memories_deleted": 0, "details": []}
    )
    return astro


# ---------------------------------------------------------------------------
# Non-erasure types yield a single no_op action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_access_request_yields_single_no_op_action():
    req = _request(request_type=DSARType.access)
    actions = await worker.run_erasure(_ok_db(), request=req, astrocyte=_ok_astrocyte())

    assert len(actions) == 1
    assert actions[0]["action"] == "no_op"
    assert actions[0]["request_type"] == "access"


@pytest.mark.asyncio
async def test_rectification_request_yields_single_no_op_action():
    req = _request(request_type=DSARType.rectification)
    actions = await worker.run_erasure(_ok_db(), request=req, astrocyte=_ok_astrocyte())

    assert actions[0]["action"] == "no_op"
    assert actions[0]["request_type"] == "rectification"


# ---------------------------------------------------------------------------
# Erasure happy path — six actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_erasure_runs_all_six_actions_with_status_completed():
    req = _request()
    db = _ok_db(rowcount=3)
    astro = _ok_astrocyte()

    actions = await worker.run_erasure(db, request=req, astrocyte=astro)

    # 5 Synapse-side actions + 1 Astrocyte action
    assert len(actions) == 6
    expected_actions = {
        "synapse_audit_events",
        "synapse_council_members",
        "synapse_notification_prefs",
        "synapse_device_tokens",
        "synapse_api_keys",
        "astrocyte_forget_principal",
    }
    assert {a["action"] for a in actions} == expected_actions

    # Every action has a status; every Synapse action carries a system
    # tag and timestamps
    for a in actions:
        assert a.get("status") in {"completed", "astrocyte_pending", "failed"}
        assert "started_at" in a
        if a["system"] == "synapse":
            assert "completed_at" in a or "failed_at" in a


# ---------------------------------------------------------------------------
# Astrocyte response paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_astrocyte_success_path_records_completed():
    req = _request()
    astro = _ok_astrocyte({"banks_processed": 2, "memories_deleted": 7, "details": []})

    actions = await worker.run_erasure(_ok_db(), request=req, astrocyte=astro)
    astro_action = next(a for a in actions if a["action"] == "astrocyte_forget_principal")

    assert astro_action["status"] == "completed"
    assert astro_action["result"]["banks_processed"] == 2
    assert astro_action["result"]["memories_deleted"] == 7
    astro.forget_principal.assert_awaited_once()
    # The principal we sent must be the subject of the request
    kwargs = astro.forget_principal.await_args.kwargs
    assert kwargs["principal"] == "user:alice"


@pytest.mark.asyncio
async def test_astrocyte_404_records_astrocyte_pending(caplog):
    req = _request()
    astro = MagicMock()
    astro.forget_principal = AsyncMock(side_effect=NotImplementedError("404 from gateway"))

    actions = await worker.run_erasure(_ok_db(), request=req, astrocyte=astro)
    astro_action = next(a for a in actions if a["action"] == "astrocyte_forget_principal")

    # Note: the worker logs at warning, not error — image lag is
    # operational, not a bug. Assert the status, not the log level.
    assert astro_action["status"] == "astrocyte_pending"
    assert "Astrocyte" in astro_action["note"]


@pytest.mark.asyncio
async def test_astrocyte_hard_failure_records_failed(caplog):
    req = _request()
    astro = MagicMock()
    astro.forget_principal = AsyncMock(side_effect=RuntimeError("connection refused"))

    actions = await worker.run_erasure(_ok_db(), request=req, astrocyte=astro)
    astro_action = next(a for a in actions if a["action"] == "astrocyte_forget_principal")

    assert astro_action["status"] == "failed"
    assert "connection refused" in astro_action["error"]


# ---------------------------------------------------------------------------
# Council member stripping — the only Synapse action with non-trivial
# logic (the others are SQL deletes / updates).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_council_member_action_strips_subject_and_anonymises_creator():
    """Subject is in members[0] and is the council's creator."""
    req = _request()
    req.subject_principal = "user:alice"

    council = MagicMock()
    council.members = [
        {"principal": "user:alice", "name": "Alice"},
        {"principal": "user:bob", "name": "Bob"},
    ]
    council.created_by = "user:alice"
    council.tenant_id = None

    db = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=[council])
    result.scalars = MagicMock(return_value=scalars)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    # Drive only the council action — call run_erasure but use a stub
    # that returns no rows for the other queries
    astro = _ok_astrocyte()
    actions = await worker.run_erasure(db, request=req, astrocyte=astro)
    council_action = next(a for a in actions if a["action"] == "synapse_council_members")

    assert council_action["status"] == "completed"
    assert council_action["councils_touched"] >= 1
    assert council_action["member_entries_removed"] == 1
    # The actual mutation
    assert council.members == [{"principal": "user:bob", "name": "Bob"}]
    assert council.created_by == "user:erased"


# ---------------------------------------------------------------------------
# build_certificate_payload
# ---------------------------------------------------------------------------


def test_build_certificate_payload_carries_request_fields_and_actions():
    req = _request()
    payload = worker.build_certificate_payload(
        req,
        completed_by="user:reviewer",
        actions=[{"system": "synapse", "action": "x", "status": "completed"}],
    )

    assert payload["request_id"] == str(req.id)
    assert payload["subject_principal"] == "user:alice"
    assert payload["request_type"] == "erasure"
    assert payload["completed_by"] == "user:reviewer"
    assert payload["actions"] == [{"system": "synapse", "action": "x", "status": "completed"}]
    # ISO timestamps for both anchors
    assert "T" in payload["completed_at"]
    assert "T" in payload["requested_at"]
