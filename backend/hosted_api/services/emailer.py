"""Email delivery helpers for hosted job completion notifications."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path
import smtplib

from ..config import get_settings


def write_email_preview(email: str, subject: str, body: str, preview_dir: Path) -> Path:
    """Write an email preview to disk until a real provider is configured."""
    preview_dir.mkdir(parents=True, exist_ok=True)
    safe_email = email.replace("@", "_at_").replace(".", "_")
    path = preview_dir / f"{safe_email}.txt"
    payload = f"TO: {email}\nSUBJECT: {subject}\n\n{body}\n"
    path.write_text(payload, encoding="utf-8")
    return path


def send_or_preview_email(email: str, subject: str, body: str, preview_dir: Path) -> Path | None:
    """Send email through SMTP when configured, otherwise write a preview file."""
    settings = get_settings()
    if not settings.smtp_host:
        return write_email_preview(email, subject, body, preview_dir)

    message = EmailMessage()
    message["From"] = settings.email_from
    message["To"] = email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_starttls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(message)
    return None
