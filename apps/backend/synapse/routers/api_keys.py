"""API keys router — B9: machine-to-machine authentication via hashed API keys."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from synapse.audit import emit as audit_emit
from synapse.auth.jwt import AuthenticatedUser, generate_api_key, get_current_user
from synapse.db.models import ApiKey
from synapse.db.session import get_session as get_db_session

router = APIRouter(tags=["api-keys"])


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateApiKeyRequest(BaseModel):
    name: str
    roles: list[str] = ["member"]


class ApiKeyCreatedResponse(BaseModel):
    id: uuid.UUID
    name: str
    key: str  # raw key — shown ONCE
    key_prefix: str
    roles: list[str]
    created_at: datetime
    tenant_id: str | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    roles: list[str]
    created_at: datetime
    last_used_at: datetime | None = None
    tenant_id: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    body: CreateApiKeyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """Create a new API key. The raw key is returned once and never stored."""
    # Only admins may create keys with admin role
    if "admin" in body.roles and "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Only admins can create admin-scoped keys")

    raw_key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        id=uuid.uuid4(),
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        created_by=user.principal,
        tenant_id=user.tenant_id,
        roles=body.roles,
        created_at=datetime.now(UTC),
    )
    db.add(api_key)
    await audit_emit(
        db,
        "api_key.created",
        user.principal,
        tenant_id=user.tenant_id,
        resource_type="api_key",
        resource_id=str(api_key.id),
        metadata={"name": body.name, "roles": body.roles},
    )
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        key_prefix=api_key.key_prefix,
        roles=list(api_key.roles),
        created_at=api_key.created_at,
        tenant_id=api_key.tenant_id,
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    """List active (non-revoked) API keys for the current user."""
    stmt = select(ApiKey).where(
        ApiKey.created_by == user.principal,
        ApiKey.revoked_at.is_(None),
    )
    result = await db.execute(stmt)
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            roles=list(k.roles),
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            tenant_id=k.tenant_id,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    """Revoke (soft-delete) an API key."""
    api_key = await db.get(ApiKey, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Admins can revoke any key in their tenant; others can only revoke their own
    is_admin = "admin" in user.roles
    owns_key = api_key.created_by == user.principal
    same_tenant = api_key.tenant_id == user.tenant_id

    if not owns_key and not (is_admin and same_tenant):
        raise HTTPException(status_code=403, detail="Cannot revoke this API key")

    if api_key.revoked_at is not None:
        raise HTTPException(status_code=409, detail="API key is already revoked")

    api_key.revoked_at = datetime.now(UTC)
    await audit_emit(
        db,
        "api_key.revoked",
        user.principal,
        tenant_id=user.tenant_id,
        resource_type="api_key",
        resource_id=str(key_id),
        metadata={"name": api_key.name},
    )
    await db.commit()
