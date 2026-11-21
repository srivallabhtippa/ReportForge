import uuid

from app.models import Role
from app.permissions import PERMISSIONS
from tests.conftest import login_as, make_org, make_role, make_user


def as_user(client, db, org, email, keys):
    """A user holding one role with exactly `keys`; returns auth headers."""
    role = make_role(db, org, f"role-for-{email}", keys)
    make_user(db, org, email, [role])
    return login_as(client, email)


# --- Reading ------------------------------------------------------------------------


def test_list_permissions_returns_the_catalogue(client, auth_headers):
    response = client.get("/api/permissions", headers=auth_headers)
    assert response.status_code == 200
    assert {p["key"] for p in response.json()} == set(PERMISSIONS)


def test_list_roles_shows_the_admin_role_with_all_permissions(client, auth_headers):
    roles = client.get("/api/roles", headers=auth_headers).json()
    assert [r["name"] for r in roles] == ["Admin"]
    assert roles[0]["is_system"] is True
    assert {p["key"] for p in roles[0]["permissions"]} == set(PERMISSIONS)


def test_endpoints_need_a_login_and_the_right_permission(client, db, org):
    assert client.get("/api/roles").status_code == 401
    no_perms = as_user(client, db, org, "n@example.com", [])
    assert client.get("/api/roles", headers=no_perms).status_code == 403
    assert client.get("/api/permissions", headers=no_perms).status_code == 403
    viewer = as_user(client, db, org, "v@example.com", ["roles.view"])
    assert client.get("/api/roles", headers=viewer).status_code == 200
    # viewing is not managing
    body = {"name": "X", "permission_keys": []}
    assert client.post("/api/roles", json=body, headers=viewer).status_code == 403


# --- Creating -----------------------------------------------------------------------


