"""Tests for POST /v1/councils/{id}/contribute and the quorum/session helpers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.council.session import quorum_met
from synapse.db.models import CouncilSession, CouncilStatus
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# App fixture — same pattern as test_councils.py
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
        yield c, mock_session


@pytest.fixture
def client(_wired_client):
    c, _ = _wired_client
    return c


@pytest.fixture
def db_session(_wired_client):
    _, session = _wired_client
    return session


@pytest.fixture
def token():
    return make_jwt(sub="user-1", tenant_id="tenant-test")


@pytest.fixture
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_BODY = {
    "member_id": "user:alice",
    "member_name": "Alice",
    "content": "I think we should proceed with option B.",
}


def _make_async_council(
    *,
    status: CouncilStatus = CouncilStatus.waiting_contributions,
    contributions: list | None = None,
    quorum: int | None = None,
    members: list | None = None,
    session_id: uuid.UUID | None = None,
) -> MagicMock:
    obj = MagicMock(spec=CouncilSession)
    obj.id = session_id or uuid.uuid4()
    obj.status = status
    obj.contributions = contributions if contributions is not None else []
    obj.quorum = quorum
    obj.members = members or [
        {"model_id": "openai/gpt-4o", "name": "GPT"},
        {"model_id": "anthropic/claude-3-5", "name": "Claude"},
    ]
    obj.tenant_id = "tenant-test"
    return obj


# ---------------------------------------------------------------------------
# Unit: quorum_met
# ---------------------------------------------------------------------------


def test_quorum_met_explicit_quorum_not_reached():
    council = _make_async_council(quorum=3, contributions=[{}, {}])
    assert quorum_met(council) is False


def test_quorum_met_explicit_quorum_reached_exactly():
    council = _make_async_council(quorum=2, contributions=[{}, {}])
    assert quorum_met(council) is True


def test_quorum_met_explicit_quorum_exceeded():
    council = _make_async_council(quorum=2, contributions=[{}, {}, {}])
    assert quorum_met(council) is True


def test_quorum_met_defaults_to_member_count_not_reached():
    # 2 members, 1 contribution — not met
    council = _make_async_council(quorum=None, contributions=[{}])
    assert quorum_met(council) is False


def test_quorum_met_defaults_to_member_count_reached():
    # 2 members, 2 contributions — met
    council = _make_async_council(quorum=None, contributions=[{}, {}])
    assert quorum_met(council) is True


def test_quorum_met_single_member_single_contribution():
    council = _make_async_council(
        quorum=None,
        members=[{"model_id": "openai/gpt-4o"}],
        contributions=[{}],
    )
    assert quorum_met(council) is True


def test_quorum_met_no_contributions_never_met():
    council = _make_async_council(quorum=1, contributions=[])
    assert quorum_met(council) is False


# ---------------------------------------------------------------------------
# Unit: add_contribution (session layer)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_contribution_appends_entry():
    from synapse.council.models import ContributeRequest
    from synapse.council.session import add_contribution

    session_id = uuid.uuid4()
    existing = _make_async_council(session_id=session_id, contributions=[])

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=existing)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    body = ContributeRequest(member_id="user:bob", member_name="Bob", content="My view.")
    result = await add_contribution(mock_db, session_id, body, member_type="human")

    # The new entry must be appended
    assert len(result.contributions) == 1
    entry = result.contributions[0]
    assert entry["member_id"] == "user:bob"
    assert entry["member_name"] == "Bob"
    assert entry["content"] == "My view."
    assert entry["member_type"] == "human"
    assert "submitted_at" in entry
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_contribution_raises_on_missing_session():
    from synapse.council.models import ContributeRequest
    from synapse.council.session import add_contribution

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)

    body = ContributeRequest(member_id="user:x", member_name="X", content=".")
    with pytest.raises(ValueError, match="not found"):
        await add_contribution(mock_db, uuid.uuid4(), body)


# ---------------------------------------------------------------------------
# POST /v1/councils/{id}/contribute — auth + validation
# ---------------------------------------------------------------------------


def test_contribute_requires_auth(client):
    resp = client.post(f"/v1/councils/{uuid.uuid4()}/contribute", json=_VALID_BODY)
    assert resp.status_code == 401


def test_contribute_validates_missing_member_id(client, headers):
    resp = client.post(
        f"/v1/councils/{uuid.uuid4()}/contribute",
        json={"member_name": "Alice", "content": "Hello"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_contribute_validates_missing_content(client, headers):
    resp = client.post(
        f"/v1/councils/{uuid.uuid4()}/contribute",
        json={"member_id": "user:alice", "member_name": "Alice"},
        headers=headers,
    )
    assert resp.status_code == 422


def test_contribute_validates_missing_member_name(client, headers):
    resp = client.post(
        f"/v1/councils/{uuid.uuid4()}/contribute",
        json={"member_id": "user:alice", "content": "Hello"},
        headers=headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/councils/{id}/contribute — 404
# ---------------------------------------------------------------------------


def test_contribute_404_on_missing_session(client, headers):
    with patch("synapse.routers.contributions.get_session", new=AsyncMock(return_value=None)):
        resp = client.post(
            f"/v1/councils/{uuid.uuid4()}/contribute",
            json=_VALID_BODY,
            headers=headers,
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /v1/councils/{id}/contribute — 409 wrong status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_status",
    [
        CouncilStatus.pending,
        CouncilStatus.stage_1,
        CouncilStatus.stage_2,
        CouncilStatus.stage_3,
        CouncilStatus.closed,
        CouncilStatus.failed,
        CouncilStatus.pending_approval,
        CouncilStatus.scheduled,
    ],
)
def test_contribute_409_on_wrong_status(client, headers, bad_status):
    council = _make_async_council(status=bad_status)
    with patch("synapse.routers.contributions.get_session", new=AsyncMock(return_value=council)):
        resp = client.post(
            f"/v1/councils/{council.id}/contribute",
            json=_VALID_BODY,
            headers=headers,
        )
    assert resp.status_code == 409
    assert str(bad_status) in resp.json()["detail"] or bad_status.value in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /v1/councils/{id}/contribute — 202, quorum not met
# ---------------------------------------------------------------------------


def test_contribute_202_below_quorum_returns_correct_body(client, headers):
    session_id = uuid.uuid4()
    # After contribution: 1 of 2 required (quorum=2)
    after_contribution = _make_async_council(
        session_id=session_id,
        status=CouncilStatus.waiting_contributions,
        contributions=[{"member_id": "user:alice", "content": "..."}],
        quorum=2,
    )

    with (
        patch(
            "synapse.routers.contributions.get_session",
            new=AsyncMock(
                return_value=_make_async_council(status=CouncilStatus.waiting_contributions)
            ),
        ),
        patch(
            "synapse.routers.contributions.add_contribution",
            new=AsyncMock(return_value=after_contribution),
        ),
        patch("synapse.routers.contributions.asyncio.create_task") as mock_task,
    ):
        resp = client.post(
            f"/v1/councils/{session_id}/contribute",
            json=_VALID_BODY,
            headers=headers,
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["session_id"] == str(session_id)
    assert body["quorum_met"] is False
    assert body["contributions_received"] == 1
    assert body["quorum"] == 2
    mock_task.assert_not_called()


# ---------------------------------------------------------------------------
# POST /v1/councils/{id}/contribute — 202, quorum met → resume triggered
# ---------------------------------------------------------------------------


def test_contribute_202_quorum_met_triggers_background_resume(client, headers):
    session_id = uuid.uuid4()
    # After contribution: 2 of 2 → quorum met
    after_contribution = _make_async_council(
        session_id=session_id,
        status=CouncilStatus.waiting_contributions,
        contributions=[{"member_id": "user:alice"}, {"member_id": "user:bob"}],
        quorum=2,
    )

    with (
        patch(
            "synapse.routers.contributions.get_session",
            new=AsyncMock(
                return_value=_make_async_council(status=CouncilStatus.waiting_contributions)
            ),
        ),
        patch(
            "synapse.routers.contributions.add_contribution",
            new=AsyncMock(return_value=after_contribution),
        ),
        patch("synapse.routers.contributions.asyncio.create_task") as mock_task,
    ):
        resp = client.post(
            f"/v1/councils/{session_id}/contribute",
            json=_VALID_BODY,
            headers=headers,
        )

    assert resp.status_code == 202
    body = resp.json()
    assert body["quorum_met"] is True
    assert body["contributions_received"] == 2
    mock_task.assert_called_once()


def test_contribute_quorum_met_response_includes_all_fields(client, headers):
    session_id = uuid.uuid4()
    after_contribution = _make_async_council(
        session_id=session_id,
        status=CouncilStatus.waiting_contributions,
        contributions=[{}],
        quorum=1,
    )

    with (
        patch(
            "synapse.routers.contributions.get_session",
            new=AsyncMock(
                return_value=_make_async_council(status=CouncilStatus.waiting_contributions)
            ),
        ),
        patch(
            "synapse.routers.contributions.add_contribution",
            new=AsyncMock(return_value=after_contribution),
        ),
        patch("synapse.routers.contributions.asyncio.create_task"),
    ):
        resp = client.post(
            f"/v1/councils/{session_id}/contribute",
            json=_VALID_BODY,
            headers=headers,
        )

    body = resp.json()
    assert "session_id" in body
    assert "contributions_received" in body
    assert "quorum" in body
    assert "quorum_met" in body


# ---------------------------------------------------------------------------
# POST /v1/councils/{id}/contribute — quorum defaults to member count
# ---------------------------------------------------------------------------


def test_contribute_quorum_defaults_to_member_count_in_response(client, headers):
    session_id = uuid.uuid4()
    members = [
        {"model_id": "openai/gpt-4o"},
        {"model_id": "anthropic/claude-3-5"},
        {"model_id": "google/gemini"},
    ]
    after_contribution = _make_async_council(
        session_id=session_id,
        status=CouncilStatus.waiting_contributions,
        contributions=[{}],
        quorum=None,  # should default to len(members) = 3
        members=members,
    )

    with (
        patch(
            "synapse.routers.contributions.get_session",
            new=AsyncMock(
                return_value=_make_async_council(status=CouncilStatus.waiting_contributions)
            ),
        ),
        patch(
            "synapse.routers.contributions.add_contribution",
            new=AsyncMock(return_value=after_contribution),
        ),
        patch("synapse.routers.contributions.asyncio.create_task"),
    ):
        resp = client.post(
            f"/v1/councils/{session_id}/contribute",
            json=_VALID_BODY,
            headers=headers,
        )

    body = resp.json()
    assert body["quorum"] == 3  # len(members)
    assert body["quorum_met"] is False  # only 1 of 3


# ---------------------------------------------------------------------------
# mark_failed — sets status, records error, commits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_failed_sets_status_and_error():
    """mark_failed transitions the session to failed and stores the error string."""
    from synapse.council.session import mark_failed

    session_id = uuid.uuid4()
    mock_session_obj = MagicMock(spec=CouncilSession)
    mock_session_obj.status = CouncilStatus.stage_1
    mock_session_obj.config = {}

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_session_obj)
    mock_db.commit = AsyncMock()

    await mark_failed(mock_db, session_id, error="LLM timeout")

    assert mock_session_obj.status == CouncilStatus.failed
    assert mock_session_obj.config["_error"] == "LLM timeout"
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_failed_no_op_on_missing_session():
    """mark_failed silently no-ops when the session does not exist."""
    from synapse.council.session import mark_failed

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    mock_db.commit = AsyncMock()

    await mark_failed(mock_db, uuid.uuid4(), error="gone")

    mock_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_failed_without_error_message():
    """mark_failed works when no error string is provided."""
    from synapse.council.session import mark_failed

    session_id = uuid.uuid4()
    mock_session_obj = MagicMock(spec=CouncilSession)
    mock_session_obj.status = CouncilStatus.stage_2
    mock_session_obj.config = {}

    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_session_obj)
    mock_db.commit = AsyncMock()

    await mark_failed(mock_db, session_id)

    assert mock_session_obj.status == CouncilStatus.failed
    assert "_error" not in mock_session_obj.config
    mock_db.commit.assert_awaited_once()
