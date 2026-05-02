"""DSAR state machine — pending → approved → completed (or rejected).

Tests use AsyncMock for the DB session — same pattern as the rest of
the suite. The state machine itself is logic over ORM rows; the row
mutation is what we verify.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from synapse.db.models import DSARRequest, DSARStatus, DSARType
from synapse.dsar import state_machine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_request(
    *,
    status: DSARStatus = DSARStatus.pending,
    notes: str | None = None,
    request_type: DSARType = DSARType.erasure,
) -> MagicMock:
    req = MagicMock(spec=DSARRequest)
    req.id = uuid.uuid4()
    req.status = status
    req.notes = notes
    req.request_type = request_type
    req.tenant_id = None
    req.subject_principal = "user:alice"
    req.requested_by = "user:bob"
    req.reviewed_by = None
    req.reviewed_at = None
    req.completed_at = None
    req.certificate = None
    return req


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_inserts_pending_row():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    req = await state_machine.create(
        db,
        subject_principal="user:alice",
        request_type=DSARType.erasure,
        requested_by="user:bob",
    )

    assert req.subject_principal == "user:alice"
    assert req.request_type == DSARType.erasure
    assert req.requested_by == "user:bob"
    assert req.status == DSARStatus.pending
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# approve / reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_pending_to_approved():
    req = _mock_request(status=DSARStatus.pending)
    db = AsyncMock()
    db.get = AsyncMock(return_value=req)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = await state_machine.approve(db, req.id, "user:reviewer", notes="LGTM")

    assert result.status == DSARStatus.approved
    assert result.reviewed_by == "user:reviewer"
    assert result.reviewed_at is not None
    assert "LGTM" in (result.notes or "")


@pytest.mark.asyncio
async def test_reject_pending_to_rejected():
    req = _mock_request(status=DSARStatus.pending)
    db = AsyncMock()
    db.get = AsyncMock(return_value=req)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = await state_machine.reject(db, req.id, "user:reviewer", notes="duplicate")

    assert result.status == DSARStatus.rejected
    assert result.reviewed_by == "user:reviewer"
    assert "duplicate" in (result.notes or "")


@pytest.mark.asyncio
async def test_approve_appends_notes_does_not_overwrite():
    req = _mock_request(status=DSARStatus.pending, notes="initial context")
    db = AsyncMock()
    db.get = AsyncMock(return_value=req)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = await state_machine.approve(db, req.id, "user:reviewer", notes="approved")

    assert "initial context" in result.notes
    assert "approved" in result.notes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "starting_status",
    [DSARStatus.approved, DSARStatus.rejected, DSARStatus.completed],
)
async def test_approve_rejects_non_pending(starting_status):
    req = _mock_request(status=starting_status)
    db = AsyncMock()
    db.get = AsyncMock(return_value=req)

    with pytest.raises(state_machine.InvalidStatusTransition) as exc:
        await state_machine.approve(db, req.id, "user:reviewer")

    assert exc.value.actual == starting_status
    assert DSARStatus.pending in exc.value.expected


@pytest.mark.asyncio
async def test_approve_missing_request_raises_lookup_error():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    with pytest.raises(LookupError):
        await state_machine.approve(db, uuid.uuid4(), "user:reviewer")


# ---------------------------------------------------------------------------
# mark_completed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_completed_approved_to_completed_with_certificate():
    req = _mock_request(status=DSARStatus.approved)
    db = AsyncMock()
    db.get = AsyncMock(return_value=req)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    fake_cert = {"format": "x", "version": 1, "payload": {}, "signature": {}}
    result = await state_machine.mark_completed(db, req.id, "user:reviewer", certificate=fake_cert)

    assert result.status == DSARStatus.completed
    assert result.completed_at is not None
    assert result.certificate == fake_cert


@pytest.mark.asyncio
async def test_mark_completed_rejects_pending_request():
    req = _mock_request(status=DSARStatus.pending)
    db = AsyncMock()
    db.get = AsyncMock(return_value=req)

    with pytest.raises(state_machine.InvalidStatusTransition) as exc:
        await state_machine.mark_completed(db, req.id, "user:reviewer")

    assert exc.value.actual == DSARStatus.pending
    assert DSARStatus.approved in exc.value.expected


@pytest.mark.asyncio
async def test_mark_completed_does_not_overwrite_existing_reviewed_by():
    """If approve() already recorded the reviewer, complete() shouldn't
    silently rewrite that field — the certificate carries the
    completer; the row carries the original approver."""
    req = _mock_request(status=DSARStatus.approved)
    req.reviewed_by = "user:original-approver"

    db = AsyncMock()
    db.get = AsyncMock(return_value=req)
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    await state_machine.mark_completed(db, req.id, "user:different-completer")
    assert req.reviewed_by == "user:original-approver"
