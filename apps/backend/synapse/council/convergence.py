"""Convergence detection for multi-round deliberation.

Measures how much each member's response changed between consecutive rounds
using word-level Jaccard similarity.  If the average similarity across all
members exceeds ``threshold``, responses have stabilised — no further rounds
are needed.

Jaccard similarity: |intersection| / |union| of word sets.
Range: 0.0 (completely different) – 1.0 (identical).
A threshold of 0.72 means ~72 % of vocabulary overlap — practically the same
argument, just slightly reworded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import StageOneResponse


_PUNCT = str.maketrans("", "", ".,;:!?\"'()[]{}'")


def _word_set(text: str) -> set[str]:
    """Lower-case word tokens, stripping punctuation."""
    return {w.translate(_PUNCT) for w in text.lower().split() if w.translate(_PUNCT)}


def jaccard(text1: str, text2: str) -> float:
    """Word-level Jaccard similarity between two texts."""
    a = _word_set(text1)
    b = _word_set(text2)
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def check_convergence(
    prev_responses: list[StageOneResponse],
    new_responses: list[StageOneResponse],
    threshold: float = 0.72,
) -> bool:
    """Return True if responses have converged (average Jaccard ≥ threshold).

    Only members present in *both* lists are compared.  If there are no
    comparable pairs, returns False (keep going).
    """
    prev_by_id = {r.member_id: r.content for r in prev_responses}
    similarities: list[float] = []

    for resp in new_responses:
        prev_content = prev_by_id.get(resp.member_id)
        if prev_content is not None and resp.content:
            similarities.append(jaccard(prev_content, resp.content))

    if not similarities:
        return False

    avg = sum(similarities) / len(similarities)
    return avg >= threshold
