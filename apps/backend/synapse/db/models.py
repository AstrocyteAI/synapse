"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class CouncilStatus(str, PyEnum):
    pending = "pending"
    stage_1 = "stage_1"
    stage_2 = "stage_2"
    stage_3 = "stage_3"
    closed = "closed"
    failed = "failed"


class CouncilType(str, PyEnum):
    llm = "llm"
    agent = "agent"
    mixed = "mixed"
    solo = "solo"


class CouncilSession(Base):
    __tablename__ = "council_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=CouncilStatus.pending)
    council_type: Mapped[str] = mapped_column(String(16), nullable=False, default=CouncilType.llm)

    # Member config — list of {model_id, name, role, system_prompt_override}
    members: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    chairman: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Per-session overrides
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Verdict (populated after stage_3)
    verdict: Mapped[str | None] = mapped_column(Text, nullable=True)
    consensus_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    dissent_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Metadata
    topic_tag: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(256), nullable=False)  # principal
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transcript: Mapped[CouncilTranscript | None] = relationship(
        "CouncilTranscript", back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class CouncilTranscript(Base):
    """Full stage-by-stage transcript. Kept separate to keep sessions table lean."""

    __tablename__ = "council_transcripts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    council_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("council_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Stage outputs
    precedents: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    stage1_responses: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    stage2_rankings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    aggregate_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    stage3_verdict: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    session: Mapped[CouncilSession] = relationship("CouncilSession", back_populates="transcript")
