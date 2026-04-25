"""Deliberation Stage — Red Team.

In red-team mode members act as adversaries rather than neutral deliberators.
Each member attacks the *other* members' proposed answers, looking for fatal
flaws, hidden assumptions, and failure modes.

There is no revise phase and no convergence check.  The output is a risk
surface rather than a refined recommendation.  Stage 3 synthesis still runs
— the chairman summarises the attack findings into a final risk verdict.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import CouncilMember, MemberCritique, StageOneResponse
    from synapse.llm.client import LLMClient

_logger = logging.getLogger(__name__)

_RED_TEAM_SYSTEM_PROMPT = """\
You are {name}, an adversarial analyst on a red team.
{role_line}

Question under review: {question}

Proposed solutions from other analysts (anonymised):
{other_responses}

Your task: attack these proposals ruthlessly.
- Find every way they could fail, be exploited, or go wrong.
- Identify hidden assumptions that, if wrong, would sink the plan.
- Point out what the authors overlooked or underweighted.
- Do NOT propose alternatives — your job is to expose weaknesses.
Be specific, not vague. Keep your attack under 300 words."""


def _format_targets(member_id: str, responses: list[StageOneResponse]) -> str:
    others = [r for r in responses if r.member_id != member_id]
    if not others:
        return "(no other responses to attack)"
    parts = []
    for i, resp in enumerate(others):
        label = chr(65 + i)
        parts.append(f"Proposal {label}:\n{resp.content}")
    return "\n\n".join(parts)


async def _attack_member(
    member: CouncilMember,
    question: str,
    responses: list[StageOneResponse],
    llm: LLMClient,
    timeout: float,
) -> MemberCritique:
    from synapse.council.models import MemberCritique
    from synapse.llm.client import derive_display_name

    name = member.name or derive_display_name(member.model_id)
    role_line = f"Your adversarial role: {member.role}" if member.role else ""
    targets = _format_targets(member.model_id, responses)

    system = _RED_TEAM_SYSTEM_PROMPT.format(
        name=name,
        role_line=role_line,
        question=question,
        other_responses=targets,
    ).strip()

    try:
        attack = await asyncio.wait_for(
            llm.complete(
                model=member.model_id,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": "Launch your attack now."},
                ],
                temperature=0.65,
            ),
            timeout=timeout,
        )
        return MemberCritique(
            member_id=member.model_id,
            member_name=name,
            critique=attack,
        )
    except Exception as e:
        _logger.warning("Red team member %s failed: %s", member.model_id, e)
        return MemberCritique(
            member_id=member.model_id,
            member_name=name,
            critique="",
            error=str(e),
        )


async def run_red_team(
    members: list[CouncilMember],
    question: str,
    stage1_responses: list[StageOneResponse],
    llm: LLMClient,
    timeout: float = 60.0,
) -> list[MemberCritique]:
    """Each red-team member attacks the other members' Stage 1 proposals in parallel."""
    tasks = [
        _attack_member(m, question, stage1_responses, llm, timeout) for m in members
    ]
    return list(await asyncio.gather(*tasks))
