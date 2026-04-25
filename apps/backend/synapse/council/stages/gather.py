"""Stage 1: Gather — parallel member queries with precedents injected."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from synapse.council.models import CouncilMember, StageOneResponse
    from synapse.llm.client import LLMClient
    from synapse.memory.gateway_client import MemoryHit

_logger = logging.getLogger(__name__)

_STAGE1_SYSTEM_PROMPT = """\
You are {name}, a council member participating in a structured deliberation.
{role_line}
Your task: provide a thorough, well-reasoned response to the question below.
Be direct. Do not hedge excessively. State your recommendation clearly.
{precedents_section}"""

_PRECEDENTS_SECTION = """\

Relevant past decisions that may inform your response:
{formatted_precedents}
Consider these precedents — agree, disagree, or build on them with clear reasoning."""


def _format_precedents(precedents: list[MemoryHit]) -> str:
    if not precedents:
        return ""
    lines = []
    for i, hit in enumerate(precedents, 1):
        lines.append(f"{i}. {hit.content[:500]}")
    return _PRECEDENTS_SECTION.format(formatted_precedents="\n".join(lines))


def _build_system_prompt(member: CouncilMember, precedents: list[MemoryHit]) -> str:
    from synapse.llm.client import derive_display_name

    name = member.name or derive_display_name(member.model_id)
    role_line = f"Your role in this council: {member.role}" if member.role else ""

    if member.system_prompt_override:
        return member.system_prompt_override

    return _STAGE1_SYSTEM_PROMPT.format(
        name=name,
        role_line=role_line,
        precedents_section=_format_precedents(precedents),
    ).strip()


async def _query_member(
    member: CouncilMember,
    question: str,
    precedents: list[MemoryHit],
    llm: LLMClient,
    timeout: float,
) -> StageOneResponse:
    from synapse.council.models import StageOneResponse
    from synapse.llm.client import derive_display_name

    name = member.name or derive_display_name(member.model_id)
    system_prompt = _build_system_prompt(member, precedents)

    try:
        content = await asyncio.wait_for(
            llm.complete(
                model=member.model_id,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
            ),
            timeout=timeout,
        )
        return StageOneResponse(member_id=member.model_id, member_name=name, content=content)
    except TimeoutError:
        _logger.warning("Member %s timed out in Stage 1", member.model_id)
        return StageOneResponse(
            member_id=member.model_id, member_name=name, content="", error="timeout"
        )
    except Exception as e:
        _logger.warning("Member %s failed in Stage 1: %s", member.model_id, e)
        return StageOneResponse(
            member_id=member.model_id, member_name=name, content="", error=str(e)
        )


async def run_gather(
    members: list[CouncilMember],
    question: str,
    precedents: list[MemoryHit],
    llm: LLMClient,
    timeout: float = 60.0,
) -> list[StageOneResponse]:
    """
    Query all council members in parallel.

    Graceful degradation: failed members are excluded from the result.
    Raises if all members fail.
    """
    tasks = [_query_member(m, question, precedents, llm, timeout) for m in members]
    results = await asyncio.gather(*tasks)

    successful = [r for r in results if not r.error]
    if not successful:
        errors = {r.member_name: r.error for r in results}
        raise RuntimeError(f"All council members failed in Stage 1: {errors}")

    failed_count = len(results) - len(successful)
    if failed_count:
        _logger.warning("%d member(s) failed in Stage 1 — continuing with %d", failed_count, len(successful))

    return successful
