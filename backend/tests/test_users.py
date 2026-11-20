import uuid

from sqlalchemy import select

from app.models import Role, User
from tests.conftest import TEST_PASSWORD, login_as, make_org, make_role, make_user

NEW_USER = {"email": "Bob@Example.com", "full_name": "Bob Builder", "password": TEST_PASSWORD}


def admin_role_id(client, headers):
    roles = client.get("/api/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == "Admin")


def as_user(client, db, org, email, keys):
    role = make_role(db, org, f"role-for-{email}", keys)
    make_user(db, org, email, [role])
    return login_as(client, email)


def my_org(db):
    return db.scalar(select(User)).organization


# --- Reading and permissions ---------------------------------------------------------


def test_list_users_shows_roles_and_active_flag(client, auth_headers):
    users = client.get("/api/users", headers=auth_headers).json()
    assert len(users) == 1
    assert users[0]["email"] == "ada@example.com"
    assert users[0]["is_active"] is True
    assert [r["name"] for r in users[0]["roles"]] == ["Admin"]
    assert "password" not in str(users[0])


def test_user_endpoints_need_the_right_permission(client, db, org):
    assert client.get("/api/users").status_code == 401
    nobody = as_user(client, db, org, "n@example.com", [])
    assert client.get("/api/users", headers=nobody).status_code == 403
    viewer = as_user(client, db, org, "v@example.com", ["users.view"])
    assert client.get("/api/users", headers=viewer).status_code == 200
    assert client.post("/api/users", json=NEW_USER, headers=viewer).status_code == 403


# --- Creating ------------------------------------------------------------------------


def test_create_user_with_role_who_can_then_log_in(client, auth_headers):
    role = client.post(
        "/api/roles", json={"name": "Viewer", "permission_keys": ["users.view"]}, headers=auth_headers
    ).json()
    response = client.post(
        "/api/users", json={**NEW_USER, "role_ids": [role["id"]]}, headers=auth_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "bob@example.com"
    assert [r["name"] for r in body["roles"]] == ["Viewer"]

    bob = login_as(client, "bob@example.com")
    assert client.get("/api/users", headers=bob).status_code == 200  # users.view
    assert client.post("/api/users", json=NEW_USER, headers=bob).status_code == 403


def test_new_user_joins_the_callers_organization_only(client, db, auth_headers):
    other = make_org(db, "Other")
    response = client.post(
        "/api/users",
        json={**NEW_USER, "organization_id": str(other.id)},  # ignored: not part of the schema
        headers=auth_headers,
    )
    assert response.status_code == 201
    created = db.scalar(select(User).where(User.email == "bob@example.com"))
    assert created.organization_id == my_org(db).id


def test_duplicate_email_is_409_even_across_organizations(client, db, auth_headers):
    other = make_org(db, "Other")
    make_user(db, other, "bob@example.com", [])
    assert client.post("/api/users", json=NEW_USER, headers=auth_headers).status_code == 409


def test_weak_password_is_422(client, auth_headers):
    response = client.post(
        "/api/users", json={**NEW_USER, "password": "short"}, headers=auth_headers
    )
    assert response.status_code == 422


def test_foreign_or_unknown_role_id_is_422(client, db, auth_headers):
    foreign = make_role(db, make_org(db, "Other"), "Foreign", [])
    for rid in (foreign.id, uuid.uuid4()):
        response = client.post(
            "/api/users", json={**NEW_USER, "role_ids": [str(rid)]}, headers=auth_headers
        )
        assert response.status_code == 422


# --- Privilege escalation ------------------------------------------------------------


def test_cannot_assign_a_role_with_permissions_you_lack(client, db, org):
    caller = as_user(client, db, org, "m@example.com", ["users.manage", "users.view"])
    powerful = make_role(db, org, "Powerful", ["audit.view"])
    response = client.post(
        "/api/users", json={**NEW_USER, "role_ids": [str(powerful.id)]}, headers=caller
    )
    assert response.status_code == 403
    assert db.scalar(select(User).where(User.email == "bob@example.com")) is None


def test_cannot_promote_someone_to_a_role_you_lack_via_patch(client, db, org):
    caller = as_user(client, db, org, "m@example.com", ["users.manage"])
    powerful = make_role(db, org, "Powerful", ["audit.view"])
    target = make_user(db, org, "t@example.com", [])
    response = client.patch(
        f"/api/users/{target.id}", json={"role_ids": [str(powerful.id)]}, headers=caller
    )
    assert response.status_code == 403


def test_users_manage_alone_cannot_disable_an_admin(client, db, auth_headers):
    org = my_org(db)
    caller = as_user(client, db, org, "m@example.com", ["users.manage"])
    admin = db.scalar(select(User).where(User.email == "ada@example.com"))
    response = client.patch(f"/api/users/{admin.id}", json={"is_active": False}, headers=caller)
    assert response.status_code == 403
    db.expire_all()
    assert db.get(User, admin.id).is_active is True


# --- Updating ------------------------------------------------------------------------


def test_patch_changes_name_and_replaces_roles(client, db, auth_headers):
    org = my_org(db)
    a = make_role(db, org, "A", ["users.view"])
    b = make_role(db, org, "B", ["roles.view"])
    target = make_user(db, org, "t@example.com", [a])

    body = client.patch(
        f"/api/users/{target.id}",
        json={"full_name": "New Name", "role_ids": [str(b.id)]},
        headers=auth_headers,
    ).json()
    assert body["full_name"] == "New Name"
    assert [r["name"] for r in body["roles"]] == ["B"]
    assert body["email"] == "t@example.com"  # untouched


def test_disabled_user_cannot_log_in_or_use_an_old_token(client, db, auth_headers):
    org = my_org(db)
    target = make_user(db, org, "t@example.com", [make_role(db, org, "R", ["users.view"])])
    token_headers = login_as(client, "t@example.com")
    assert client.get("/api/users", headers=token_headers).status_code == 200

    client.patch(f"/api/users/{target.id}", json={"is_active": False}, headers=auth_headers)

    assert client.get("/api/users", headers=token_headers).status_code == 401
    login = client.post("/api/auth/login", json={"email": "t@example.com", "password": TEST_PASSWORD})
    assert login.status_code == 401


# --- Last-admin guard ----------------------------------------------------------------


def test_last_admin_cannot_be_disabled(client, db, auth_headers):
    me = db.scalar(select(User))
    response = client.patch(f"/api/users/{me.id}", json={"is_active": False}, headers=auth_headers)
    assert response.status_code == 409


def test_last_admin_cannot_lose_the_admin_role(client, db, auth_headers):
    me = db.scalar(select(User))
    response = client.patch(f"/api/users/{me.id}", json={"role_ids": []}, headers=auth_headers)
    assert response.status_code == 409
    db.expire_all()
    assert [r.name for r in db.get(User, me.id).roles] == ["Admin"]


def test_with_a_second_admin_the_first_can_step_down(client, db, auth_headers):
    admin_id = admin_role_id(client, auth_headers)
    created = client.post(
        "/api/users", json={**NEW_USER, "role_ids": [admin_id]}, headers=auth_headers
    ).json()
    ada = db.scalar(select(User).where(User.email == "ada@example.com"))

    assert client.patch(
        f"/api/users/{ada.id}", json={"is_active": False}, headers=auth_headers
    ).status_code == 200
    # Ada is now disabled, so Bob is the last admin and is protected.
    bob = login_as(client, "bob@example.com")
    response = client.patch(f"/api/users/{created['id']}", json={"is_active": False}, headers=bob)
    assert response.status_code == 409


def test_a_disabled_admin_does_not_count_as_a_remaining_admin(client, db, auth_headers):
    org = my_org(db)
    admin = db.scalar(select(Role).where(Role.organization_id == org.id, Role.is_system))
    ghost = make_user(db, org, "ghost@example.com", [admin])
    ghost.is_active = False
    db.commit()
    me = db.scalar(select(User).where(User.email == "ada@example.com"))
    response = client.patch(f"/api/users/{me.id}", json={"is_active": False}, headers=auth_headers)
    assert response.status_code == 409


# --- Tenant isolation ----------------------------------------------------------------


def test_other_organizations_users_are_invisible_and_untouchable(client, db, auth_headers):
    other = make_org(db, "Other")
    foreign = make_user(db, other, "f@example.com", [])
    url = f"/api/users/{foreign.id}"

    assert client.get(url, headers=auth_headers).status_code == 404
    assert client.patch(url, json={"is_active": False}, headers=auth_headers).status_code == 404
    assert "f@example.com" not in client.get("/api/users", headers=auth_headers).text
    db.expire_all()
    assert db.get(User, foreign.id).is_active is True


def test_listing_users_uses_a_constant_number_of_queries(client, db, auth_headers):
    from sqlalchemy import event

    from app.database import engine

    org = my_org(db)
    role = make_role(db, org, "R", ["users.view"])

    def count_queries() -> int:
        statements: list[str] = []

        def record(conn, cursor, statement, *args):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            assert client.get("/api/users", headers=auth_headers).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", record)
        return len(statements)

    few = count_queries()
    for i in range(10):
        make_user(db, org, f"u{i}@example.com", [role])
    assert count_queries() == few  # 10 more users, same number of queries (no N+1)
