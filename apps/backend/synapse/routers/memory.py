"""Memory router — Astrocyte operations exposed via Synapse REST API."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from synapse.auth.jwt import AuthenticatedUser, get_current_user
from synapse.memory.banks import Banks
from synapse.memory.context import build_context
from synapse.memory.models import (
    CompileRequest,
    ForgetRequest,
    GraphNeighborsRequest,
    GraphSearchRequest,
    ReflectRequest,
    RetainRequest,
)

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])

# ---------------------------------------------------------------------------
# Bank allow-lists per operation
# ---------------------------------------------------------------------------

# Read-only recall/search — same banks the council engine reads from
_SEARCH_BANKS = {Banks.COUNCILS, Banks.DECISIONS, Banks.PRECEDENTS}
_DEFAULT_BANK = Banks.DECISIONS

# Direct user writes only go to their own agent bank
_RETAIN_BANKS = {Banks.AGENTS}

# Direct user deletes only from agent bank — councils/decisions are managed by the engine
_FORGET_BANKS = {Banks.AGENTS}

# Graph traversal is read-only — allow richer cross-bank discovery
_GRAPH_BANKS = {Banks.DECISIONS, Banks.PRECEDENTS, Banks.AGENTS}

# Wiki compilation makes sense on decisions and agent context
_COMPILE_BANKS = {Banks.DECISIONS, Banks.AGENTS}


def _bank_error(allowed: set[str]) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail=f"bank_id must be one of: {', '.join(sorted(allowed))}",
    )


# ---------------------------------------------------------------------------
# GET /v1/memory/search  (recall)
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
        Query(description=f"Bank to search. One of: {', '.join(sorted(_SEARCH_BANKS))}"),
    ] = _DEFAULT_BANK,
    limit: Annotated[int, Query(ge=1, le=20, description="Max results")] = 10,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if bank not in _SEARCH_BANKS:
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


@router.get(
    "/memory/recall",
    summary="Recall memories using the shared Synapse backend contract",
)
async def recall_memory(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=500, description="Search query")],
    bank: Annotated[
        str,
        Query(description=f"Bank to search. One of: {', '.join(sorted(_SEARCH_BANKS))}"),
    ] = _DEFAULT_BANK,
    limit: Annotated[int, Query(ge=1, le=20, description="Max results")] = 10,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    result = await search_memory(request=request, q=q, bank=bank, limit=limit, user=user)
    return {"data": {"memories": result["hits"], "query": result["query"], "bank": result["bank"]}}


# ---------------------------------------------------------------------------
# POST /v1/memory/retain
# ---------------------------------------------------------------------------


@router.post(
    "/memory/retain",
    summary="Store a memory in Astrocyte",
    status_code=201,
)
async def retain_memory(
    request: Request,
    body: RetainRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if body.bank_id not in _RETAIN_BANKS:
        raise _bank_error(_RETAIN_BANKS)

    context = build_context(user)
    result = await request.app.state.astrocyte.retain(
        content=body.content,
        bank_id=body.bank_id,
        tags=body.tags,
        context=context,
        metadata=body.metadata if body.metadata else None,
    )
    return {"memory_id": result.memory_id, "stored": result.stored}


# ---------------------------------------------------------------------------
# POST /v1/memory/reflect
# ---------------------------------------------------------------------------


@router.post(
    "/memory/reflect",
    summary="Synthesise an answer over a memory bank (wiki-style reflection)",
)
async def reflect_memory(
    request: Request,
    body: ReflectRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if body.bank_id not in _SEARCH_BANKS:
        raise _bank_error(_SEARCH_BANKS)

    context = build_context(user)
    result = await request.app.state.astrocyte.reflect(
        query=body.query,
        bank_id=body.bank_id,
        context=context,
        max_tokens=body.max_tokens,
        include_sources=body.include_sources,
    )
    return {"answer": result.answer, "sources": result.sources}


# ---------------------------------------------------------------------------
# POST /v1/memory/forget
# ---------------------------------------------------------------------------


@router.post(
    "/memory/forget",
    summary="Delete memories from Astrocyte",
)
async def forget_memory(
    request: Request,
    body: ForgetRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if body.bank_id not in _FORGET_BANKS:
        raise _bank_error(_FORGET_BANKS)

    context = build_context(user)
    result = await request.app.state.astrocyte.forget(
        bank_id=body.bank_id,
        context=context,
        memory_ids=body.memory_ids,
        tags=body.tags,
    )
    return result if isinstance(result, dict) else {"ok": True}


# ---------------------------------------------------------------------------
# POST /v1/memory/graph/search
# ---------------------------------------------------------------------------


@router.post(
    "/memory/graph/search",
    summary="Search the knowledge graph for entities by name",
)
async def graph_search(
    request: Request,
    body: GraphSearchRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if body.bank_id not in _GRAPH_BANKS:
        raise _bank_error(_GRAPH_BANKS)

    context = build_context(user)
    entities = await request.app.state.astrocyte.graph_search(
        query=body.query,
        bank_id=body.bank_id,
        context=context,
        limit=body.limit,
    )
    return {
        "query": body.query,
        "bank": body.bank_id,
        "count": len(entities),
        "entities": [
            {
                "entity_id": e.entity_id,
                "name": e.name,
                "entity_type": e.entity_type,
                "metadata": e.metadata,
            }
            for e in entities
        ],
    }


# ---------------------------------------------------------------------------
# POST /v1/memory/graph/neighbors
# ---------------------------------------------------------------------------


@router.post(
    "/memory/graph/neighbors",
    summary="Traverse the knowledge graph from seed entity IDs",
)
async def graph_neighbors(
    request: Request,
    body: GraphNeighborsRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if body.bank_id not in _GRAPH_BANKS:
        raise _bank_error(_GRAPH_BANKS)

    context = build_context(user)
    hits = await request.app.state.astrocyte.graph_neighbors(
        entity_ids=body.entity_ids,
        bank_id=body.bank_id,
        context=context,
        max_depth=body.max_depth,
        limit=body.limit,
    )
    return {
        "bank": body.bank_id,
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


# ---------------------------------------------------------------------------
# POST /v1/memory/compile
# ---------------------------------------------------------------------------


@router.post(
    "/memory/compile",
    summary="Trigger wiki synthesis (M8 compile pipeline) for a memory bank",
    status_code=202,
)
async def compile_memory(
    request: Request,
    body: CompileRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if body.bank_id not in _COMPILE_BANKS:
        raise _bank_error(_COMPILE_BANKS)

    context = build_context(user)
    result = await request.app.state.astrocyte.compile(
        bank_id=body.bank_id,
        context=context,
        scope=body.scope,
    )
    return result if isinstance(result, dict) else {"ok": True, "bank_id": body.bank_id}
