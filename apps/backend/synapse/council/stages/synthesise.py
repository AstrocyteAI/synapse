"""Stage 3: Synthesise — chairman produces the final verdict."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import (
        CouncilMember,
        RankingResult,
        StageOneResponse,
        SynthesisResult,
    )
    from synapse.llm.client import LLMClient

_logger = logging.getLogger(__name__)

_STAGE3_SYSTEM_PROMPT = """\
You are the chairman of a deliberative council. Your task is to synthesise the council's \
collective reasoning into a single authoritative verdict.

You have received the following anonymous responses from council members, ordered by \
peer-ranking score (highest ranked first):

{ranked_responses}

Guidelines:
- State a clear recommendation or decision.
- Explain the key reasoning that led to it.
- Acknowledge significant dissenting views where they exist.
- If important aspects are genuinely uncertain, mark them with [UNCERTAIN].
- Be concise (under 400 words) but complete.

End your response with:
CONFIDENCE: HIGH | MEDIUM | LOW
(choose HIGH if there was strong consensus, MEDIUM if partial, LOW if members diverged significantly)"""


def _rank_responses_for_chairman(
    stage1_responses: list[StageOneResponse],
    ranking_result: RankingResult,
) -> str:
    """
    Present Stage 1 responses in aggregate rank order to the chairman.
    Labels remain anonymous — chairman never sees which model wrote what.
    """
    # Sort labels by aggregate score (lower = better rank)
    sorted_labels = sorted(
        ranking_result.aggregate_scores.keys(),
        key=lambda lbl: ranking_result.aggregate_scores[lbl],
    )

    # Map label -> response content
    label_to_content: dict[str, str] = {}
    labels = [chr(65 + i) for i in range(len(stage1_responses))]
    for label, resp in zip(labels, stage1_responses, strict=True):
        label_to_content[f"Response {label}"] = resp.content

    parts = []
    for rank, label in enumerate(sorted_labels, 1):
        score = ranking_result.aggregate_scores[label]
        content = label_to_content.get(label, "")
        parts.append(f"[Rank #{rank}, avg rank score {score:.2f}]\n{label}:\n{content}\n")

    return "\n".join(parts)


def _extract_confidence(text: str) -> str:
    match = re.search(r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", text, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    # Heuristic fallback from verdict text
    lower = text.lower()
    if "strongly recommend" in lower or "clearly" in lower:
        return "high"
    if "uncertain" in lower or "[uncertain]" in lower:
        return "low"
    return "medium"


def _extract_uncertainty_markers(text: str) -> list[str]:
    return re.findall(r"\[UNCERTAIN\][^\n]*", text, re.IGNORECASE)


def _strip_confidence_footer(text: str) -> str:
    return re.sub(r"\s*CONFIDENCE:\s*(HIGH|MEDIUM|LOW)\s*$", "", text, flags=re.IGNORECASE).strip()


async def run_synthesise(
    chairman: CouncilMember,
    stage1_responses: list[StageOneResponse],
    ranking_result: RankingResult,
    question: str,
    llm: LLMClient,
    timeout: float = 90.0,
) -> SynthesisResult:
    """Chairman synthesises final verdict from Stage 1 responses and Stage 2 rankings."""
    import asyncio

    from synapse.council.models import SynthesisResult

    ranked_responses = _rank_responses_for_chairman(stage1_responses, ranking_result)

    raw = await asyncio.wait_for(
        llm.complete(
            model=chairman.model_id,
            messages=[
                {
                    "role": "system",
                    "content": _STAGE3_SYSTEM_PROMPT.format(ranked_responses=ranked_responses),
                },
                {
                    "role": "user",
                    "content": f"Original question: {question}\n\nPlease provide your synthesis now.",
                },
            ],
            temperature=0.5,
            max_tokens=1024,
        ),
        timeout=timeout,
    )

    confidence_label = _extract_confidence(raw)
    uncertainty_markers = _extract_uncertainty_markers(raw)
    verdict_text = _strip_confidence_footer(raw)

    return SynthesisResult(
        verdict=verdict_text,
        confidence_label=confidence_label,
        uncertainty_markers=uncertainty_markers,
    )
