"""Council orchestrator — coordinates stages, publishes events, persists results."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from synapse.council.models import CouncilMember, CouncilResult
from synapse.council.stages.gather import run_gather
from synapse.council.stages.rank import run_rank
from synapse.council.stages.synthesise import run_synthesise
from synapse.db.models import CouncilSession, CouncilStatus, CouncilTranscript
from synapse.llm.client import LLMClient, derive_display_name
from synapse.memory.banks import Banks, council_tags, verdict_tags
from synapse.memory.context import AstrocyteContext

if TYPE_CHECKING:
    from synapse.memory.gateway_client import AstrocyteGatewayClient
    from synapse.realtime.centrifugo import CentrifugoClient

_logger = logging.getLogger(__name__)


class CouncilOrchestrator:
    def __init__(
        self,
        astrocyte: AstrocyteGatewayClient,
        centrifugo: CentrifugoClient,
        llm: LLMClient,
        settings,
    ) -> None:
        self._astrocyte = astrocyte
        self._centrifugo = centrifugo
        self._llm = llm
        self._settings = settings

    async def run(
        self,
        session_id: uuid.UUID,
        question: str,
        members: list[CouncilMember],
        chairman: CouncilMember,
        context: AstrocyteContext,
        db: AsyncSession,
        council_type: str = "llm",
        topic_tag: str | None = None,
    ) -> CouncilResult:
        council_id = str(session_id)

        async def publish(event_type: str, payload: dict) -> None:
            try:
                await self._centrifugo.publish_council_event(council_id, event_type, payload)
            except Exception as e:
                _logger.warning("Centrifugo publish failed (%s): %s", event_type, e)

        async def set_status(status: str) -> None:
            session = await db.get(CouncilSession, session_id)
            if session:
                session.status = status
                await db.commit()

        # --- Recall precedents ---
        await set_status(CouncilStatus.pending)
        precedents = []
        try:
            precedents = await self._astrocyte.recall(
                query=question,
                bank_id=Banks.PRECEDENTS,
                context=context,
                max_results=self._settings.max_precedents,
            )
        except Exception as e:
            _logger.warning("Precedent recall failed: %s — continuing without precedents", e)

        await publish("precedents_ready", {"count": len(precedents)})

        # --- Stage 1: Gather ---
        await set_status(CouncilStatus.stage_1)
        await publish("stage_started", {"stage": 1})

        stage1_responses = await run_gather(
            members=members,
            question=question,
            precedents=precedents,
            llm=self._llm,
            timeout=self._settings.stage1_timeout_seconds,
        )

        await publish("stage1_complete", {
            "responses": [
                {"member_id": r.member_id, "member_name": r.member_name, "content": r.content}
                for r in stage1_responses
            ],
        })

        # --- Stage 2: Rank (skip for solo councils) ---
        await set_status(CouncilStatus.stage_2)
        await publish("stage_started", {"stage": 2})

        if council_type == "solo" or len(stage1_responses) == 1:
            from synapse.council.models import MemberRanking, RankingResult
            label = "A"
            label_map = {f"Response {label}": stage1_responses[0].member_id}
            ranking_result = RankingResult(
                label_map=label_map,
                member_rankings=[
                    MemberRanking(
                        member_id=stage1_responses[0].member_id,
                        member_name=stage1_responses[0].member_name,
                        ranking=[f"Response {label}"],
                        raw_response="",
                    )
                ],
                aggregate_scores={f"Response {label}": 1.0},
                consensus_score=1.0,
            )
        else:
            ranking_result = await run_rank(
                members=members,
                stage1_responses=stage1_responses,
                llm=self._llm,
                timeout=self._settings.stage2_timeout_seconds,
            )

        dissent_detected = self._detect_dissent(ranking_result)
        await publish("stage2_complete", {
            "consensus_score": ranking_result.consensus_score,
            "aggregate_scores": ranking_result.aggregate_scores,
            "dissent_detected": dissent_detected,
        })

        # --- Stage 3: Synthesise ---
        await set_status(CouncilStatus.stage_3)
        await publish("stage_started", {"stage": 3})

        synthesis = await run_synthesise(
            chairman=chairman,
            stage1_responses=stage1_responses,
            ranking_result=ranking_result,
            question=question,
            llm=self._llm,
            timeout=self._settings.stage3_timeout_seconds,
        )

        await publish("stage3_complete", {"verdict": synthesis.verdict, "confidence_label": synthesis.confidence_label})

        # --- Persist to DB ---
        session = await db.get(CouncilSession, session_id)
        if session:
            session.status = CouncilStatus.closed
            session.verdict = synthesis.verdict
            session.consensus_score = ranking_result.consensus_score
            session.confidence_label = synthesis.confidence_label
            session.dissent_detected = dissent_detected
            session.closed_at = datetime.now(timezone.utc)

            transcript = CouncilTranscript(
                council_id=session_id,
                precedents=[{"content": p.content, "score": p.score} for p in precedents],
                stage1_responses=[r.model_dump() for r in stage1_responses],
                stage2_rankings=[r.model_dump() for r in ranking_result.member_rankings],
                aggregate_scores=ranking_result.aggregate_scores,
                stage3_verdict={"verdict": synthesis.verdict, "confidence_label": synthesis.confidence_label},
            )
            db.add(transcript)
            await db.commit()

        # --- Retain to Astrocyte ---
        asyncio.create_task(
            self._retain_to_astrocyte(
                session_id=council_id,
                question=question,
                stage1_responses=stage1_responses,
                synthesis=synthesis,
                consensus_score=ranking_result.consensus_score,
                council_type=council_type,
                topic_tag=topic_tag,
                context=context,
            )
        )

        await publish("session_closed", {"session_id": council_id})

        result = CouncilResult(
            session_id=session_id,
            question=question,
            verdict=synthesis.verdict,
            consensus_score=ranking_result.consensus_score,
            confidence_label=synthesis.confidence_label,
            dissent_detected=dissent_detected,
            stage1_responses=stage1_responses,
            ranking_result=ranking_result,
            synthesis=synthesis,
        )
        return result

    def _detect_dissent(self, ranking_result) -> bool:
        """Flag dissent when any member's ranking significantly diverges from consensus."""
        if len(ranking_result.member_rankings) < 2:
            return False
        # Simple heuristic: consensus_score < 0.4 suggests significant dissent
        return ranking_result.consensus_score < 0.4

    async def _retain_to_astrocyte(
        self,
        session_id: str,
        question: str,
        stage1_responses,
        synthesis,
        consensus_score: float,
        council_type: str,
        topic_tag: str | None,
        context: AstrocyteContext,
    ) -> None:
        """Retain full transcript + verdict summary to Astrocyte. Fire-and-forget."""
        try:
            # Full transcript → councils bank
            full_transcript = (
                f"Council: {question}\n\n"
                + "\n\n".join(
                    f"[{r.member_name}]: {r.content}" for r in stage1_responses
                )
                + f"\n\nVerdict: {synthesis.verdict}"
            )
            await self._astrocyte.retain(
                content=full_transcript,
                bank_id=Banks.COUNCILS,
                tags=council_tags(council_type, topic_tag) + [session_id],
                context=context,
                metadata={"council_id": session_id, "consensus_score": consensus_score},
            )

            # Concise verdict → decisions bank
            verdict_summary = f"Q: {question}\n\nVerdict: {synthesis.verdict}\nConfidence: {synthesis.confidence_label}"
            await self._astrocyte.retain(
                content=verdict_summary,
                bank_id=Banks.DECISIONS,
                tags=verdict_tags(council_type, topic_tag) + [session_id],
                context=context,
                metadata={
                    "council_id": session_id,
                    "consensus_score": consensus_score,
                    "confidence_label": synthesis.confidence_label,
                },
            )
        except Exception as e:
            _logger.error("Failed to retain council %s to Astrocyte: %s", session_id, e)
