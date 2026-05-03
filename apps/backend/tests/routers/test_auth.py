"""Tests for local auth endpoints — /v1/auth/* and /.well-known/*."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from synapse.auth.local import hash_password, issue_token
from synapse.config import Settings
from synapse.db.models import User
from synapse.main import create_app
from tests.conftest import TEST_SETTINGS

# ---------------------------------------------------------------------------
# Generate a throw-away RSA key pair for all auth tests
# ---------------------------------------------------------------------------

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_KEY = _PRIVATE_KEY.public_key()

TEST_PRIVATE_PEM = _PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
).decode()

TEST_PUBLIC_PEM = _PUBLIC_KEY.public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

LOCAL_SETTINGS = Settings(
    **{
        **TEST_SETTINGS.model_dump(),
        "synapse_auth_mode": "local",
        "synapse_local_jwt_private_key": TEST_PRIVATE_PEM,
        "synapse_local_jwt_public_key": TEST_PUBLIC_PEM,
        "synapse_local_jwt_issuer": "http://localhost:8000",
        "synapse_local_registration_open": True,
    }
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_user(
    email: str = "alice@example.com",
    role: str = "member",
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password("correct-password"),
        role=role,
        is_active=is_active,
        created_at=datetime.now(UTC),
    )
    return user


@pytest.fixture
def _wired_client():
    """TestClient wired with local auth settings and a mock DB session."""
    application = create_app()
    mock_session = AsyncMock()
    mock_sessionmaker = MagicMock()
    mock_sessionmaker.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_sessionmaker.return_value.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("synapse.main.get_settings", return_value=LOCAL_SETTINGS),
        TestClient(application, raise_server_exceptions=False) as c,
    ):
        application.state.sessionmaker = mock_sessionmaker
        yield c, mock_session


@pytest.fixture
def client(_wired_client):
    c, _ = _wired_client
    return c


@pytest.fixture
def db(_wired_client):
    _, session = _wired_client
    return session


def _auth_header(user: User) -> dict:
    token = issue_token(str(user.id), user.email, user.role, LOCAL_SETTINGS)
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# POST /v1/auth/register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_creates_user_and_returns_token(self, client, db):
        db.scalar.return_value = None  # no existing user
        db.refresh = AsyncMock(side_effect=lambda u: None)

        resp = client.post(
            "/v1/auth/register", json={"email": "new@example.com", "password": "s3cr3t"}
        )

        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == LOCAL_SETTINGS.synapse_local_jwt_ttl_seconds

    def test_register_409_on_duplicate_email(self, client, db):
        db.scalar.return_value = _make_user()  # existing user

        resp = client.post(
            "/v1/auth/register", json={"email": "alice@example.com", "password": "s3cr3t"}
        )

        assert resp.status_code == 409

    def test_register_403_when_registration_closed(self, db):
        closed_settings = Settings(
            **{**LOCAL_SETTINGS.model_dump(), "synapse_local_registration_open": False}
        )
        application = create_app()
        mock_sessionmaker = MagicMock()
        mock_sessionmaker.return_value.__aenter__ = AsyncMock(return_value=db)
        mock_sessionmaker.return_value.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("synapse.main.get_settings", return_value=closed_settings),
            TestClient(application, raise_server_exceptions=False) as c,
        ):
            application.state.sessionmaker = mock_sessionmaker
            resp = c.post(
                "/v1/auth/register", json={"email": "new@example.com", "password": "s3cr3t"}
            )

        assert resp.status_code == 403

    def test_register_501_in_hs256_mode(self):
        application = create_app()
        with (
            patch("synapse.main.get_settings", return_value=TEST_SETTINGS),
            TestClient(application, raise_server_exceptions=False) as c,
        ):
            resp = c.post(
                "/v1/auth/register", json={"email": "new@example.com", "password": "s3cr3t"}
            )
        assert resp.status_code == 501


# ---------------------------------------------------------------------------
# POST /v1/auth/login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_returns_token(self, client, db):
        db.scalar.return_value = _make_user()

        resp = client.post(
            "/v1/auth/login", json={"email": "alice@example.com", "password": "correct-password"}
        )

        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_401_wrong_password(self, client, db):
        db.scalar.return_value = _make_user()

        resp = client.post(
            "/v1/auth/login", json={"email": "alice@example.com", "password": "wrong"}
        )

        assert resp.status_code == 401

    def test_login_401_unknown_user(self, client, db):
        db.scalar.return_value = None  # user not found

        resp = client.post("/v1/auth/login", json={"email": "ghost@example.com", "password": "any"})

        assert resp.status_code == 401

    def test_login_updates_last_login_at(self, client, db):
        user = _make_user()
        assert user.last_login_at is None
        db.scalar.return_value = user

        client.post(
            "/v1/auth/login", json={"email": "alice@example.com", "password": "correct-password"}
        )

        assert user.last_login_at is not None


# ---------------------------------------------------------------------------
# GET /v1/auth/me
# ---------------------------------------------------------------------------


class TestMe:
    def test_me_returns_user_profile(self, client, db):
        user = _make_user()
        db.scalar.return_value = user

        resp = client.get("/v1/auth/me", headers=_auth_header(user))

        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "alice@example.com"
        assert body["role"] == "member"

    def test_me_401_without_token(self, client):
        resp = client.get("/v1/auth/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /v1/auth/users  (admin create)
# ---------------------------------------------------------------------------


class TestAdminCreateUser:
    def test_admin_can_create_user(self, client, db):
        admin = _make_user(email="admin@example.com", role="admin")
        # get_current_user decodes the JWT directly (no DB call for non-sk- tokens)
        # only call is the duplicate-email check inside admin_create_user
        db.scalar.return_value = None  # no existing user with target email
        db.refresh = AsyncMock(side_effect=lambda u: None)

        resp = client.post(
            "/v1/auth/users",
            json={"email": "new@example.com", "password": "s3cr3t"},
            headers=_auth_header(admin),
        )

        assert resp.status_code == 201
        assert resp.json()["email"] == "new@example.com"

    def test_member_cannot_create_user(self, client, db):
        member = _make_user()
        db.scalar.return_value = member

        resp = client.post(
            "/v1/auth/users",
            json={"email": "new@example.com", "password": "s3cr3t"},
            headers=_auth_header(member),
        )

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /v1/auth/users/export
# ---------------------------------------------------------------------------


class TestExportUsers:
    def test_admin_gets_user_list(self, client, db):
        admin = _make_user(email="admin@example.com", role="admin")
        users = [
            _make_user(email="alice@example.com"),
            _make_user(email="bob@example.com"),
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = users
        db.scalar.return_value = admin
        db.execute = AsyncMock(return_value=mock_result)

        resp = client.get("/v1/auth/users/export", headers=_auth_header(admin))

        assert resp.status_code == 200
        exported = resp.json()
        assert len(exported) == 2
        emails = {u["email"] for u in exported}
        assert emails == {"alice@example.com", "bob@example.com"}
        # id field must be present — used to preserve UUID in Casdoor on migration
        assert all("id" in u for u in exported)

    def test_member_cannot_export(self, client, db):
        member = _make_user()
        db.scalar.return_value = member

        resp = client.get("/v1/auth/users/export", headers=_auth_header(member))

        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /.well-known/jwks.json
# ---------------------------------------------------------------------------


class TestJwks:
    def test_jwks_returns_rsa_key(self, client):
        resp = client.get("/.well-known/jwks.json")

        assert resp.status_code == 200
        body = resp.json()
        assert "keys" in body
        assert len(body["keys"]) == 1
        key = body["keys"][0]
        assert key["kty"] == "RSA"
        assert key["alg"] == "RS256"
        assert key["use"] == "sig"
        assert "n" in key and "e" in key

    def test_jwks_503_when_no_public_key_configured(self):
        no_key_settings = Settings(
            **{**LOCAL_SETTINGS.model_dump(), "synapse_local_jwt_public_key": ""}
        )
        application = create_app()
        with (
            patch("synapse.main.get_settings", return_value=no_key_settings),
            TestClient(application, raise_server_exceptions=False) as c,
        ):
            resp = c.get("/.well-known/jwks.json")
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# GET /.well-known/openid-configuration
# ---------------------------------------------------------------------------


class TestOidcDiscovery:
    def test_discovery_includes_required_fields(self, client):
        resp = client.get("/.well-known/openid-configuration")

        assert resp.status_code == 200
        body = resp.json()
        assert body["issuer"] == LOCAL_SETTINGS.synapse_local_jwt_issuer
        assert "jwks_uri" in body
        assert "token_endpoint" in body
        assert "RS256" in body["id_token_signing_alg_values_supported"]
