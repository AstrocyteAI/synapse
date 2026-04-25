"""Council orchestrator — coordinates stages, publishes events, persists results."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from synapse.council.conflict import check_conflict
from synapse.council.convergence import check_convergence
from synapse.council.models import (
    CouncilMember,
    CouncilResult,
    DeliberationRound,
    MemberCritique,
    StageOneResponse,
)
from synapse.council.stages.critique import run_critique
from synapse.council.stages.gather import run_gather
from synapse.council.stages.rank import run_rank
from synapse.council.stages.red_team import run_red_team
from synapse.council.stages.revise import run_revise
from synapse.council.stages.synthesise import run_synthesise
from synapse.council.thread import append_event, get_thread_by_council
from synapse.db.models import CouncilSession, CouncilStatus, CouncilTranscript, ThreadEventType
from synapse.llm.client import LLMClient
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
        human_turns: list[str] | None = None,
    ) -> CouncilResult:
        """Run the full council pipeline.

        Args:
            human_turns: Mode 2 messages injected by a human participant during
                deliberation. Included verbatim in the transcript retained to the
                ``councils`` Astrocyte bank so future councils can recall not just
                what agents said but also the human context that shaped the session.
        """
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

        await publish(
            "stage1_complete",
            {
                "responses": [
                    {"member_id": r.member_id, "member_name": r.member_name, "content": r.content}
                    for r in stage1_responses
                ],
            },
        )

        # --- Multi-round deliberation (B5) ---
        current_responses = stage1_responses
        deliberation_rounds: list = []

        is_red_team = council_type == "red_team"
        do_deliberation = (
            self._settings.deliberation_enabled
            and len(current_responses) > 1
            and council_type not in ("solo",)
        )

        if is_red_team:
            # Red team: one round of adversarial attacks, no revise phase
            await publish("red_team_started", {})
            attacks = await run_red_team(
                members=members,
                question=question,
                stage1_responses=current_responses,
                llm=self._llm,
                timeout=self._settings.critique_timeout_seconds,
            )
            deliberation_rounds.append(
                {
                    "round": 1,
                    "mode": "red_team",
                    "attacks": [a.model_dump() for a in attacks],
                    "converged": False,
                }
            )
            await publish(
                "red_team_complete",
                {
                    "attacks": [
                        {"member_id": a.member_id, "member_name": a.member_name} for a in attacks
                    ],
                },
            )

        elif do_deliberation:
            max_rounds = self._settings.max_deliberation_rounds
            threshold = self._settings.convergence_threshold

            for round_num in range(1, max_rounds + 1):
                await publish("deliberation_round_started", {"round": round_num})

                # Critique phase
                critiques = await run_critique(
                    members=members,
                    question=question,
                    current_responses=current_responses,
                    llm=self._llm,
                    timeout=self._settings.critique_timeout_seconds,
                )

                # Revise phase
                revised = await run_revise(
                    members=members,
                    question=question,
                    current_responses=current_responses,
                    critiques=critiques,
                    llm=self._llm,
                    timeout=self._settings.revise_timeout_seconds,
                )

                converged = check_convergence(current_responses, revised, threshold)
                current_responses = revised

                deliberation_rounds.append(
                    {
                        "round": round_num,
                        "mode": "deliberation",
                        "critiques": [c.model_dump() for c in critiques],
                        "revised_responses": [r.model_dump() for r in revised],
                        "converged": converged,
                    }
                )

                await publish(
                    "deliberation_round_complete",
                    {
                        "round": round_num,
                        "converged": converged,
                        "revised_count": len(revised),
                    },
                )

                if converged:
                    _logger.info("Council %s converged after round %d", council_id, round_num)
                    break

        # Use the latest (possibly revised) responses for ranking
        final_responses = current_responses

        # --- Stage 2: Rank (skip for solo councils) ---
        await set_status(CouncilStatus.stage_2)
        await publish("stage_started", {"stage": 2})

        if council_type == "solo" or len(final_responses) == 1:
            from synapse.council.models import MemberRanking, RankingResult

            label = "A"
            label_map = {f"Response {label}": final_responses[0].member_id}
            ranking_result = RankingResult(
                label_map=label_map,
                member_rankings=[
                    MemberRanking(
                        member_id=final_responses[0].member_id,
                        member_name=final_responses[0].member_name,
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
                stage1_responses=final_responses,
                llm=self._llm,
                timeout=self._settings.stage2_timeout_seconds,
            )

        dissent_detected = self._detect_dissent(ranking_result)
        await publish(
            "stage2_complete",
            {
                "consensus_score": ranking_result.consensus_score,
                "aggregate_scores": ranking_result.aggregate_scores,
                "dissent_detected": dissent_detected,
            },
        )

        # --- Stage 3: Synthesise ---
        await set_status(CouncilStatus.stage_3)
        await publish("stage_started", {"stage": 3})

        synthesis = await run_synthesise(
            chairman=chairman,
            stage1_responses=final_responses,
            ranking_result=ranking_result,
            question=question,
            llm=self._llm,
            timeout=self._settings.stage3_timeout_seconds,
        )

        await publish(
            "stage3_complete",
            {"verdict": synthesis.verdict, "confidence_label": synthesis.confidence_label},
        )

        # --- Append verdict thread event ---
        thread = await get_thread_by_council(db, session_id)
        if thread:
            verdict_event = await append_event(
                db,
                thread_id=thread.id,
                event_type=ThreadEventType.verdict,
                actor_id="system",
                content=synthesis.verdict,
                metadata={
                    "council_id": council_id,
                    "confidence_label": synthesis.confidence_label,
                    "consensus_score": ranking_result.consensus_score,
                    "dissent_detected": dissent_detected,
                },
            )
            try:
                from synapse.council.thread import thread_event_dict

                await self._centrifugo.publish(
                    f"thread:{thread.id}", thread_event_dict(verdict_event)
                )
            except Exception as e:
                _logger.warning("Failed to publish verdict thread event: %s", e)

        # --- Conflict detection (B6) ---
        conflict_result = await check_conflict(
            verdict=synthesis.verdict,
            question=question,
            precedents=precedents,
            chairman_model_id=chairman.model_id,
            llm=self._llm,
            timeout=30.0,
        )

        if conflict_result.detected and thread:
            conflict_event = await append_event(
                db,
                thread_id=thread.id,
                event_type=ThreadEventType.conflict_detected,
                actor_id="system",
                content=conflict_result.summary
                or "This verdict may conflict with a past decision.",
                metadata={
                    "council_id": council_id,
                    "conflicting_content": conflict_result.conflicting_content,
                    "precedent_score": conflict_result.precedent_score,
                    "new_verdict": synthesis.verdict,
                },
            )
            try:
                from synapse.council.thread import thread_event_dict as _tdict

                await self._centrifugo.publish(f"thread:{thread.id}", _tdict(conflict_event))
            except Exception as e:
                _logger.warning("Failed to publish conflict thread event: %s", e)

        # --- Persist to DB ---
        final_status = (
            CouncilStatus.pending_approval if conflict_result.detected else CouncilStatus.closed
        )
        session = await db.get(CouncilSession, session_id)
        if session:
            session.status = final_status
            session.verdict = synthesis.verdict
            session.consensus_score = ranking_result.consensus_score
            session.confidence_label = synthesis.confidence_label
            session.dissent_detected = dissent_detected
            if final_status == CouncilStatus.closed:
                session.closed_at = datetime.now(UTC)
            if conflict_result.detected:
                session.conflict_metadata = conflict_result.model_dump()

            transcript = CouncilTranscript(
                council_id=session_id,
                round_number=len(deliberation_rounds) + 1,
                precedents=[{"content": p.content, "score": p.score} for p in precedents],
                stage1_responses=[r.model_dump() for r in final_responses],
                stage2_rankings=[r.model_dump() for r in ranking_result.member_rankings],
                aggregate_scores=ranking_result.aggregate_scores,
                stage3_verdict={
                    "verdict": synthesis.verdict,
                    "confidence_label": synthesis.confidence_label,
                },
                deliberation_rounds=deliberation_rounds,
            )
            db.add(transcript)
            await db.commit()

        # --- Retain to Astrocyte ---
        asyncio.create_task(
            self._retain_to_astrocyte(
                session_id=council_id,
                question=question,
                stage1_responses=final_responses,
                synthesis=synthesis,
                consensus_score=ranking_result.consensus_score,
                council_type=council_type,
                topic_tag=topic_tag,
                context=context,
                human_turns=human_turns or [],
            )
        )

        if final_status == CouncilStatus.closed:
            await publish("session_closed", {"session_id": council_id})
        else:
            await publish(
                "pending_approval",
                {
                    "session_id": council_id,
                    "conflict_summary": conflict_result.summary,
                },
            )

        result = CouncilResult(
            session_id=session_id,
            question=question,
            verdict=synthesis.verdict,
            consensus_score=ranking_result.consensus_score,
            confidence_label=synthesis.confidence_label,
            dissent_detected=dissent_detected,
            stage1_responses=final_responses,
            ranking_result=ranking_result,
            synthesis=synthesis,
            deliberation_rounds=[
                DeliberationRound(
                    round=rd["round"],
                    critiques=[
                        MemberCritique(**c) for c in rd.get("critiques", rd.get("attacks", []))
                    ],
                    revised_responses=[
                        StageOneResponse(**r) for r in rd.get("revised_responses", [])
                    ],
                    converged=rd.get("converged", False),
                )
                for rd in deliberation_rounds
            ],
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
        human_turns: list[str] | None = None,
    ) -> None:
        """Retain full transcript + verdict summary to Astrocyte. Fire-and-forget.

        The transcript written to the ``councils`` bank includes human turns
        (Mode 2 messages) so future councils can recall the full deliberation
        context — not just what agents said, but what the human contributed.

        Reflection events (Mode 3 Q&A) are retained separately by the chat
        router at the point they occur, not here.
        """
        try:
            # Full transcript → councils bank
            # Human turns are interleaved before agent responses so the
            # semantic embedding captures the full deliberation context.
            parts = [f"Council: {question}"]
            if human_turns:
                parts.append("\n".join(f"[Human]: {msg}" for msg in human_turns))
            parts.extend(f"[{r.member_name}]: {r.content}" for r in stage1_responses)
            parts.append(f"Verdict: {synthesis.verdict}")
            full_transcript = "\n\n".join(parts)
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
