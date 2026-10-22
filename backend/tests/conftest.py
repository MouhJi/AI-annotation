import os
import secrets
import tempfile
from pathlib import Path
import pytest

# Set before importing app/main or any test module; never connect to the user's DB.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["STORAGE_PATH"] = tempfile.mkdtemp(prefix="annotation-auth-tests-")
os.environ["JWT_SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["APP_ENV"] = "test"
os.environ["EMAIL_BACKEND"] = "file"
os.environ["EMAIL_PROVIDER"] = "file"
os.environ["EMAIL_VERIFICATION_REQUIRED"] = "false"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
# Legacy tests create small input images under /tmp on Windows too.
Path("/tmp").mkdir(exist_ok=True)

@pytest.fixture(autouse=True)
def clear_auth_rate_limits():
    from app.rate_limit import limiter
    limiter.buckets.clear()
