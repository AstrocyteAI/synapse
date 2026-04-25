"""Router-level fixtures — shared by all tests under tests/routers/."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _no_restore_from_db():
    """Suppress DB recovery on lifespan startup.

    restore_from_db queries the real DB for scheduled/waiting sessions.
    Router tests use a fully mocked DB, so this would fail with a connection
    error.  Patch it out so the lifespan completes cleanly.
    """
    with patch("synapse.main.restore_from_db", new=AsyncMock(return_value=None)):
        yield
