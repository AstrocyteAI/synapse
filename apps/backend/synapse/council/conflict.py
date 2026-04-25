"""Conflict detection — check whether a new verdict contradicts past precedents.

Only runs when high-similarity precedents (score > SIMILARITY_THRESHOLD) exist.
Uses the chairman's model for the LLM assessment so the same arbiter that
produced the verdict also evaluates the conflict.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import ConflictResult
    from synapse.llm.client import LLMClient
    from synapse.memory.gateway_client import MemoryHit

_logger = logging.getLogger(__name__)

# Only consider precedents above this similarity score for conflict checking.
# Below this threshold the match is likely coincidental rather than topically related.
SIMILARITY_THRESHOLD = 0.75

_CONFLICT_SYSTEM_PROMPT = """\
You are a conflict analyst. A council has just reached a verdict on a question.
Your task: determine whether this new verdict CONTRADICTS any of the listed past decisions.

A contradiction means the new verdict recommends something that directly conflicts with
what was previously decided — not merely a different emphasis or updated context.

New verdict:
{verdict}

Original question: {question}

Past decisions to check against:
{precedents}

Does this new verdict contradict any past decision?
Answer EXACTLY with one of:
  CONFLICT: YES
  CONFLICT: NO

If YES, add one sentence explaining which past decision is contradicted and why."""

_YES_RE = re.compile(r"CONFLICT\s*:\s*YES", re.IGNORECASE)
_NO_RE = re.compile(r"CONFLICT\s*:\s*NO", re.IGNORECASE)


def _format_precedents(hits: list[MemoryHit]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"{i}. [score {h.score:.2f}] {h.content[:600]}")
    return "\n\n".join(parts)


def _extract_summary(raw: str) -> str | None:
    """Pull the explanation after the CONFLICT: YES line."""
    lines = raw.strip().splitlines()
    explanation_lines = []
    found_yes = False
    for line in lines:
        stripped = line.strip()
        if _YES_RE.search(stripped):
            found_yes = True
            continue
        if found_yes and stripped:
            explanation_lines.append(stripped)
    return " ".join(explanation_lines).strip() or None


async def check_conflict(
    verdict: str,
    question: str,
    precedents: list[MemoryHit],
    chairman_model_id: str,
    llm: LLMClient,
    timeout: float = 30.0,
) -> ConflictResult:
    """Return a ConflictResult.

    Short-circuits to ``detected=False`` when no high-similarity precedents
    exist — avoids unnecessary LLM calls for novel questions.
    """
    import asyncio

    from synapse.council.models import ConflictResult

    # Filter to high-similarity matches only
    relevant = [h for h in precedents if h.score >= SIMILARITY_THRESHOLD]
    if not relevant:
        return ConflictResult(detected=False)

    formatted = _format_precedents(relevant)
    system = _CONFLICT_SYSTEM_PROMPT.format(
        verdict=verdict,
        question=question,
        precedents=formatted,
    ).strip()

    try:
        raw = await asyncio.wait_for(
            llm.complete(
                model=chairman_model_id,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": "Please assess now."},
                ],
                temperature=0.1,
                max_tokens=256,
            ),
            timeout=timeout,
        )
    except Exception as e:
        _logger.warning("Conflict check failed: %s — treating as no conflict", e)
        return ConflictResult(detected=False)

    if _YES_RE.search(raw):
        # Find the best matching (highest score) precedent as the primary conflict
        best = max(relevant, key=lambda h: h.score)
        return ConflictResult(
            detected=True,
            summary=_extract_summary(raw),
            conflicting_content=best.content[:800],
            precedent_score=best.score,
        )

    return ConflictResult(detected=False)
