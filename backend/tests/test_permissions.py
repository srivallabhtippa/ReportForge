"""Tests for require_permission, using a throwaway app with routes that need permissions.

The real app has no permission-protected routes until steps 5-7, and the dependency
deserves tests of its own, so these routes exist only here.
"""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies import get_current_permissions, require_permission
from app.models import User
from tests.conftest import login_as, make_role, make_user

probe = FastAPI()


@probe.get("/needs-users-manage")
def needs_users_manage(user: User = Depends(require_permission("users.manage"))):
    return {"user": user.email}


@probe.get("/my-permissions")
def my_permissions(perms: frozenset[str] = Depends(get_current_permissions)):
    return sorted(perms)


@pytest.fixture
def probe_client():
    return TestClient(probe)


def test_no_token_is_401_not_403(probe_client):
    assert probe_client.get("/needs-users-manage").status_code == 401


def test_registered_admin_has_every_permission(client, probe_client, auth_headers):
    response = probe_client.get("/my-permissions", headers=auth_headers)
    assert response.status_code == 200
    from app.permissions import PERMISSIONS

    assert response.json() == sorted(PERMISSIONS)
    assert probe_client.get("/needs-users-manage", headers=auth_headers).status_code == 200


def test_user_without_the_permission_gets_403(client, probe_client, db, org):
    viewer = make_role(db, org, "Viewer", ["users.view"])
    make_user(db, org, "v@example.com", [viewer])

    response = probe_client.get("/needs-users-manage", headers=login_as(client, "v@example.com"))
    assert response.status_code == 403


def test_user_with_no_roles_has_no_permissions(client, probe_client, db, org):
    make_user(db, org, "none@example.com", [])
    headers = login_as(client, "none@example.com")

    assert probe_client.get("/my-permissions", headers=headers).json() == []
    assert probe_client.get("/needs-users-manage", headers=headers).status_code == 403


def test_permissions_are_the_union_of_all_roles_without_duplicates(client, probe_client, db, org):
    a = make_role(db, org, "A", ["users.view", "roles.view"])
    b = make_role(db, org, "B", ["users.view", "users.manage"])
    make_user(db, org, "both@example.com", [a, b])
    headers = login_as(client, "both@example.com")

    assert probe_client.get("/my-permissions", headers=headers).json() == [
        "roles.view",
        "users.manage",
        "users.view",
    ]
    assert probe_client.get("/needs-users-manage", headers=headers).status_code == 200


def test_removing_a_role_takes_effect_immediately_with_the_same_token(
    client, probe_client, db, org
):
    manager = make_role(db, org, "Manager", ["users.manage"])
    user = make_user(db, org, "m@example.com", [manager])
    headers = login_as(client, "m@example.com")
    assert probe_client.get("/needs-users-manage", headers=headers).status_code == 200

    user.roles.clear()
    db.commit()

    # Same token, no new login: permissions come from the database, not from the JWT.
    assert probe_client.get("/needs-users-manage", headers=headers).status_code == 403


def test_unknown_permission_fails_when_the_route_is_defined():
    with pytest.raises(ValueError, match="Unknown permission"):
        require_permission("users.manag")  # typo