def test_create_role(client, auth_headers):
    response = client.post(
        "/api/roles",
        json={"name": "  Viewer ", "description": "Read only", "permission_keys": ["users.view", "users.view"]},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Viewer"  # trimmed
    assert body["is_system"] is False  # clients can never create system roles
    assert [p["key"] for p in body["permissions"]] == ["users.view"]  # duplicate dropped


def test_create_role_with_unknown_permission_is_422(client, auth_headers):
    response = client.post(
        "/api/roles", json={"name": "Bad", "permission_keys": ["users.fly"]}, headers=auth_headers
    )
    assert response.status_code == 422
    assert "users.fly" in response.json()["detail"]


def test_duplicate_role_name_in_same_org_is_409(client, auth_headers):
    body = {"name": "Viewer", "permission_keys": []}
    assert client.post("/api/roles", json=body, headers=auth_headers).status_code == 201
    assert client.post("/api/roles", json=body, headers=auth_headers).status_code == 409


def test_same_role_name_in_two_orgs_is_fine(client, db, auth_headers):
    other = make_org(db, "Other")
    make_role(db, other, "Viewer", [])
    response = client.post(
        "/api/roles", json={"name": "Viewer", "permission_keys": []}, headers=auth_headers
    )
    assert response.status_code == 201


# --- Privilege escalation -----------------------------------------------------------


def test_cannot_create_a_role_with_permissions_you_do_not_hold(client, db, org):
    headers = as_user(client, db, org, "m@example.com", ["roles.manage", "roles.view"])
    response = client.post(
        "/api/roles",
        json={"name": "Super", "permission_keys": ["users.manage"]},
        headers=headers,
    )
    assert response.status_code == 403
    assert "users.manage" in response.json()["detail"]
    # and the same user can grant what they do hold
    ok = client.post(
        "/api/roles",
        json={"name": "Meta", "permission_keys": ["roles.view"]},
        headers=headers,
    )
    assert ok.status_code == 201


def test_cannot_add_a_permission_you_lack_when_editing(client, db, org):
    headers = as_user(client, db, org, "m@example.com", ["roles.manage", "roles.view"])
    role = make_role(db, org, "Target", ["users.view"])
    response = client.patch(
        f"/api/roles/{role.id}",
        json={"permission_keys": ["users.view", "audit.view"]},
        headers=headers,
    )
    assert response.status_code == 403


def test_cannot_edit_or_delete_a_role_that_holds_permissions_you_lack(client, db, org):
    headers = as_user(client, db, org, "m@example.com", ["roles.manage"])
    role = make_role(db, org, "Auditor", ["audit.view"])
    url = f"/api/roles/{role.id}"

    assert client.patch(url, json={"name": "Renamed"}, headers=headers).status_code == 403
    assert client.patch(url, json={"permission_keys": []}, headers=headers).status_code == 403
    assert client.delete(url, headers=headers).status_code == 403
    db.expire_all()
    assert db.get(Role, role.id).name == "Auditor"
    assert [p.key for p in db.get(Role, role.id).permissions] == ["audit.view"]


def test_can_edit_a_role_whose_permissions_you_all_hold(client, db, org):
    headers = as_user(client, db, org, "m@example.com", ["roles.manage", "users.view"])
    role = make_role(db, org, "Small", ["users.view"])
    response = client.patch(f"/api/roles/{role.id}", json={"name": "Renamed"}, headers=headers)
    assert response.status_code == 200


# --- Updating and deleting ----------------------------------------------------------


def test_patch_changes_only_what_is_sent(client, auth_headers):
    created = client.post(
        "/api/roles",
        json={"name": "Viewer", "description": "d", "permission_keys": ["users.view"]},
        headers=auth_headers,
    ).json()
    updated = client.patch(
        f"/api/roles/{created['id']}", json={"description": "new"}, headers=auth_headers
    ).json()
    assert updated["name"] == "Viewer"
    assert updated["description"] == "new"
    assert [p["key"] for p in updated["permissions"]] == ["users.view"]


def test_patch_replaces_the_permission_set(client, auth_headers):
    created = client.post(
        "/api/roles", json={"name": "R", "permission_keys": ["users.view"]}, headers=auth_headers
    ).json()
    updated = client.patch(
        f"/api/roles/{created['id']}",
        json={"permission_keys": ["roles.view", "org.view"]},
        headers=auth_headers,
    ).json()
    assert sorted(p["key"] for p in updated["permissions"]) == ["org.view", "roles.view"]


def test_renaming_to_an_existing_name_is_409(client, auth_headers):
    client.post("/api/roles", json={"name": "A"}, headers=auth_headers)
    b = client.post("/api/roles", json={"name": "B"}, headers=auth_headers).json()
    response = client.patch(f"/api/roles/{b['id']}", json={"name": "A"}, headers=auth_headers)
    assert response.status_code == 409


def test_delete_role_removes_it_from_users(client, db, auth_headers, org):
    from app.models import User
    from sqlalchemy import select

    role = client.post("/api/roles", json={"name": "Temp"}, headers=auth_headers).json()
    db_role = db.get(Role, uuid.UUID(role["id"]))
    user = db.scalar(select(User))
    user.roles.append(db_role)
    db.commit()

    assert client.delete(f"/api/roles/{role['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/roles/{role['id']}", headers=auth_headers).status_code == 404
    db.expire_all()
    assert [r.name for r in db.scalar(select(User)).roles] == ["Admin"]


# --- System role --------------------------------------------------------------------


def test_system_admin_role_cannot_be_changed_or_deleted(client, auth_headers):
    admin = client.get("/api/roles", headers=auth_headers).json()[0]
    url = f"/api/roles/{admin['id']}"
    assert client.patch(url, json={"name": "Boss"}, headers=auth_headers).status_code == 403
    assert client.patch(url, json={"permission_keys": []}, headers=auth_headers).status_code == 403
    assert client.delete(url, headers=auth_headers).status_code == 403
    assert client.get(url, headers=auth_headers).json()["name"] == "Admin"


# --- Tenant isolation ---------------------------------------------------------------


def test_other_organizations_roles_are_invisible_and_untouchable(client, db, auth_headers):
    other = make_org(db, "Other")
    foreign = make_role(db, other, "Secret", ["audit.view"])
    url = f"/api/roles/{foreign.id}"

    assert client.get(url, headers=auth_headers).status_code == 404
    assert client.patch(url, json={"name": "Hacked"}, headers=auth_headers).status_code == 404
    assert client.delete(url, headers=auth_headers).status_code == 404
    assert "Secret" not in client.get("/api/roles", headers=auth_headers).text
    db.expire_all()
    assert db.get(Role, foreign.id).name == "Secret"


def test_unknown_role_id_is_404(client, auth_headers):
    response = client.get(f"/api/roles/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404
