from sqlalchemy import select

from app.models import AuditLog, User
from tests.conftest import TEST_PASSWORD, login_as, make_org, make_role, make_user


def events(client, headers, **params):
    response = client.get("/api/audit-log", headers=headers, params=params)
    assert response.status_code == 200
    return response.json()


def actions(client, headers, **params):
    return [e["action"] for e in events(client, headers, **params)]


def test_registration_and_login_are_recorded(client, auth_headers):
    # auth_headers fixture = register + login
    assert actions(client, auth_headers) == ["auth.login", "organization.registered"]
    first = events(client, auth_headers)[-1]
    assert first["actor_email"] == "ada@example.com"
    assert first["details"]["organization_name"] == "Acme Supermarkets"


def test_failed_login_is_not_recorded(client, auth_headers):
    before = len(events(client, auth_headers))
    client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-password-1"})
    assert len(events(client, auth_headers)) == before


def test_role_lifecycle_is_recorded_with_details(client, auth_headers):
    role = client.post(
        "/api/roles",
        json={"name": "Viewer", "permission_keys": ["users.view"]},
        headers=auth_headers,
    ).json()
    client.patch(
        f"/api/roles/{role['id']}",
        json={"name": "Reader", "permission_keys": ["roles.view"]},
        headers=auth_headers,
    )
    client.delete(f"/api/roles/{role['id']}", headers=auth_headers)

    log = {e["action"]: e for e in events(client, auth_headers)}
    assert log["role.created"]["details"] == {"name": "Viewer", "permissions": ["users.view"]}
    assert log["role.updated"]["details"] == {
        "name": {"from": "Viewer", "to": "Reader"},
        "permissions": {"added": ["roles.view"], "removed": ["users.view"]},
    }
    assert log["role.deleted"]["details"] == {"name": "Reader"}
    assert {e["target_id"] for e in events(client, auth_headers) if e["target_type"] == "role"} == {role["id"]}
    assert log["role.created"]["actor_email"] == "ada@example.com"


def test_update_that_changes_nothing_is_not_an_event(client, auth_headers):
    role = client.post("/api/roles", json={"name": "Same"}, headers=auth_headers).json()
    before = len(events(client, auth_headers))
    client.patch(f"/api/roles/{role['id']}", json={"name": "Same"}, headers=auth_headers)
    assert len(events(client, auth_headers)) == before


def test_user_changes_are_recorded_and_never_contain_the_password(client, db, auth_headers):
    created = client.post(
        "/api/users",
        json={"email": "bob@example.com", "full_name": "Bob Builder", "password": "super-secret-pass-1"},
        headers=auth_headers,
    ).json()
    role = client.post("/api/roles", json={"name": "Viewer"}, headers=auth_headers).json()
    client.patch(
        f"/api/users/{created['id']}",
        json={"is_active": False, "role_ids": [role["id"]], "full_name": "Robert"},
        headers=auth_headers,
    )
    client.patch(f"/api/users/{created['id']}", json={"is_active": True}, headers=auth_headers)

    log = events(client, auth_headers)
    names = [e["action"] for e in log]
    for expected in ("user.created", "user.updated", "user.disabled", "user.enabled", "user.roles_changed"):
        assert expected in names
    roles_changed = next(e for e in log if e["action"] == "user.roles_changed")
    assert roles_changed["details"]["added"] == ["Viewer"]
    assert roles_changed["details"]["email"] == "bob@example.com"
    # Nothing secret anywhere in the whole log.
    text = str(log)
    assert "super-secret-pass-1" not in text
    assert "$argon2" not in text


def test_refused_change_leaves_no_audit_row(client, db, auth_headers):
    """Change and record succeed or fail together (same transaction)."""
    body = {"name": "Dup"}
    client.post("/api/roles", json=body, headers=auth_headers)
    before = db.query(AuditLog).count()
    assert client.post("/api/roles", json=body, headers=auth_headers).status_code == 409
    db.expire_all()
    assert db.query(AuditLog).count() == before

    me = db.scalar(select(User))
    assert client.patch(f"/api/users/{me.id}", json={"is_active": False}, headers=auth_headers).status_code == 409
    db.expire_all()
    assert db.query(AuditLog).count() == before


# --- Reading: filters, paging, permission, tenancy -----------------------------------


def test_filter_and_paging(client, auth_headers):
    for i in range(3):
        client.post("/api/roles", json={"name": f"R{i}"}, headers=auth_headers)
    assert actions(client, auth_headers, action="role.created") == ["role.created"] * 3
    newest_first = events(client, auth_headers, action="role.created")
    assert [e["details"]["name"] for e in newest_first] == ["R2", "R1", "R0"]
    page = events(client, auth_headers, action="role.created", limit=1, offset=1)
    assert [e["details"]["name"] for e in page] == ["R1"]


def test_limit_is_bounded(client, auth_headers):
    assert client.get("/api/audit-log?limit=100000", headers=auth_headers).status_code == 422
    assert client.get("/api/audit-log?limit=0", headers=auth_headers).status_code == 422


def test_needs_audit_view_permission(client, db, org):
    assert client.get("/api/audit-log").status_code == 401
    make_user(db, org, "n@example.com", [make_role(db, org, "none", ["users.view"])])
    assert client.get("/api/audit-log", headers=login_as(client, "n@example.com")).status_code == 403
    make_user(db, org, "a@example.com", [make_role(db, org, "auditor", ["audit.view"])])
    assert client.get("/api/audit-log", headers=login_as(client, "a@example.com")).status_code == 200


def test_log_only_shows_own_organization(client, db, auth_headers):
    other = make_org(db, "Other")
    other_admin = make_user(db, other, "o@example.com", [make_role(db, other, "A", ["audit.view", "roles.manage"])])
    other_headers = login_as(client, "o@example.com")
    client.post("/api/roles", json={"name": "OtherSecret"}, headers=other_headers)

    assert "OtherSecret" not in client.get("/api/audit-log", headers=auth_headers).text
    assert "ada@example.com" not in client.get("/api/audit-log", headers=other_headers).text
    assert other_admin.organization_id == other.id


def test_there_is_no_way_to_change_the_log_through_the_api(client, auth_headers):
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/audit-log", headers=auth_headers).status_code == 405


def test_deleting_a_role_logs_an_event_for_every_user_who_lost_it(client, db, auth_headers):
    from app.models import Role
    from tests.conftest import make_user

    org = db.scalar(select(User)).organization
    role = make_role(db, org, "Temp", ["users.view"])
    make_user(db, org, "a@example.com", [role])
    make_user(db, org, "b@example.com", [role])

    role_id = role.id
    assert client.delete(f"/api/roles/{role_id}", headers=auth_headers).status_code == 204

    changed = [e for e in events(client, auth_headers, action="user.roles_changed")]
    assert sorted(e["details"]["email"] for e in changed) == ["a@example.com", "b@example.com"]
    assert all(e["details"]["removed"] == ["Temp"] for e in changed)
    assert db.scalar(select(Role).where(Role.id == role_id)) is None
