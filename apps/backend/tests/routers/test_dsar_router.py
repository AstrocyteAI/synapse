"""POST /v1/dsar + lifecycle endpoint tests.

Same TestClient + AsyncMock pattern as the rest of the routers suite.
The router stitches together state_machine + worker + certificate;
the deeper unit-level assertions live in the per-module test files.
This file focuses on the wire shape: status codes, auth gating, and
the 503 fail-closed when the signing secret isn't configured.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import DSARRequest, DSARStatus, DSARType
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# App fixture — same shape as the other router test files. The DSAR
# signing secret is set on TEST_SETTINGS in conftest.py so this fixture
# stays minimal; the explicit-no-secret 503 test uses its own fixture
# that wipes the field.
# ---------------------------------------------------------------------------


@pytest.fixture
def _wired_client(mock_astrocyte, mock_centrifugo, mock_llm):
    application = create_app()
    mock_session = AsyncMock()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sessionmaker.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
        TestClient(application, raise_server_exceptions=False) as c,
    ):
        application.state.astrocyte = mock_astrocyte
        application.state.centrifugo = mock_centrifugo
        application.state.sessionmaker = mock_sessionmaker
        yield c, mock_session, application


@pytest.fixture
def client(_wired_client):
    c, _, _ = _wired_client
    return c


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {make_jwt(roles=['admin'])}"}


@pytest.fixture
def member_headers():
    return {"Authorization": f"Bearer {make_jwt(roles=['member'])}"}


def _make_dsar_row(
    *,
    status: DSARStatus = DSARStatus.pending,
    request_type: DSARType = DSARType.erasure,
) -> MagicMock:
    row = MagicMock(spec=DSARRequest)
    row.id = uuid.uuid4()
    row.tenant_id = "tenant-test"
    row.subject_principal = "user:alice"
    row.request_type = request_type
    row.reason = "GDPR Art. 17"
    row.status = status
    row.notes = None
    row.requested_by = "user:bob"
    row.requested_at = datetime.now(UTC)
    row.reviewed_by = None
    row.reviewed_at = None
    row.completed_at = None
    row.certificate = None
    return row


# ---------------------------------------------------------------------------
# POST /v1/dsar — anyone can file
# ---------------------------------------------------------------------------


def test_create_returns_201_for_member(client, member_headers):
    new_row = _make_dsar_row()
    with patch(
        "synapse.routers.dsar.state_machine.create",
        new=AsyncMock(return_value=new_row),
    ):
        resp = client.post(
            "/v1/dsar",
            json={
                "subject_principal": "user:alice",
                "request_type": "erasure",
                "reason": "GDPR Art. 17",
            },
            headers=member_headers,
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["subject_principal"] == "user:alice"
    assert body["request_type"] == "erasure"
    assert body["status"] == "pending"


def test_create_requires_auth(client):
    resp = client.post(
        "/v1/dsar",
        json={"subject_principal": "user:alice", "request_type": "erasure"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /v1/dsar — admin only
# ---------------------------------------------------------------------------


def test_list_rejects_non_admin(client, member_headers):
    resp = client.get("/v1/dsar", headers=member_headers)
    assert resp.status_code == 403


def test_list_returns_rows_for_admin(client, admin_headers):
    rows = [_make_dsar_row(), _make_dsar_row(status=DSARStatus.approved)]
    with patch(
        "synapse.routers.dsar.state_machine.list_requests",
        new=AsyncMock(return_value=rows),
    ):
        resp = client.get("/v1/dsar", headers=admin_headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2


def test_list_rejects_unknown_status_filter(client, admin_headers):
    resp = client.get("/v1/dsar?status=banana", headers=admin_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Lifecycle — approve / reject / complete
# ---------------------------------------------------------------------------


def test_approve_returns_200_and_advances_status(client, admin_headers):
    approved = _make_dsar_row(status=DSARStatus.approved)
    with patch(
        "synapse.routers.dsar.state_machine.approve",
        new=AsyncMock(return_value=approved),
    ):
        resp = client.patch(
            f"/v1/dsar/{approved.id}/approve",
            json={"notes": "verified subject"},
            headers=admin_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


def test_approve_rejects_non_admin(client, member_headers):
    resp = client.patch(
        f"/v1/dsar/{uuid.uuid4()}/approve",
        json={},
        headers=member_headers,
    )
    assert resp.status_code == 403


def test_approve_returns_409_on_invalid_transition(client, admin_headers):
    """A request already in ``rejected`` cannot be approved."""
    from synapse.dsar.state_machine import InvalidStatusTransition

    with patch(
        "synapse.routers.dsar.state_machine.approve",
        new=AsyncMock(
            side_effect=InvalidStatusTransition(
                expected=DSARStatus.pending, actual=DSARStatus.rejected
            )
        ),
    ):
        resp = client.patch(
            f"/v1/dsar/{uuid.uuid4()}/approve",
            json={},
            headers=admin_headers,
        )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid_status_transition"
    assert detail["actual"] == "rejected"


def test_reject_returns_200_and_records_terminal_status(client, admin_headers):
    rejected = _make_dsar_row(status=DSARStatus.rejected)
    with patch(
        "synapse.routers.dsar.state_machine.reject",
        new=AsyncMock(return_value=rejected),
    ):
        resp = client.patch(
            f"/v1/dsar/{rejected.id}/reject",
            json={"notes": "duplicate of #123"},
            headers=admin_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_complete_returns_200_with_signed_certificate(client, admin_headers):
    approved = _make_dsar_row(status=DSARStatus.approved)
    completed = _make_dsar_row(status=DSARStatus.completed)
    completed.id = approved.id
    completed.certificate = {
        "format": "synapse-dsar-cert-v1",
        "version": 1,
        "payload": {"actions": []},
        "signature": {"alg": "HMAC-SHA256", "value": "deadbeef"},
    }

    with (
        patch(
            "synapse.routers.dsar.state_machine.get",
            new=AsyncMock(return_value=approved),
        ),
        patch(
            "synapse.routers.dsar.worker.run_erasure",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "synapse.routers.dsar.state_machine.mark_completed",
            new=AsyncMock(return_value=completed),
        ),
    ):
        resp = client.patch(
            f"/v1/dsar/{approved.id}/complete",
            headers=admin_headers,
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["certificate"]["format"] == "synapse-dsar-cert-v1"


def test_complete_returns_409_when_not_yet_approved(client, admin_headers):
    pending = _make_dsar_row(status=DSARStatus.pending)
    with patch(
        "synapse.routers.dsar.state_machine.get",
        new=AsyncMock(return_value=pending),
    ):
        resp = client.patch(
            f"/v1/dsar/{pending.id}/complete",
            headers=admin_headers,
        )

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid_status_transition"


def test_complete_returns_404_when_request_missing(client, admin_headers):
    with patch(
        "synapse.routers.dsar.state_machine.get",
        new=AsyncMock(return_value=None),
    ):
        resp = client.patch(
            f"/v1/dsar/{uuid.uuid4()}/complete",
            headers=admin_headers,
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 503 fail-closed when signing secret is missing
# ---------------------------------------------------------------------------


def test_complete_returns_503_when_signing_secret_unset(client, admin_headers):
    """Without a signing secret, the router refuses to complete a
    request — operators must set ``synapse_dsar_signing_secret`` before
    issuing certificates.

    The fixture's ``application.state.settings`` is the global
    TEST_SETTINGS (with the secret pre-populated); we wipe the field
    in-place for this test only. ``model_copy`` is avoided because
    Pydantic's copy seems to interact badly with the FastAPI lifespan
    in this codebase — see the conftest.py override pattern.
    """
    # The router reads the secret from request.app.state.settings; wipe
    # the field for the duration of this test and restore on exit.
    settings = client.app.state.settings
    original_secret = settings.synapse_dsar_signing_secret
    object.__setattr__(settings, "synapse_dsar_signing_secret", "")
    try:
        resp = client.patch(
            f"/v1/dsar/{uuid.uuid4()}/complete",
            headers=admin_headers,
        )
    finally:
        object.__setattr__(settings, "synapse_dsar_signing_secret", original_secret)

    assert resp.status_code == 503
    assert "signing_secret" in resp.json()["detail"]
