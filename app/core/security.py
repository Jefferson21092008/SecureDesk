from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()
# Used to keep the password-verification path comparable when an account does not exist.
# The value is generated at process startup and is never accepted as a real credential.
DUMMY_PASSWORD_HASH = password_hash.hash("SecureDesk-Dummy-Password-Only-9!")


@dataclass(frozen=True)
class AccessTokenClaims:
    subject: str
    jti: str
    issued_at: datetime
    expires_at: datetime


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.access_token_minutes)
    payload = {
        "sub": subject,
        "jti": uuid4().hex,
        "type": "access",
        "iat": issued_at,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenClaims:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        options={"require": ["sub", "jti", "type", "iat", "exp", "iss", "aud"]},
    )

    if payload.get("type") != "access":
        raise ValueError("Invalid token type")

    subject = payload.get("sub")
    jti = payload.get("jti")
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")

    if not isinstance(subject, str) or not subject:
        raise ValueError("Token subject is missing")
    if not isinstance(jti, str) or not jti:
        raise ValueError("Token identifier is missing")
    if not isinstance(issued_at, (int, float)) or not isinstance(expires_at, (int, float)):
        raise ValueError("Token timestamps are invalid")

    return AccessTokenClaims(
        subject=subject,
        jti=jti,
        issued_at=datetime.fromtimestamp(issued_at, tz=timezone.utc),
        expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
    )
