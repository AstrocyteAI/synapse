"""Astrocyte bank name constants and MIP tag helpers."""

from __future__ import annotations


class Banks:
    COUNCILS = "councils"  # Full session transcripts (audit record)
    DECISIONS = "decisions"  # Concise extracted verdicts (searchable)
    PRECEDENTS = "precedents"  # Curated promoted decisions (pre-Stage 1 injection)
    AGENTS = "agents"  # Per-agent context and identity


def council_tags(council_type: str, topic_tag: str | None = None) -> list[str]:
    tags = ["council", council_type]
    if topic_tag:
        tags.append(topic_tag)
    return tags


def verdict_tags(council_type: str, topic_tag: str | None = None) -> list[str]:
    tags = ["verdict", council_type]
    if topic_tag:
        tags.append(topic_tag)
    return tags
