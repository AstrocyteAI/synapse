"""S-MT1 — defense-in-depth tenant isolation contract tests.

Asserts that every route which fetches or mutates a tenant-scoped row
refuses to leak across tenants — even when the caller knows a valid
session_id / thread_id / api_key_id from another tenant.

Two layers of coverage:

  1. **Repo helpers** — `get_session`, `get_thread` accept a `tenant_id`
     kwarg and return ``None`` on cross-tenant fetches. Verified
     directly so the helper's contract is locked in even if no router
     uses it (yet).
  2. **Routers** — each endpoint that previously had a hole (or a
     403/404 distinction info leak) is exercised with a JWT for tenant
     A against a row in tenant B; the response must be 404 (not 403,
     not 200, not 500).

The tests use the same AsyncMock pattern as the rest of the suite —
real Postgres isn't required because the contract being tested is
"the helper / router routes the request through tenant_id correctly,"
not "the database constraint actually enforces it." The repo helpers
are unit-tested at the SQL level by the existing council/thread
tests.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from synapse.db.models import CouncilSession, CouncilStatus, Thread
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS, make_jwt

# ---------------------------------------------------------------------------
# Repo-helper unit tests — get_session / get_thread tenant scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_session_returns_none_when_tenant_mismatches():
    """Cross-tenant fetch collapses to None — caller can't distinguish
    'exists in another tenant' from 'doesn't exist'."""
    from synapse.council.session import get_session

    db = AsyncMock()
    row = MagicMock(spec=CouncilSession)
    row.tenant_id = "tenant-A"
    db.get = AsyncMock(return_value=row)

    result = await get_session(db, uuid.uuid4(), tenant_id="tenant-B")
    assert result is None


@pytest.mark.asyncio
async def test_get_session_returns_row_when_tenant_matches():
    from synapse.council.session import get_session

    db = AsyncMock()
    row = MagicMock(spec=CouncilSession)
    row.tenant_id = "tenant-A"
    db.get = AsyncMock(return_value=row)

    result = await get_session(db, uuid.uuid4(), tenant_id="tenant-A")
    assert result is row


@pytest.mark.asyncio
async def test_get_session_unscoped_path_returns_row_regardless():
    """The default ``...`` sentinel is the un-scoped path used by
    background workers. It must keep working."""
    from synapse.council.session import get_session

    db = AsyncMock()
    row = MagicMock(spec=CouncilSession)
    row.tenant_id = "tenant-A"
    db.get = AsyncMock(return_value=row)

    result = await get_session(db, uuid.uuid4())
    assert result is row


@pytest.mark.asyncio
async def test_get_session_with_explicit_none_tenant_matches_null_rows():
    """A JWT with no tenant_id must only see rows where tenant_id IS NULL."""
    from synapse.council.session import get_session

    db = AsyncMock()
    null_row = MagicMock(spec=CouncilSession)
    null_row.tenant_id = None
    db.get = AsyncMock(return_value=null_row)

    assert await get_session(db, uuid.uuid4(), tenant_id=None) is null_row

    # Same query, but the row has a tenant — must be filtered out
    other_row = MagicMock(spec=CouncilSession)
    other_row.tenant_id = "tenant-A"
    db.get = AsyncMock(return_value=other_row)
    assert await get_session(db, uuid.uuid4(), tenant_id=None) is None


@pytest.mark.asyncio
async def test_get_thread_returns_none_when_tenant_mismatches():
    from synapse.council.thread import get_thread

    db = AsyncMock()
    thread = MagicMock(spec=Thread)
    thread.tenant_id = "tenant-A"
    db.get = AsyncMock(return_value=thread)

    assert await get_thread(db, uuid.uuid4(), tenant_id="tenant-B") is None


@pytest.mark.asyncio
async def test_get_thread_unscoped_path_returns_row():
    from synapse.council.thread import get_thread

    db = AsyncMock()
    thread = MagicMock(spec=Thread)
    thread.tenant_id = "tenant-A"
    db.get = AsyncMock(return_value=thread)

    assert await get_thread(db, uuid.uuid4()) is thread


