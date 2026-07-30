from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt as _bcrypt
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from app.core.config import settings


class CredentialsError(Exception):
    """Token signature is invalid or payload is malformed."""

class TokenExpiredError(Exception):
    """Token has passed its expiry time."""

class TokenTypeError(Exception):
    """Wrong token type presented."""


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    salt = _bcrypt.gensalt(rounds=12)
    return _bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(
    subject: str | Any,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "exp": expire,
        "sub": str(subject),
        "role": role,
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str | Any, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=7)
    payload = {
        "exp": expire,
        "sub": str(subject),
        "role": role,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired") from exc
    except InvalidTokenError as exc:
        raise CredentialsError("Could not validate credentials") from exc

    if payload.get("type") != "access":
        raise TokenTypeError("Expected an access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("Refresh token has expired") from exc
    except InvalidTokenError as exc:
        raise CredentialsError("Could not validate refresh token") from exc

    if payload.get("type") != "refresh":
        raise TokenTypeError("Expected a refresh token")
    return payload
