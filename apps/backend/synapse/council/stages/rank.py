"""Stage 2: Rank — anonymised peer review and aggregate scoring."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import CouncilMember, MemberRanking, RankingResult, StageOneResponse
    from synapse.llm.client import LLMClient

_logger = logging.getLogger(__name__)

_STAGE2_SYSTEM_PROMPT = """\
You are reviewing anonymous responses from a council deliberation.
Your task: rank these responses from best to worst based on quality, reasoning, and usefulness.

{responses_text}

Evaluate each response on:
- Clarity and directness of the recommendation
- Quality of reasoning and evidence
- Practical applicability
- Completeness

You MUST end your response with a FINAL RANKING section in exactly this format:
FINAL RANKING:
1. Response X
2. Response Y
3. Response Z
(list all responses in order from best to worst)"""


def _anonymise(responses: list[StageOneResponse]) -> tuple[list[dict], dict[str, str]]:
    """Assign labels A, B, C… and return the anonymised list and reverse map."""
    labels = [chr(65 + i) for i in range(len(responses))]
    anonymised = [
        {"label": f"Response {label}", "content": resp.content}
        for label, resp in zip(labels, responses, strict=True)
    ]
    label_map = {
        f"Response {label}": resp.member_id for label, resp in zip(labels, responses, strict=True)
    }
    return anonymised, label_map


def _format_responses(anonymised: list[dict]) -> str:
    parts = []
    for item in anonymised:
        parts.append(f"--- {item['label']} ---\n{item['content']}\n")
    return "\n".join(parts)


def _parse_ranking(text: str, labels: list[str]) -> list[str]:
    """
    Extract ordered labels from FINAL RANKING section.
    Falls back to scanning the full response for 'Response X' patterns.
    """
    # Try to extract the FINAL RANKING: section
    match = re.search(r"FINAL RANKING:\s*(.*?)(?:\n\n|\Z)", text, re.DOTALL | re.IGNORECASE)
    section = match.group(1) if match else text

    # Match labels in the order they appear in the text (not alphabetical label order)
    label_alts = "|".join(re.escape(lbl) for lbl in labels)
    pattern = re.compile(rf"\bResponse\s+({label_alts})\b", re.IGNORECASE)

    found: list[str] = []
    for m in pattern.finditer(section):
        entry = f"Response {m.group(1).upper()}"
        if entry not in found:
            found.append(entry)

    # Fill in any missing labels at the end (parser fallback)
    for lbl in labels:
        if f"Response {lbl}" not in found:
            found.append(f"Response {lbl}")

    return found


def _compute_aggregate_scores(
    member_rankings: list[MemberRanking],
    labels: list[str],
) -> dict[str, float]:
    """
    Compute mean rank position per response label.
    Lower score = higher ranked (rank 1 is best).
    """
    rank_sums: dict[str, float] = {f"Response {lbl}": 0.0 for lbl in labels}
    count: dict[str, int] = {f"Response {lbl}": 0 for lbl in labels}

    for mr in member_rankings:
        for position, label in enumerate(mr.ranking, start=1):
            if label in rank_sums:
                rank_sums[label] += position
                count[label] += 1

    return {
        label: (rank_sums[label] / count[label]) if count[label] else float(len(labels))
        for label in rank_sums
    }


def _compute_kendalls_w(member_rankings: list[MemberRanking], labels: list[str]) -> float:
    """
    Kendall's W (coefficient of concordance) — measure of inter-rater agreement.
    Returns 0.0 (no agreement) to 1.0 (perfect agreement).
    """
    m = len(member_rankings)  # number of raters
    n = len(labels)  # number of items

    if m < 2 or n < 2:
        return 1.0  # trivial case

    # Rank sums for each label across all raters
    rank_sums: dict[str, float] = {f"Response {lbl}": 0.0 for lbl in labels}
    for mr in member_rankings:
        for position, label in enumerate(mr.ranking, start=1):
            if label in rank_sums:
                rank_sums[label] += position

    mean_rank_sum = m * (n + 1) / 2
    s = sum((rs - mean_rank_sum) ** 2 for rs in rank_sums.values())
    denominator = m**2 * (n**3 - n) / 12

    return round(s / denominator, 4) if denominator > 0 else 0.0


async def _rank_member(
    member: CouncilMember,
    anonymised: list[dict],
    labels: list[str],
    llm: LLMClient,
    timeout: float,
) -> MemberRanking | None:
    from synapse.council.models import MemberRanking
    from synapse.llm.client import derive_display_name

    name = member.name or derive_display_name(member.model_id)
    responses_text = _format_responses(anonymised)

    try:
        raw = await asyncio.wait_for(
            llm.complete(
                model=member.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": _STAGE2_SYSTEM_PROMPT.format(responses_text=responses_text),
                    },
                    {
                        "role": "user",
                        "content": "Please provide your ranking now.",
                    },
                ],
                temperature=0.3,  # lower temp for more consistent structured output
            ),
            timeout=timeout,
        )
        ranking = _parse_ranking(raw, labels)
        return MemberRanking(
            member_id=member.model_id,
            member_name=name,
            ranking=ranking,
            raw_response=raw,
        )
    except Exception as e:
        _logger.warning("Member %s failed in Stage 2: %s", member.model_id, e)
        return None


async def run_rank(
    members: list[CouncilMember],
    stage1_responses: list[StageOneResponse],
    llm: LLMClient,
    timeout: float = 60.0,
) -> RankingResult:
    """Anonymise Stage 1 responses and run parallel peer ranking."""
    from synapse.council.models import RankingResult

    anonymised, label_map = _anonymise(stage1_responses)
    labels = [chr(65 + i) for i in range(len(stage1_responses))]

    tasks = [_rank_member(m, anonymised, labels, llm, timeout) for m in members]
    results = await asyncio.gather(*tasks)

    valid_rankings = [r for r in results if r is not None]
    if not valid_rankings:
        # All members failed ranking — use identity order as fallback
        _logger.warning("All members failed Stage 2 — using identity ranking")
        from synapse.council.models import MemberRanking

        valid_rankings = [
            MemberRanking(
                member_id="fallback",
                member_name="Fallback",
                ranking=[f"Response {lbl}" for lbl in labels],
                raw_response="",
            )
        ]

    aggregate_scores = _compute_aggregate_scores(valid_rankings, labels)
    consensus_score = _compute_kendalls_w(valid_rankings, labels)

    return RankingResult(
        label_map=label_map,
        member_rankings=valid_rankings,
        aggregate_scores=aggregate_scores,
        consensus_score=consensus_score,
    )
