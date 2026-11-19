import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings

JWT_ALGORITHM = "HS256"

# Argon2id is the current recommended password hashing algorithm. It is slow and
# memory-hungry on purpose, so guessing passwords from a stolen database is costly.
# The defaults are tuned for interactive logins.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    # Returns one string that contains the algorithm, its settings, a random salt
    # and the hash. The same password produces a different string every time.
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    # Never raises for a wrong password, just returns False.
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


# A real hash of a throwaway password. Login verifies against it when the email is
# unknown, so "unknown email" and "wrong password" take the same time to answer.
DUMMY_PASSWORD_HASH = hash_password("not-a-real-password")


def create_access_token(user_id: uuid.UUID, organization_id: uuid.UUID) -> tuple[str, int]:
    """Build a signed token. Returns the token and its lifetime in seconds."""
    settings = get_settings()
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),  # "subject": who this token is about
        "org": str(organization_id),
        "iat": now,  # issued at
        "exp": now + lifetime,  # expires: the library rejects the token after this
    }
    token = jwt.encode(claims, settings.secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str) -> dict:
    """Check the signature and expiry, and return the claims.

    Raises jwt.InvalidTokenError (or a subclass) for anything wrong: bad signature,
    expired, malformed, or missing a required claim.
    """
    return jwt.decode(
        token,
        get_settings().secret_key.get_secret_value(),
        # Pin the algorithm. Never accept whatever the token's own header claims,
        # otherwise an attacker could ask for "none" (no signature at all).
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub", "org"]},
    )
