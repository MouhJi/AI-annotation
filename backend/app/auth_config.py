import os
import secrets
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from .email_config import email_settings

@lru_cache
def settings():
    production = os.getenv("APP_ENV", "development") == "production"
    secret = os.getenv("JWT_SECRET_KEY", "")
    secure = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
    origins = [value.strip() for value in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if value.strip()]
    email_backend = email_settings()["provider"]
    if "*" in origins: raise RuntimeError("CORS_ORIGINS must be an explicit allowlist")
    frontend = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    parsed = urlsplit(frontend)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or any(c.isspace() for c in frontend):
        raise RuntimeError("FRONTEND_URL must be an absolute HTTP(S) URL without credentials, query or fragment")
    if production and (len(secret) < 32 or not secure or email_backend != "smtp" or not os.getenv("SMTP_HOST") or not os.getenv("SMTP_FROM_EMAIL") or not frontend.startswith("https://") or any(not origin.startswith("https://") for origin in origins)):
        raise RuntimeError("Production requires JWT_SECRET_KEY (32+ chars), secure cookies and SMTP")
    if not secret:
        # A random persistent local secret, never a shared default or printed to logs.
        path = Path(os.getenv("STORAGE_PATH", "./storage")) / ".auth-secret"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x", encoding="utf-8") as stream: stream.write(secrets.token_urlsafe(48))
            path.chmod(0o600)
        except FileExistsError: pass
        secret = path.read_text(encoding="utf-8").strip()
    if len(secret) < 32: raise RuntimeError("JWT_SECRET_KEY must contain at least 32 characters")
    return {"secret": secret, "issuer": os.getenv("JWT_ISSUER", "annotation-platform"), "audience": os.getenv("JWT_AUDIENCE", "annotation-web"), "access_minutes": int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")), "refresh_days": int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7")), "secure": secure, "origins": origins, "frontend": frontend, "email_backend": email_backend, "verify_required": os.getenv("EMAIL_VERIFICATION_REQUIRED", "false").lower() == "true"}
