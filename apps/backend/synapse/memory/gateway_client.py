"""Astrocyte gateway HTTP client — retain / recall / reflect / forget."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from synapse.memory.context import AstrocyteContext

_logger = logging.getLogger(__name__)


@dataclass
class MemoryHit:
    memory_id: str
    content: str
    score: float
    bank_id: str
    tags: list[str]
    metadata: dict[str, Any]


@dataclass
class RetainResult:
    memory_id: str
    stored: bool


@dataclass
class ReflectResult:
    answer: str
    sources: list[dict[str, Any]]


class AstrocyteGatewayClient:
    """Thin async HTTP wrapper over the Astrocyte gateway REST API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = http_client

    def _headers(self, context: AstrocyteContext) -> dict[str, str]:
        """Build headers for api_key auth mode: X-Api-Key + X-Astrocyte-Principal."""
        return {
            "X-Api-Key": self._api_key,
            "X-Astrocyte-Principal": context.principal,
            "Content-Type": "application/json",
        }

    async def retain(
        self,
        content: str,
        bank_id: str,
        tags: list[str],
        context: AstrocyteContext,
        metadata: dict[str, Any] | None = None,
    ) -> RetainResult:
        payload: dict[str, Any] = {"content": content, "bank_id": bank_id, "tags": tags}
        if metadata:
            payload["metadata"] = metadata

        resp = await self._http.post(
            f"{self._base_url}/v1/retain",
            json=payload,
            headers=self._headers(context),
        )
        resp.raise_for_status()
        data = resp.json()
        return RetainResult(
            memory_id=data.get("memory_id", ""),
            stored=data.get("stored", True),
        )

    async def recall(
        self,
        query: str,
        bank_id: str,
        context: AstrocyteContext,
        max_results: int = 5,
        max_tokens: int | None = None,
        tags: list[str] | None = None,
    ) -> list[MemoryHit]:
        payload: dict[str, Any] = {
            "query": query,
            "bank_id": bank_id,
            "max_results": max_results,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if tags:
            payload["tags"] = tags

        resp = await self._http.post(
            f"{self._base_url}/v1/recall",
            json=payload,
            headers=self._headers(context),
        )
        resp.raise_for_status()
        data = resp.json()

        hits = []
        for h in data.get("memories", []):
            hits.append(
                MemoryHit(
                    memory_id=h.get("memory_id", ""),
                    content=h.get("content", ""),
                    score=h.get("score", 0.0),
                    bank_id=h.get("bank_id", bank_id),
                    tags=h.get("tags", []),
                    metadata=h.get("metadata", {}),
                )
            )
        return hits

    async def reflect(
        self,
        query: str,
        bank_id: str,
        context: AstrocyteContext,
        max_tokens: int | None = None,
        include_sources: bool = True,
    ) -> ReflectResult:
        payload: dict[str, Any] = {
            "query": query,
            "bank_id": bank_id,
            "include_sources": include_sources,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        resp = await self._http.post(
            f"{self._base_url}/v1/reflect",
            json=payload,
            headers=self._headers(context),
        )
        resp.raise_for_status()
        data = resp.json()
        return ReflectResult(
            answer=data.get("answer", ""),
            sources=data.get("sources", []),
        )

    async def forget(
        self,
        bank_id: str,
        context: AstrocyteContext,
        memory_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"bank_id": bank_id}
        if memory_ids:
            payload["memory_ids"] = memory_ids
        if tags:
            payload["tags"] = tags

        resp = await self._http.post(
            f"{self._base_url}/v1/forget",
            json=payload,
            headers=self._headers(context),
        )
        resp.raise_for_status()
        return resp.json()
