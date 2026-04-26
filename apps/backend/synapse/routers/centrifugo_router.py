"""Centrifugo connection token endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.realtime.tokens import issue_connection_token

router = APIRouter(tags=["realtime"])


@router.get(
    "/centrifugo/token",
    summary="Issue a Centrifugo connection token for the authenticated user",
)
async def get_centrifugo_token(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    settings = request.app.state.settings
    token = issue_connection_token(user.sub, settings)
    return {"token": token}


@router.get(
    "/socket/token",
    summary="Issue a realtime transport descriptor",
)
async def get_socket_token(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    settings = request.app.state.settings
    token = issue_connection_token(user.sub, settings)
    ttl = settings.centrifugo_token_ttl_seconds

    return {
        "transport": "centrifugo",
        "url": settings.centrifugo_ws_url,
        "token": token,
        "expires_in": ttl,
        "topics": {
            "council": "council:<council_id>",
            "thread": "thread:<thread_id>",
        },
    }
