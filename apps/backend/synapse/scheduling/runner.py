"""ScheduledCouncilRunner — lightweight asyncio-based scheduler for B7.

Persists nothing beyond the ``run_at`` column already on ``CouncilSession``.
On app startup, :func:`restore_from_db` queries all ``scheduled`` sessions
and re-registers them.  In-flight tasks are cancelled on shutdown.

For recurring (cron) councils — a future addition — this module will grow a
``schedule_cron`` entry point; the asyncio Task approach works there too
(sleep-based retry loop).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

_logger = logging.getLogger(__name__)


class ScheduledCouncilRunner:
    """Holds asyncio Tasks, one per scheduled council.

    Each task sleeps until ``run_at`` then fires the orchestrator.
    Tasks clean themselves up on completion or cancellation.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule(self, app, session_id: uuid.UUID, run_at: datetime) -> None:
        """Register a future council run.  No-ops if already scheduled."""
        key = str(session_id)
        if key in self._tasks and not self._tasks[key].done():
            return
        task = asyncio.create_task(
            self._sleep_then_run(app, session_id, run_at),
            name=f"scheduled-council-{key}",
        )
        self._tasks[key] = task

    def schedule_resume(self, app, session_id: uuid.UUID, run_at: datetime) -> None:
        """Schedule a :meth:`CouncilOrchestrator.resume` call at *run_at*.

        Used by B3 to enforce ``contribution_deadline``.
        """
        key = f"resume-{session_id}"
        if key in self._tasks and not self._tasks[key].done():
            return
        task = asyncio.create_task(
            self._sleep_then_resume(app, session_id, run_at),
            name=f"resume-council-{session_id}",
        )
        self._tasks[key] = task

    def cancel(self, session_id: uuid.UUID) -> None:
        """Cancel a pending run task (e.g. council was deleted)."""
        for prefix in ("", "resume-"):
            key = f"{prefix}{session_id}"
            task = self._tasks.pop(key, None)
            if task and not task.done():
                task.cancel()

    async def shutdown(self) -> None:
        """Cancel all pending tasks and wait for them to finish."""
        tasks = [t for t in self._tasks.values() if not t.done()]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _sleep_then_run(self, app, session_id: uuid.UUID, run_at: datetime) -> None:
        key = str(session_id)
        try:
            delay = (run_at - datetime.now(UTC)).total_seconds()
            if delay > 0:
                _logger.info("Scheduled council %s will fire in %.0f s", session_id, delay)
                await asyncio.sleep(delay)
            await _fire_council(app, session_id)
        except asyncio.CancelledError:
            _logger.info("Scheduled council %s was cancelled", session_id)
        finally:
            self._tasks.pop(key, None)

    async def _sleep_then_resume(self, app, session_id: uuid.UUID, run_at: datetime) -> None:
        key = f"resume-{session_id}"
        try:
            delay = (run_at - datetime.now(UTC)).total_seconds()
            if delay > 0:
                _logger.info("Async council %s deadline resume in %.0f s", session_id, delay)
                await asyncio.sleep(delay)
            await _fire_resume(app, session_id)
        except asyncio.CancelledError:
            _logger.info("Async council %s deadline resume was cancelled", session_id)
        finally:
            self._tasks.pop(key, None)


# ---------------------------------------------------------------------------
# Fire helpers — standalone async functions so they can be tested independently
# ---------------------------------------------------------------------------


