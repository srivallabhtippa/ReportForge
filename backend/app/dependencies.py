import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, role_permissions, user_roles
from app.permissions import PERMISSIONS
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


def get_current_permissions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> frozenset[str]:
    """The set of permission keys the logged-in user holds right now.

    A user can hold several roles; the permissions are the union of all of them
    (ADR 0005, decision 4). One query joins user_roles -> role_permissions, and the
    database removes duplicates (DISTINCT) when two roles share a permission.

    FastAPI runs a dependency once per request and reuses the result, so a route
    that needs several checks still costs one query.
    """
    rows = db.scalars(
        select(role_permissions.c.permission_key)
        .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
        .where(user_roles.c.user_id == user.id)
        .distinct()
    )
    return frozenset(rows)


def require_permission(permission: str) -> Callable[..., User]:
    """Build a dependency that lets a request through only if the user holds `permission`.

    Usage:  user: User = Depends(require_permission("users.manage"))

    This is the ONLY way routes check access (ADR 0005, decision 6). Routes never look
    at role names, because role names are chosen by each organization and can change.
    """
    # Fail at import time, when the app starts, if a route names a permission that is
    # not in the catalogue. A typo would otherwise silently lock everyone out (403
    # forever) and only show up when someone happened to call that route.
    if permission not in PERMISSIONS:
        raise ValueError(f"Unknown permission {permission!r}; add it to app/permissions.py")

    def dependency(
        user: User = Depends(get_current_user),
        permissions: frozenset[str] = Depends(get_current_permissions),
    ) -> User:
        # Not logged in is already a 401 inside get_current_user. Reaching this line
        # means we know who you are, you just may not do this: 403, not 401.
        if permission not in permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Not allowed")
        return user

    return dependency
