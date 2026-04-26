"""SMTP email sender for Synapse notifications.

Operators configure their own SMTP server via env vars — no vendor lock-in.
Works with any SMTP provider: Postfix, Mailgun SMTP relay, SES SMTP, etc.
"""

from __future__ import annotations

import logging
from email.mime.text import MIMEText

_logger = logging.getLogger(__name__)


async def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    host: str,
    port: int = 587,
    username: str = "",
    password: str = "",
    from_address: str = "noreply@synapse.local",
    use_tls: bool = True,
) -> None:
    """Send a plain-text email via SMTP (async).

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Plain-text body.
        host: SMTP server hostname.
        port: SMTP port (default 587 for STARTTLS).
        username: SMTP auth username (empty = no auth).
        password: SMTP auth password.
        from_address: Envelope sender address.
        use_tls: Whether to use STARTTLS (port 587) or SSL/TLS (port 465).
            Set False for unauthenticated local relay (port 25).

    Raises:
        aiosmtplib.SMTPException: on delivery failure.
    """
    import aiosmtplib

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = to

    await aiosmtplib.send(
        msg,
        hostname=host,
        port=port,
        username=username if username else None,
        password=password if password else None,
        use_tls=use_tls,
        start_tls=False,  # use_tls already handles STARTTLS on port 587
    )

    _logger.debug("Email sent to %s subject=%r", to, subject)
