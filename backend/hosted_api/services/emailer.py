"""Email delivery helpers for hosted job completion notifications."""

from __future__ import annotations

from collections.abc import Sequence
from email.message import EmailMessage
import logging
from pathlib import Path
import shutil
import smtplib

from ..config import get_settings

logger = logging.getLogger(__name__)


def _usable_attachments(attachments: Sequence[Path] | None) -> list[Path]:
    """Drop anything missing or empty, so a failed report still sends the email."""
    usable: list[Path] = []
    for path in attachments or []:
        if path is None:
            continue
        try:
            if path.exists() and path.stat().st_size > 0:
                usable.append(path)
            else:
                logger.warning("Skipping missing or empty attachment: %s", path)
        except OSError as exc:
            logger.warning("Skipping unreadable attachment %s: %s", path, exc)
    return usable


def write_email_preview(
    email: str,
    subject: str,
    body: str,
    preview_dir: Path,
    *,
    attachments: Sequence[Path] | None = None,
    preview_slug: str | None = None,
) -> Path:
    """Write an email preview to disk until a real provider is configured."""
    preview_dir.mkdir(parents=True, exist_ok=True)
    safe_email = email.replace("@", "_at_").replace(".", "_")
    # The slug keeps one recipient's previews from overwriting each other.
    stem = f"{safe_email}.{preview_slug}" if preview_slug else safe_email
    path = preview_dir / f"{stem}.txt"

    files = _usable_attachments(attachments)
    payload = f"TO: {email}\nSUBJECT: {subject}\n\n{body}\n"
    if files:
        payload += "\nATTACHMENTS:\n"
        for src in files:
            payload += f"  {src.name} ({src.stat().st_size} bytes)\n"
            # Copy the exact bytes that would have been mailed, so the preview is
            # inspectable rather than just described.
            try:
                shutil.copy2(src, preview_dir / f"{stem}.{src.name}")
            except OSError as exc:
                logger.warning("Could not copy preview attachment %s: %s", src, exc)

    path.write_text(payload, encoding="utf-8")
    return path


def send_or_preview_email(
    email: str,
    subject: str,
    body: str,
    preview_dir: Path,
    *,
    attachments: Sequence[Path] | None = None,
    preview_slug: str | None = None,
) -> Path | None:
    """Send email through SMTP when configured, otherwise write a preview file."""
    settings = get_settings()
    if not settings.smtp_host:
        return write_email_preview(
            email, subject, body, preview_dir,
            attachments=attachments, preview_slug=preview_slug,
        )

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = email
    message["Subject"] = subject
    message.set_content(body)

    for path in _usable_attachments(attachments):
        message.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=path.name,
        )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_starttls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(message)
    return None
