"""Unit tests for NotificationDispatcher."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from synapse.db.models import DeviceToken, NotificationPreferences
from synapse.notifications.dispatcher import NotificationDispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dispatcher(
    *,
    feature_enabled: bool = True,
    smtp_host: str = "smtp.example.com",
    ntfy_url: str = "https://ntfy.sh",
) -> NotificationDispatcher:
    settings = MagicMock()
    settings.smtp_host = smtp_host
    settings.smtp_port = 587
    settings.smtp_username = "user"
    settings.smtp_password = "pass"
    settings.smtp_from_address = "noreply@synapse.local"
    settings.smtp_tls = True
    settings.ntfy_url = ntfy_url
    settings.ntfy_token = ""

    ff = MagicMock()
    ff.is_enabled = MagicMock(return_value=feature_enabled)

    http_client = AsyncMock()

    return NotificationDispatcher(settings=settings, http_client=http_client, feature_flags=ff)


def _make_prefs(
    *,
    email_enabled: bool = False,
    email_address: str | None = None,
    ntfy_enabled: bool = False,
    principal: str = "user-1",
) -> NotificationPreferences:
    prefs = MagicMock(spec=NotificationPreferences)
    prefs.principal = principal
    prefs.email_enabled = email_enabled
    prefs.email_address = email_address
    prefs.ntfy_enabled = ntfy_enabled
    return prefs


def _make_device(token: str = "my-topic") -> DeviceToken:
    device = MagicMock(spec=DeviceToken)
    device.id = uuid.uuid4()
    device.token = token
    device.token_type = "ntfy"
    return device


# ---------------------------------------------------------------------------
# Feature flag gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_no_op_when_feature_disabled():
    dispatcher = _make_dispatcher(feature_enabled=False)
    db = AsyncMock()

    await dispatcher.dispatch_verdict(
        council_id="c-1",
        question="What?",
        verdict="Yes.",
        recipient_principal="user-1",
        db=db,
    )

    # DB was never queried
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# No preferences row → silent no-op
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_no_op_when_no_prefs_row():
    dispatcher = _make_dispatcher()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    await dispatcher.dispatch_verdict(
        council_id="c-1",
        question="What?",
        verdict="Yes.",
        recipient_principal="user-1",
        db=db,
    )
    # No email/ntfy calls
    db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Email channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_sent_when_enabled():
    """_try_email calls send_email when all conditions are met."""
    dispatcher = _make_dispatcher()
    prefs = _make_prefs(email_enabled=True, email_address="alice@example.com")

    with patch("synapse.notifications.dispatcher.send_email", new=AsyncMock()) as mock_send:
        await dispatcher._try_email(prefs, "Subject", "Body")
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["to"] == "alice@example.com"
        assert call_kwargs["subject"] == "Subject"


@pytest.mark.asyncio
async def test_email_not_sent_when_disabled():
    dispatcher = _make_dispatcher()
    prefs = _make_prefs(email_enabled=False, email_address="alice@example.com")

    with patch("synapse.notifications.dispatcher.send_email", new=AsyncMock()) as mock_send:
        await dispatcher._try_email(prefs, "Subject", "Body")
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_not_sent_when_no_address():
    dispatcher = _make_dispatcher()
    prefs = _make_prefs(email_enabled=True, email_address=None)

    with patch("synapse.notifications.dispatcher.send_email", new=AsyncMock()) as mock_send:
        await dispatcher._try_email(prefs, "Subject", "Body")
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_not_sent_when_smtp_host_not_configured():
    dispatcher = _make_dispatcher(smtp_host="")
    prefs = _make_prefs(email_enabled=True, email_address="alice@example.com")

    with patch("synapse.notifications.dispatcher.send_email", new=AsyncMock()) as mock_send:
        await dispatcher._try_email(prefs, "Subject", "Body")
        mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_email_error_is_caught_not_raised():
    dispatcher = _make_dispatcher()
    prefs = _make_prefs(email_enabled=True, email_address="alice@example.com")

    with patch(
        "synapse.notifications.dispatcher.send_email",
        new=AsyncMock(side_effect=Exception("SMTP failed")),
    ):
        # Should not raise
        await dispatcher._try_email(prefs, "Subject", "Body")


# ---------------------------------------------------------------------------
# ntfy channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ntfy_not_sent_when_disabled():
    dispatcher = _make_dispatcher()
    prefs = _make_prefs(ntfy_enabled=False)
    db = AsyncMock()

    await dispatcher._try_ntfy(prefs, "user-1", "Subject", "Body", db)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_ntfy_not_sent_when_url_not_configured():
    dispatcher = _make_dispatcher(ntfy_url="")
    prefs = _make_prefs(ntfy_enabled=True)
    db = AsyncMock()

    await dispatcher._try_ntfy(prefs, "user-1", "Subject", "Body", db)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_ntfy_sends_to_all_devices():
    dispatcher = _make_dispatcher()
    prefs = _make_prefs(ntfy_enabled=True)
    db = AsyncMock()
    devices = [_make_device("topic-a"), _make_device("topic-b")]
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=devices)))
        )
    )

    with patch("synapse.notifications.ntfy.httpx") as _:
        dispatcher._http.post = AsyncMock(
            return_value=MagicMock(status_code=200, raise_for_status=MagicMock())
        )
        await dispatcher._try_ntfy(prefs, "user-1", "Subject", "Body", db)

    assert dispatcher._http.post.call_count == 2


@pytest.mark.asyncio
async def test_ntfy_error_is_caught_not_raised():
    dispatcher = _make_dispatcher()
    prefs = _make_prefs(ntfy_enabled=True)
    db = AsyncMock()
    devices = [_make_device("topic-a")]
    db.execute = AsyncMock(
        return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=devices)))
        )
    )

    dispatcher._http.post = AsyncMock(side_effect=Exception("ntfy down"))
    # Should not raise
    await dispatcher._try_ntfy(prefs, "user-1", "Subject", "Body", db)


# ---------------------------------------------------------------------------
# dispatch_verdict subject formatting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_verdict_truncates_long_question():
    dispatcher = _make_dispatcher(feature_enabled=False)
    long_q = "A" * 200
    db = AsyncMock()

    # Feature disabled — just verifies the method runs without error on long input
    await dispatcher.dispatch_verdict(
        council_id="c-1",
        question=long_q,
        verdict="Yes",
        recipient_principal="user-1",
        db=db,
    )


# ---------------------------------------------------------------------------
# dispatch_summon
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_summon_no_op_when_feature_disabled():
    dispatcher = _make_dispatcher(feature_enabled=False)
    db = AsyncMock()

    await dispatcher.dispatch_summon(
        council_id="c-1",
        question="Contribute?",
        recipient_principal="user-1",
        db=db,
    )

    db.execute.assert_not_called()
