"""Local auth router — POST /v1/auth/register, /v1/auth/login, GET /v1/auth/me.

Active only when SYNAPSE_AUTH_MODE=local.  In other modes these endpoints
return 501 so clients get a clear error rather than a silent 404.

Migration path to Cerebro
--------------------------
GET /v1/admin/users/export returns the full user list (id, email, role) for
import into Casdoor.  The ``id`` UUID is preserved as the Casdoor user ID so
the JWT ``sub`` claim stays identical across the migration — no principal
reconciliation needed in Cerebro.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.auth.local import hash_password, issue_token, verify_password
from synapse.db.models import User
from synapse.db.session import get_session as get_db_session

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterIn(BaseModel):
    email: EmailStr
    password: str


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    id: str
    email: str
    role: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_local_mode(request: Request) -> None:
    if request.app.state.settings.synapse_auth_mode != "local":
        raise HTTPException(
            status_code=501, detail="Local auth is not enabled (SYNAPSE_AUTH_MODE != local)"
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(
    body: RegisterIn,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> TokenOut:
    """Create a new local user account and return an access token.

    Disabled when ``synapse_local_registration_open=False`` — use
    POST /v1/admin/users to create accounts in that case.
    """
    _require_local_mode(request)
    settings = request.app.state.settings

    if not settings.synapse_local_registration_open:
        raise HTTPException(status_code=403, detail="Public registration is disabled")

    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role="member",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = issue_token(str(user.id), user.email, user.role, settings)
    return TokenOut(access_token=token, expires_in=settings.synapse_local_jwt_ttl_seconds)


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> TokenOut:
    """Authenticate with email + password and return an access token."""
    _require_local_mode(request)
    settings = request.app.state.settings

    user = await db.scalar(select(User).where(User.email == body.email, User.is_active.is_(True)))
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login_at = datetime.now(UTC)
    await db.commit()

    token = issue_token(str(user.id), user.email, user.role, settings)
    return TokenOut(access_token=token, expires_in=settings.synapse_local_jwt_ttl_seconds)


@router.get("/me", response_model=UserOut)
async def me(
    request: Request,
    current: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserOut:
    """Return the authenticated user's profile."""
    _require_local_mode(request)
    user = await db.scalar(select(User).where(User.id == current.sub))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(id=str(user.id), email=user.email, role=user.role)


# ---------------------------------------------------------------------------
# Admin — user management + migration export
# ---------------------------------------------------------------------------


@router.post("/users", response_model=UserOut, status_code=201, tags=["admin"])
async def admin_create_user(
    body: RegisterIn,
    request: Request,
    current: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> UserOut:
    """Admin-only: create a user account (used when registration_open=False)."""
    _require_local_mode(request)
    if "admin" not in current.roles:
        raise HTTPException(status_code=403, detail="Admin role required")

    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role="member",
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut(id=str(user.id), email=user.email, role=user.role)


@router.get("/users/export", tags=["admin"])
async def export_users(
    request: Request,
    current: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Admin-only: export user list for Casdoor import during Cerebro migration.

    The ``id`` field is the UUID to use as the Casdoor user ID — preserving it
    means the JWT ``sub`` claim is identical in both systems and no principal
    reconciliation is needed in Cerebro after migration.
    """
    _require_local_mode(request)
    if "admin" not in current.roles:
        raise HTTPException(status_code=403, detail="Admin role required")

    users = (await db.execute(select(User))).scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]
