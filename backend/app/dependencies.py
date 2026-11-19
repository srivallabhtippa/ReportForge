import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token

# Reads the "Authorization: Bearer <token>" header. auto_error=False lets us return
# our own 401 instead of FastAPI's default. It also adds the Authorize button
# to the /docs page.
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Dependency for every protected endpoint: returns the logged-in user or 401."""
    if credentials is None:
        raise _unauthorized()

    try:
        claims = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(claims["sub"])
        organization_id = uuid.UUID(claims["org"])
    except (jwt.InvalidTokenError, ValueError):
        raise _unauthorized()

    # Load the user fresh from the database on every request. A token proves who
    # you were when you logged in; the database says whether you are still allowed.
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.organization_id != organization_id:
        raise _unauthorized()
    return user
