"""Memory router — search Astrocyte banks from the UI."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.memory.banks import Banks
from synapse.memory.context import build_context

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])

# Banks that the UI is allowed to query directly
_ALLOWED_BANKS = {Banks.COUNCILS, Banks.DECISIONS, Banks.PRECEDENTS}
_DEFAULT_BANK = Banks.DECISIONS


# ---------------------------------------------------------------------------
# GET /v1/memory/search
# ---------------------------------------------------------------------------


@router.get(
    "/memory/search",
    summary="Search Astrocyte memory banks",
)
async def search_memory(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=500, description="Search query")],
    bank: Annotated[
        str,
        Query(description=f"Bank to search. One of: {', '.join(sorted(_ALLOWED_BANKS))}"),
    ] = _DEFAULT_BANK,
    limit: Annotated[int, Query(ge=1, le=20, description="Max results")] = 10,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if bank not in _ALLOWED_BANKS:
        bank = _DEFAULT_BANK

    context = build_context(user)
    astrocyte = request.app.state.astrocyte

    hits = await astrocyte.recall(
        query=q,
        bank_id=bank,
        context=context,
        max_results=limit,
    )

    return {
        "query": q,
        "bank": bank,
        "count": len(hits),
        "hits": [
            {
                "memory_id": h.memory_id,
                "content": h.content,
                "score": round(h.score, 4),
                "bank_id": h.bank_id,
                "tags": h.tags,
                "metadata": h.metadata,
            }
            for h in hits
        ],
    }
