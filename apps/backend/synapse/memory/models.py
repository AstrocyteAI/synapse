"""Pydantic request/response models for the memory router."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class RetainRequest(BaseModel):
    content: str = Field(min_length=1, max_length=50_000, description="Text to store")
    bank_id: str = Field(min_length=1, description="Target bank")
    tags: list[str] = Field(default_factory=list, description="Classification tags")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary key/value metadata"
    )


class ReflectRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500, description="Question to reflect on")
    bank_id: str = Field(min_length=1, description="Bank to synthesise from")
    include_sources: bool = Field(default=True, description="Include source memories in response")
    max_tokens: int | None = Field(
        default=None, ge=1, le=8_000, description="Token budget for synthesis"
    )


class ForgetRequest(BaseModel):
    bank_id: str = Field(min_length=1, description="Bank to delete from")
    memory_ids: list[str] | None = Field(default=None, description="Specific memory IDs to delete")
    tags: list[str] | None = Field(default=None, description="Delete all memories with these tags")

    @model_validator(mode="after")
    def _require_selector(self) -> ForgetRequest:
        if not self.memory_ids and not self.tags:
            raise ValueError("At least one of memory_ids or tags must be provided")
        return self


class GraphSearchRequest(BaseModel):
    query: str = Field(
        min_length=1, max_length=500, description="Entity name or partial name to search"
    )
    bank_id: str = Field(min_length=1, description="Bank whose graph to search")
    limit: int = Field(default=10, ge=1, le=50, description="Max entities to return")


class GraphNeighborsRequest(BaseModel):
    entity_ids: list[str] = Field(min_length=1, description="Seed entity IDs to traverse from")
    bank_id: str = Field(min_length=1, description="Bank whose graph to traverse")
    max_depth: int = Field(default=2, ge=1, le=5, description="Traversal hop depth")
    limit: int = Field(default=20, ge=1, le=100, description="Max memory hits to return")


class CompileRequest(BaseModel):
    bank_id: str = Field(min_length=1, description="Bank to compile wiki pages for")
    scope: str | None = Field(default=None, description="Restrict compilation to this topic scope")
