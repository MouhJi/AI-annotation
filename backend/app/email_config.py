"""Validated mail configuration. Never include these values in diagnostics/logs."""
import math
import os
from email.headerregistry import Address


def email_settings():
    production = os.getenv("APP_ENV", "development") == "production"
    provider = (os.getenv("EMAIL_PROVIDER") or os.getenv("EMAIL_BACKEND") or "file").strip().lower()
    if provider not in {"smtp", "file"}:
        raise RuntimeError("EMAIL_PROVIDER must be smtp or file")
    if provider == "file" and production:
        raise RuntimeError("Production requires EMAIL_PROVIDER=smtp")
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))
    except ValueError:
        raise RuntimeError("Invalid SMTP port or timeout") from None
    if not 1 <= port <= 65535 or not math.isfinite(timeout) or not 1 <= timeout <= 60:
        raise RuntimeError("SMTP port or timeout is outside the supported range")
    tls_value = os.getenv("SMTP_USE_STARTTLS", "true").lower()
    if tls_value not in {"true", "false"}:
        raise RuntimeError("SMTP_USE_STARTTLS must be true or false")
    config = dict(provider=provider, host=os.getenv("SMTP_HOST", "").strip(), port=port,
                  starttls=tls_value == "true", timeout=timeout,
                  username=os.getenv("SMTP_USERNAME", ""), password=os.getenv("SMTP_PASSWORD", ""),
                  from_email=os.getenv("SMTP_FROM_EMAIL", "").strip(),
                  from_name=os.getenv("SMTP_FROM_NAME", "Data Annotation Platform"))
    if provider == "smtp":
        if not config["host"] or not config["from_email"]:
            raise RuntimeError("SMTP requires SMTP_HOST and SMTP_FROM_EMAIL")
        try:
            Address(addr_spec=config["from_email"])
        except ValueError:
            raise RuntimeError("SMTP_FROM_EMAIL must be a valid address") from None
        if any("\n" in value or "\r" in value for value in (config["host"], config["from_email"], config["from_name"])):
            raise RuntimeError("Invalid SMTP header configuration")
        if bool(config["username"]) != bool(config["password"]):
            raise RuntimeError("Set both SMTP_USERNAME and SMTP_PASSWORD")
        if not config["starttls"] and (production or config["username"] or config["host"] not in {"localhost", "127.0.0.1", "mailpit", "mailhog"}):
            raise RuntimeError("SMTP requires STARTTLS except unauthenticated local development mail")
        if config["host"].lower() == "smtp.gmail.com" and (port != 587 or not config["starttls"] or not config["username"]):
            raise RuntimeError("Gmail SMTP requires port 587, STARTTLS and an App Password")
    return config
