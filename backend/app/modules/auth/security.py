"""Password hashing (stdlib scrypt + random salt) and the session JWT (HS256)."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import AuthSettings

_N, _R, _P = 2**14, 8, 1


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = bytes.fromhex(digest_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_scrypt(password, salt), expected)


# Burned when the email is unknown, so a miss costs the same as a wrong password.
DUMMY_HASH = hash_password(secrets.token_hex(8))


def issue_token(user_id: str, auth: AuthSettings, now: datetime | None = None) -> str:
    issued = now or datetime.now(UTC)
    claims = {
        "sub": user_id,
        "iat": issued,
        "exp": issued + timedelta(minutes=auth.token_ttl_minutes),
    }
    return jwt.encode(claims, auth.jwt_secret, algorithm="HS256")


def read_token(token: str, auth: AuthSettings) -> str | None:
    """The user id the token was issued for, or None if it is invalid or expired."""
    try:
        claims = jwt.decode(
            token, auth.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
    except jwt.PyJWTError:
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None
