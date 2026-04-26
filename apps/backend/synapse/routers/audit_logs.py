"""Audit log compatibility endpoints for the shared backend contract."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from synapse.auth.jwt import AuthenticatedUser, get_current_user

router = APIRouter(tags=["audit-logs"])


@router.get("/audit_logs")
async def list_audit_logs(
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 100,
) -> dict:
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="admin role required")

    return {"data": [], "limit": limit}