async def _fire_council(app, session_id: uuid.UUID) -> None:
    """Run a scheduled council — called when run_at fires."""
    from synapse.council.models import CouncilMember
    from synapse.council.orchestrator import CouncilOrchestrator
    from synapse.council.session import mark_failed
    from synapse.db.models import CouncilSession, CouncilStatus
    from synapse.llm.client import LLMClient
    from synapse.memory.context import AstrocyteContext

    _logger.info("Firing scheduled council %s", session_id)
    async with app.state.sessionmaker() as db:
        session = await db.get(CouncilSession, session_id)
        if not session or session.status != CouncilStatus.scheduled:
            _logger.warning(
                "Scheduled fire: session %s not found or wrong status (%s)",
                session_id,
                getattr(session, "status", "missing"),
            )
            return

        members = [CouncilMember(**m) for m in session.members]
        chairman = CouncilMember(**session.chairman)
        context = AstrocyteContext(
            principal=session.created_by,
            tenant_id=session.tenant_id,
        )

        orchestrator = CouncilOrchestrator(
            astrocyte=app.state.astrocyte,
            centrifugo=app.state.centrifugo,
            llm=LLMClient(app.state.settings),
            settings=app.state.settings,
        )
        try:
            await orchestrator.run(
                session_id=session_id,
                question=session.question,
                members=members,
                chairman=chairman,
                context=context,
                db=db,
                council_type=session.council_type,
                topic_tag=session.topic_tag,
            )
        except Exception as exc:
            _logger.error("Scheduled council %s failed: %s", session_id, exc)
            async with app.state.sessionmaker() as err_db:
                await mark_failed(err_db, session_id, error=str(exc))


async def _fire_resume(app, session_id: uuid.UUID) -> None:
    """Resume an async council when its contribution deadline has passed."""
    from synapse.council.orchestrator import CouncilOrchestrator
    from synapse.council.session import mark_failed
    from synapse.db.models import CouncilSession, CouncilStatus
    from synapse.llm.client import LLMClient

    _logger.info("Deadline resume for async council %s", session_id)
    async with app.state.sessionmaker() as db:
        session = await db.get(CouncilSession, session_id)
        if not session or session.status != CouncilStatus.waiting_contributions:
            return

        orchestrator = CouncilOrchestrator(
            astrocyte=app.state.astrocyte,
            centrifugo=app.state.centrifugo,
            llm=LLMClient(app.state.settings),
            settings=app.state.settings,
        )
        try:
            await orchestrator.resume(session_id, db)
        except Exception as exc:
            _logger.error("Deadline resume for council %s failed: %s", session_id, exc)
            async with app.state.sessionmaker() as err_db:
                await mark_failed(err_db, session_id, error=str(exc))


async def restore_from_db(app) -> None:
    """On startup: re-register any scheduled/waiting sessions lost across restarts."""
    from synapse.db.models import CouncilSession, CouncilStatus

    runner: ScheduledCouncilRunner = app.state.scheduler
    now = datetime.now(UTC)

    async with app.state.sessionmaker() as db:
        from sqlalchemy import select

        # Scheduled councils whose run_at is still in the future
        stmt = select(CouncilSession).where(
            CouncilSession.status == CouncilStatus.scheduled,
            CouncilSession.run_at.isnot(None),
        )
        result = await db.execute(stmt)
        scheduled = result.scalars().all()
        for s in scheduled:
            if s.run_at and s.run_at > now:
                runner.schedule(app, s.id, s.run_at)
                _logger.info("Restored scheduled council %s (run_at=%s)", s.id, s.run_at)
            else:
                # run_at has passed — fire immediately
                asyncio.create_task(_fire_council(app, s.id))

        # Async councils waiting for contributions with a future deadline
        stmt2 = select(CouncilSession).where(
            CouncilSession.status == CouncilStatus.waiting_contributions,
            CouncilSession.contribution_deadline.isnot(None),
        )
        result2 = await db.execute(stmt2)
        waiting = result2.scalars().all()
        for s in waiting:
            if s.contribution_deadline and s.contribution_deadline > now:
                runner.schedule_resume(app, s.id, s.contribution_deadline)
                _logger.info(
                    "Restored async council %s deadline (deadline=%s)",
                    s.id,
                    s.contribution_deadline,
                )
            else:
                asyncio.create_task(_fire_resume(app, s.id))
