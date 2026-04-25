"""Deliberation Stage — Critique.

Each member receives the other members' current responses (anonymised) and
writes a critical analysis.  This runs between Stage 1 gather and the revise
stage in each deliberation round.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import CouncilMember, MemberCritique, StageOneResponse
    from synapse.llm.client import LLMClient

_logger = logging.getLogger(__name__)

_CRITIQUE_SYSTEM_PROMPT = """\
You are {name}, a council member reviewing other members' positions.
{role_line}

The council is deliberating on: {question}

Here are the other members' current responses (anonymised):
{other_responses}

Your task: provide a critical analysis of these responses.
- Identify specific weaknesses, gaps, or flawed assumptions.
- Note what they got right and why.
- Suggest what important considerations they may have missed.
Be constructive but rigorous. Keep your critique under 250 words."""


def _format_other_responses(
    member_id: str,
    responses: list[StageOneResponse],
) -> str:
    """Return all responses *except* the current member's, labelled A, B, …"""
    others = [r for r in responses if r.member_id != member_id]
    if not others:
        return "(no other responses yet)"
    parts = []
    for i, resp in enumerate(others):
        label = chr(65 + i)
        parts.append(f"Response {label}:\n{resp.content}")
    return "\n\n".join(parts)


async def _critique_member(
    member: CouncilMember,
    question: str,
    current_responses: list[StageOneResponse],
    llm: LLMClient,
    timeout: float,
) -> MemberCritique:
    from synapse.council.models import MemberCritique
    from synapse.llm.client import derive_display_name

    name = member.name or derive_display_name(member.model_id)
    role_line = f"Your role in this council: {member.role}" if member.role else ""
    other_responses = _format_other_responses(member.model_id, current_responses)

    system = _CRITIQUE_SYSTEM_PROMPT.format(
        name=name,
        role_line=role_line,
        question=question,
        other_responses=other_responses,
    ).strip()

    try:
        critique_text = await asyncio.wait_for(
            llm.complete(
                model=member.model_id,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": "Please provide your critique now."},
                ],
                temperature=0.5,
            ),
            timeout=timeout,
        )
        return MemberCritique(
            member_id=member.model_id,
            member_name=name,
            critique=critique_text,
        )
    except Exception as e:
        _logger.warning("Member %s failed critique: %s", member.model_id, e)
        return MemberCritique(
            member_id=member.model_id,
            member_name=name,
            critique="",
            error=str(e),
        )


async def run_critique(
    members: list[CouncilMember],
    question: str,
    current_responses: list[StageOneResponse],
    llm: LLMClient,
    timeout: float = 60.0,
) -> list[MemberCritique]:
    """Each member critiques the other members' current responses in parallel."""
    tasks = [
        _critique_member(m, question, current_responses, llm, timeout) for m in members
    ]
    return list(await asyncio.gather(*tasks))
