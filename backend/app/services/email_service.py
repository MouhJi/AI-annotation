import logging
import os
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, formatdate
from pathlib import Path
from sqlalchemy import update
from ..email_config import email_settings
from ..models import EmailDeliveryAttempt
from ..models.auth import utcnow


def build_message(recipient, subject, text_body, html_body=None):
    config = email_settings()
    message = EmailMessage()
    message["To"] = recipient
    message["From"] = formataddr((config["from_name"], config["from_email"] or "noreply@localhost"))
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid()
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")
    return message


class EmailProvider:
    def send_email(self, to, subject, text_body, html_body=None):
        raise NotImplementedError


class FileEmailProvider(EmailProvider):
    def send_email(self, to, subject, text_body, html_body=None):
        if os.getenv("APP_ENV", "development") == "production":
            raise RuntimeError("File email is disabled in production")
        directory = Path(os.getenv("STORAGE_PATH", "./storage")) / ".emails"
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
        path = directory / f"{uuid.uuid4()}.eml"
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as stream:
            stream.write(build_message(to, subject, text_body, html_body).as_string())


class SMTPEmailProvider(EmailProvider):
    def send_email(self, to, subject, text_body, html_body=None):
        config = email_settings()
        message = build_message(to, subject, text_body, html_body)
        with smtplib.SMTP(config["host"], config["port"], timeout=config["timeout"]) as server:
            server.ehlo()
            if config["starttls"]:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if config["username"]:
                server.login(config["username"], config["password"])
            refused = server.send_message(message, from_addr=config["from_email"], to_addrs=[to])
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)


def prepare_delivery(db, purpose, resource_id):
    attempt = EmailDeliveryAttempt(purpose=purpose, resource_id=str(resource_id), provider=email_settings()["provider"])
    db.add(attempt)
    db.flush()
    return attempt


def deliver_email(db, attempt, to, subject, text_body, html_body=None):
    """Token + receipt must be committed first. One send, no automatic retry.

    Crashes leave a prepared/sending receipt for operators. No plaintext token is stored
    for retries: resend creates a fresh link. 'sent' means accepted by SMTP, not
    guaranteed inbox delivery.
    """
    if db.new or db.dirty:
        raise RuntimeError("Commit email work before delivery")
    claimed = db.execute(update(EmailDeliveryAttempt).where(
        EmailDeliveryAttempt.id == attempt.id, EmailDeliveryAttempt.status == "prepared",
    ).values(status="sending", updated_at=utcnow()).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.rollback()
        raise RuntimeError("This email delivery was already attempted")
    db.commit()
    status, code = "failed", None
    try:
        provider = SMTPEmailProvider() if attempt.provider == "smtp" else FileEmailProvider()
        provider.send_email(to, subject, text_body, html_body)
        status = "sent" if attempt.provider == "smtp" else "development"
    except (OSError, smtplib.SMTPException, ValueError) as error:
        code = "authentication" if isinstance(error, smtplib.SMTPAuthenticationError) else "timeout" if isinstance(error, TimeoutError) else "delivery"
        # Never log exception text, traceback, credentials, recipient or body.
        logging.getLogger(__name__).error("Email delivery failed (%s)", code)
    attempt.status, attempt.error_code, attempt.updated_at = status, code, utcnow()
    db.commit()
    return status
