import hashlib
import secrets
import uuid
from datetime import timedelta
import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError
from ..auth_config import settings
from ..models.auth import utcnow

hasher = PasswordHasher(type=Type.ID)
def hash_password(password: str) -> str:
    return hasher.hash(password)
def verify_password(password: str, password_hash: str) -> bool:
    try: return hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError): return False
def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
def opaque_token() -> str:
    return secrets.token_urlsafe(48)
def access_token(user, session):
    config = settings(); now = utcnow()
    return jwt.encode({"sub": str(user.id), "sid": str(session.id), "exp": now + timedelta(minutes=config["access_minutes"]), "iat": now, "iss": config["issuer"], "aud": config["audience"], "jti": str(uuid.uuid4()), "type": "access"}, config["secret"], algorithm="HS256")
def decode_access(token):
    config = settings()
    claims = jwt.decode(token, config["secret"], algorithms=["HS256"], issuer=config["issuer"], audience=config["audience"], options={"require": ["sub", "sid", "exp", "iat", "iss", "aud", "jti", "type"]})
    if claims["type"] != "access": raise jwt.InvalidTokenError()
    return claims
def aware(value):
    from datetime import timezone
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
