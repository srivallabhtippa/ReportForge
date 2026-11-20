"""Authorization rules shared by the roles and users routers (ADR 0005, decision 9)."""

from fastapi import HTTPException, status

from app.models import Role


def keys_of(roles: list[Role]) -> set[str]:
    """Every permission key held by at least one of the roles."""
    return {p.key for role in roles for p in role.permissions}


def forbid_granting_what_you_lack(keys: set[str], caller_permissions: frozenset[str]) -> None:
    """No privilege escalation: you can hand out only permissions you hold yourself.

    Without this, anyone with roles.manage could create a role holding every permission
    and give it to themselves.
    """
    missing = keys - caller_permissions
    if missing:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"You cannot grant permissions you do not hold: {', '.join(sorted(missing))}",
        )


def forbid_managing_above_you(keys: set[str], caller_permissions: frozenset[str], what: str) -> None:
    """You cannot edit, delete, disable or re-role something that holds permissions you lack.

    Otherwise someone with only users.manage could disable an admin, or someone with
    only roles.manage could strip or delete a more powerful role.
    """
    if keys - caller_permissions:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"You cannot manage a {what} that has permissions you do not hold",
        )
