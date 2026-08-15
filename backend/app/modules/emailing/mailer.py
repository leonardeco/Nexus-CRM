import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import urlparse

from app.core.config import settings

log = logging.getLogger("nexus.mailer")


def send_email(to_email: str, subject: str, body: str, template: str = "") -> None:
    del template
    parsed = urlparse(settings.smtp_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 1025
    message = EmailMessage()
    message["From"] = "noreply@localhost"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=10) as client:
        client.send_message(message)