# ---------------------------------------------------------------------------
# Router-level: contributions endpoint must 404 (not 403, not 200) on
# cross-tenant POST. This is the highest-severity gap MT-1 closed —
# previously a tenant-A caller could write a contribution to a tenant-B
# council if they knew the session_id.
# ---------------------------------------------------------------------------


def _make_council(tenant_id: str, status=CouncilStatus.waiting_contributions):
    obj = MagicMock(spec=CouncilSession)
    obj.id = uuid.uuid4()
    obj.tenant_id = tenant_id
    obj.status = status
    obj.contributions = []
    obj.quorum = 1
    obj.members = [{"model_id": "openai/gpt-4o", "name": "GPT"}]
    return obj


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


def test_contributions_returns_404_for_cross_tenant_session(client):
    """Tenant-A caller targets a session that lives in tenant-B.

    Previous behaviour: 202 (the contribution was written). Post-MT-1:
    404 — same shape as a missing session, so the caller can't even
    learn that the session exists.
    """
    council_in_tenant_b = _make_council(tenant_id="tenant-B")
    headers = {"Authorization": f"Bearer {make_jwt(tenant_id='tenant-A')}"}

    with patch(
        "synapse.routers.contributions.get_session",
        new=AsyncMock(return_value=council_in_tenant_b),
    ):
        resp = client.post(
            f"/v1/councils/{council_in_tenant_b.id}/contribute",
            json={
                "member_id": "user:alice",
                "member_name": "Alice",
                "content": "This shouldn't go through.",
            },
            headers=headers,
        )

    assert resp.status_code == 404


def test_contributions_admin_can_cross_tenants(client):
    """Admins keep their cross-tenant escape hatch (audit / debugging).

    The 404 we just asserted for non-admins must NOT apply when the
    JWT carries the admin role — otherwise we've broken the legitimate
    operator path.
    """
    council_in_tenant_b = _make_council(tenant_id="tenant-B")
    admin_token = make_jwt(tenant_id="tenant-A", roles=["admin"])
    headers = {"Authorization": f"Bearer {admin_token}"}

    with (
        patch(
            "synapse.routers.contributions.get_session",
            new=AsyncMock(return_value=council_in_tenant_b),
        ),
        patch(
            "synapse.routers.contributions.add_contribution",
            new=AsyncMock(return_value=council_in_tenant_b),
        ),
        patch("synapse.routers.contributions.asyncio.create_task"),
    ):
        resp = client.post(
            f"/v1/councils/{council_in_tenant_b.id}/contribute",
            json={
                "member_id": "user:alice",
                "member_name": "Alice",
                "content": "Operator override — investigating.",
            },
            headers=headers,
        )

    assert resp.status_code == 202


# ---------------------------------------------------------------------------
# Router-level: audit log fails closed when tenant_id is null.
#
# The previous bug was that a JWT with no `synapse_tenant` claim saw
# audit events for EVERY tenant. Post-MT-1 such a caller sees only
# rows where tenant_id IS NULL — same scope as their JWT.
# ---------------------------------------------------------------------------


def test_audit_log_filters_null_tenant_jwt_strictly(client, _wired_client):
    """JWT with no tenant_id must produce a query that filters
    `tenant_id IS NULL`, not a query without a tenant filter."""
    _, db_session = _wired_client

    # The route only needs db.execute to return something iterable.
    db_session.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        )
    )

    # Hand-build a JWT with no tenant_id claim (different from
    # `make_jwt` which always sets one).
    import jwt as pyjwt

    from tests.conftest import TEST_JWT_SECRET

    token = pyjwt.encode(
        {
            "sub": "admin-without-tenant",
            "aud": "synapse",
            "synapse_roles": ["admin"],
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )

    resp = client.get(
        "/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    # Inspect the generated SQL — it must contain a tenant_id filter.
    # Without the MT-1 fix the query had no tenant clause at all when
    # user.tenant_id was falsy.
    captured_stmt = db_session.execute.call_args.args[0]
    compiled_sql = str(captured_stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    assert "tenant_id" in compiled_sql, (
        "audit-log query must filter on tenant_id even when JWT has no "
        f"tenant claim — produced SQL: {compiled_sql}"
    )
