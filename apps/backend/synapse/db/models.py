"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class CouncilStatus(StrEnum):
    pending = "pending"
    stage_1 = "stage_1"
    stage_2 = "stage_2"
    stage_3 = "stage_3"
    pending_approval = (
        "pending_approval"  # verdict ready, conflict detected — awaiting human review
    )
    waiting_contributions = "waiting_contributions"  # B3: async council awaiting quorum
    scheduled = "scheduled"  # B7: council scheduled for future run_at time
    closed = "closed"
    failed = "failed"


class CouncilType(StrEnum):
    llm = "llm"
    agent = "agent"
    mixed = "mixed"
    solo = "solo"
    async_ = "async"  # B3: members contribute on own schedule
    red_team = "red_team"  # B5: adversarial attack mode


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

    # Conflict detection (B6) — populated when a verdict contradicts a precedent
    conflict_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Async councils (B3) — contributions accumulate until quorum; then Stage 2+3 fires
    contributions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    quorum: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contribution_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Scheduling (B7) — deferred councils run at this UTC timestamp
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    stage1_responses: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    stage2_rankings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    aggregate_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    stage3_verdict: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Multi-round deliberation — [{round, critiques, revised_responses, converged}]
    deliberation_rounds: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    session: Mapped[CouncilSession] = relationship("CouncilSession", back_populates="transcript")


# ---------------------------------------------------------------------------
# Thread storage — append-only chat event log
# ---------------------------------------------------------------------------


class ThreadEventType(StrEnum):
    user_message = "user_message"
    council_started = "council_started"
    stage_progress = "stage_progress"
    member_response = "member_response"
    ranking_summary = "ranking_summary"
    verdict = "verdict"
    reflection = "reflection"
    precedent_hit = "precedent_hit"
    summon_requested = "summon_requested"
    member_summoned = "member_summoned"
    system_event = "system_event"
    conflict_detected = "conflict_detected"


class Thread(Base):
    """Chat container — one per council session; also supports future standalone chat."""

    __tablename__ = "threads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Nullable — null for standalone chat threads not backed by a council
    council_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("council_sessions.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )

    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    events: Mapped[list[ThreadEvent]] = relationship(
        "ThreadEvent",
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ThreadEvent.id",
    )
    session: Mapped[CouncilSession | None] = relationship(
        "CouncilSession", foreign_keys=[council_id]
    )


class ThreadEvent(Base):
    """Append-only event log for a thread.

    The BIGSERIAL ``id`` is both the global ordering primitive and the
    pagination cursor (use ``before_id`` / ``after_id`` — never SQL OFFSET).

    Primary index: (thread_id, id DESC) — single-partition scan for history.
    """

    __tablename__ = "thread_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    thread_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)

    # actor_id: "user:{sub}" | "agent:{model_id}" | "system"
    actor_id: Mapped[str] = mapped_column(String(256), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    # Human-readable content; null for non-message events
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Event-specific structured payload (see chat.md §8.3 for field shapes)
    # Named "event_metadata" on the Python side; "metadata" is reserved by SQLAlchemy's
    # Declarative API (it is the MetaData object on every Base subclass).
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    thread: Mapped[Thread] = relationship("Thread", back_populates="events")
