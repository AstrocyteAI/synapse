"""Deliberation Stage — Revise.

Each member receives their own previous response and the critiques written by
other members, then produces a revised response.  This closes one deliberation
round (critique → revise).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import CouncilMember, MemberCritique, StageOneResponse
    from synapse.llm.client import LLMClient

_logger = logging.getLogger(__name__)

_REVISE_SYSTEM_PROMPT = """\
You are {name}, a council member who has just reviewed critiques of the ongoing deliberation.
{role_line}

Original question: {question}

Your previous response:
{own_response}

Critiques from other council members (anonymised):
{critiques}

Your task: revise your response in light of these critiques.
- Acknowledge valid criticisms and update your position accordingly.
- Defend positions you still believe are correct, with clear reasoning.
- Do not merely repeat your previous answer — genuinely engage with the feedback.
- Keep your revised response under 400 words and end with a clear recommendation."""


def _format_critiques(
    member_id: str,
    critiques: list[MemberCritique],
) -> str:
    """Return critiques from all members *except* the current one."""
    others = [c for c in critiques if c.member_id != member_id and not c.error and c.critique]
    if not others:
        return "(no critiques received)"
    parts = []
    for i, c in enumerate(others):
        label = chr(65 + i)
        parts.append(f"Critique {label}:\n{c.critique}")
    return "\n\n".join(parts)


async def _revise_member(
    member: CouncilMember,
    question: str,
    own_response: str,
    critiques: list[MemberCritique],
    llm: LLMClient,
    timeout: float,
) -> StageOneResponse:
    from synapse.council.models import StageOneResponse
    from synapse.llm.client import derive_display_name

    name = member.name or derive_display_name(member.model_id)
    role_line = f"Your role in this council: {member.role}" if member.role else ""
    formatted_critiques = _format_critiques(member.model_id, critiques)

    system = _REVISE_SYSTEM_PROMPT.format(
        name=name,
        role_line=role_line,
        question=question,
        own_response=own_response,
        critiques=formatted_critiques,
    ).strip()

    try:
        revised = await asyncio.wait_for(
            llm.complete(
                model=member.model_id,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": "Please provide your revised response now."},
                ],
                temperature=0.45,
            ),
            timeout=timeout,
        )
        return StageOneResponse(member_id=member.model_id, member_name=name, content=revised)
    except Exception as e:
        _logger.warning("Member %s failed revise: %s", member.model_id, e)
        # On failure, keep the previous response unchanged
        return StageOneResponse(
            member_id=member.model_id, member_name=name, content=own_response, error=str(e)
        )


async def run_revise(
    members: list[CouncilMember],
    question: str,
    current_responses: list[StageOneResponse],
    critiques: list[MemberCritique],
    llm: LLMClient,
    timeout: float = 60.0,
) -> list[StageOneResponse]:
    """Each member revises their response given critiques from peers."""
    # Build a lookup: member_id → current response content
    response_by_member = {r.member_id: r.content for r in current_responses}

    tasks = [
        _revise_member(
            member=m,
            question=question,
            own_response=response_by_member.get(m.model_id, ""),
            critiques=critiques,
            llm=llm,
            timeout=timeout,
        )
        for m in members
    ]
    return list(await asyncio.gather(*tasks))
