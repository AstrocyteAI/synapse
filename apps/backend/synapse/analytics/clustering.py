"""Topic clustering via Astrocyte reflect."""

from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


async def cluster_topics(astrocyte, context, topic_tags: list[str]) -> dict:
    """Summarise a list of topic_tags into semantic clusters via Astrocyte.

    Returns ``{"clusters": <answer string>, "sources": [...]}``.
    If *topic_tags* is empty or Astrocyte raises, returns an empty result.
    """
    if not topic_tags:
        return {"clusters": "", "sources": []}

    tag_list = "\n".join(f"- {tag}" for tag in topic_tags)
    prompt = (
        "You are a strategic analyst. "
        "The following topic tags come from a deliberation system. "
        "Group them into meaningful semantic clusters and briefly describe each cluster.\n\n"
        f"Topic tags:\n{tag_list}"
    )

    try:
        from synapse.memory.banks import Banks

        result = await astrocyte.reflect(
            query=prompt,
            bank_id=Banks.COUNCILS,
            context=context,
        )
        return {
            "clusters": result.answer if result else "",
            "sources": result.sources if result else [],
        }
    except Exception:
        _logger.warning("cluster_topics: astrocyte.reflect failed", exc_info=True)
        return {"clusters": "", "sources": []}
