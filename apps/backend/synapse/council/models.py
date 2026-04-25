"""Pydantic models for council requests, responses, and in-flight state."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field


class CouncilMember(BaseModel):
    model_id: str
    name: str = ""  # derived from model_id if empty
    role: str = ""  # injected into system prompt
    system_prompt_override: str = ""  # replaces default system prompt if set


class CreateCouncilRequest(BaseModel):
    question: str
    members: list[CouncilMember] | None = None  # uses defaults if None
    chairman: CouncilMember | None = None  # uses default if None
    council_type: str = "llm"
    template_id: str | None = None
    topic_tag: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class StageOneResponse(BaseModel):
    member_id: str  # e.g. "openai/gpt-4o"
    member_name: str
    content: str
    error: str | None = None


class MemberRanking(BaseModel):
    member_id: str
    member_name: str
    ranking: list[str]  # ordered labels: ["Response B", "Response A", "Response C"]
    raw_response: str


class RankingResult(BaseModel):
    label_map: dict[str, str]  # {"Response A": "member_id", ...}
    member_rankings: list[MemberRanking]
    aggregate_scores: dict[str, float]  # {"Response A": 1.67, ...}  (lower = better rank)
    consensus_score: float  # Kendall's W [0, 1]


class SynthesisResult(BaseModel):
    verdict: str
    confidence_label: str  # high | medium | low
    uncertainty_markers: list[str] = Field(default_factory=list)


class ConflictResult(BaseModel):
    detected: bool
    summary: str | None = None  # LLM-generated explanation of the conflict
    conflicting_content: str | None = None  # the precedent text that conflicts
    precedent_score: float | None = None  # similarity score of the conflicting precedent


class MemberCritique(BaseModel):
    member_id: str
    member_name: str
    critique: str
    error: str | None = None


class DeliberationRound(BaseModel):
    round: int
    critiques: list[MemberCritique]
    revised_responses: list[StageOneResponse]
    converged: bool = False


class CouncilResult(BaseModel):
    session_id: uuid.UUID
    question: str
    verdict: str
    consensus_score: float
    confidence_label: str
    dissent_detected: bool
    stage1_responses: list[StageOneResponse]  # final-round responses going into ranking
    ranking_result: RankingResult
    synthesis: SynthesisResult
    deliberation_rounds: list[DeliberationRound] = Field(default_factory=list)
