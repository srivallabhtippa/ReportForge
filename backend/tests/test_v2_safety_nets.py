"""Tests that guard the v2 design as a whole, not one endpoint.

1. Route inventory: no /api route can be added without authentication.
2. Migration: the v1 -> v2 data migration works on real v1-shaped rows.
3. Concurrency: two admins demoting each other at once cannot leave zero admins.
4. Registration is all-or-nothing.
"""

import threading

from alembic import command
from alembic.config import Config
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.database import SessionLocal, engine
from app.main import app
from app.models import AuditLog, Organization, Role, User
from tests.conftest import BACKEND_DIR, TEST_PASSWORD, login_as, make_org, make_role, make_user

# The only /api routes that may be called without a token.
PUBLIC_API_ROUTES = {("POST", "/api/auth/register"), ("POST", "/api/auth/login")}


# --- 1. Route inventory --------------------------------------------------------------


def test_every_api_route_rejects_anonymous_requests(client):
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            if (method, route.path) in PUBLIC_API_ROUTES:
                continue
            # Fill path parameters with a well-formed dummy id.
            path = route.path.replace("{role_id}", "00000000-0000-0000-0000-000000000000")
            path = path.replace("{user_id}", "00000000-0000-0000-0000-000000000000")
            response = client.request(method, path)
            assert response.status_code == 401, f"{method} {route.path} is not protected"
            checked += 1
    assert checked >= 10  # guards against the loop silently checking nothing


# --- 2. Migration --------------------------------------------------------------------


def test_v2_migration_converts_v1_users_into_admin_role_holders():
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    v1 = "f48135c8c951"
    try:
        command.downgrade(config, v1)  # back to the v1 schema (tables are empty here)
        with engine.begin() as c:
            c.execute(text("INSERT INTO organizations (name) VALUES ('A'), ('B')"))
            c.execute(
                text(
                    "INSERT INTO users (organization_id, email, password_hash, full_name) "
                    "SELECT id, lower(name) || n || '@x.com', 'hash', 'N' "
                    "FROM organizations, (VALUES ('1'), ('2')) AS t(n)"
                )
            )
        command.upgrade(config, "head")

        with engine.connect() as c:
            assert c.execute(text("select count(*) from roles")).scalar() == 2
            assert c.execute(text("select count(*) from user_roles")).scalar() == 4
            # Every user ended up with exactly one role, the Admin of their own organization.
            wrong = c.execute(
                text(
                    "select count(*) from users u "
                    "join user_roles ur on ur.user_id = u.id "
                    "join roles r on r.id = ur.role_id "
                    "where r.organization_id <> u.organization_id or r.name <> 'Admin'"
                )
            ).scalar()
            assert wrong == 0
            per_role = c.execute(text("select count(*) from role_permissions group by role_id")).scalars().all()
            assert per_role == [7, 7]
    finally:
        command.upgrade(config, "head")  # always leave the schema at head for other tests


def test_downgrade_disables_everyone_who_was_not_an_admin(db, org):
    admin = make_role(db, org, "Admin", ["users.view"], is_system=True)
    viewer = make_role(db, org, "Viewer", ["users.view"])
    make_user(db, org, "admin@example.com", [admin])
    make_user(db, org, "viewer@example.com", [viewer])
    make_user(db, org, "nobody@example.com", [])

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    try:
        command.downgrade(config, "f48135c8c951")
        with engine.connect() as c:
            active = dict(c.execute(text("select email, is_active from users")).all())
        # In v1 every user is an admin, so only genuine admins may stay able to log in.
        assert active == {
            "admin@example.com": True,
            "viewer@example.com": False,
            "nobody@example.com": False,
        }
    finally:
        command.upgrade(config, "head")


# --- 3. Concurrency ------------------------------------------------------------------


def test_two_admins_demoting_each_other_at_once_never_leave_zero_admins(client, db, auth_headers):
    organization = db.scalar(select(User)).organization
    admin_role = db.scalar(select(Role).where(Role.organization_id == organization.id, Role.is_system))
    make_user(db, organization, "bob@example.com", [admin_role])
    ada = db.scalar(select(User).where(User.email == "ada@example.com"))
    bob = db.scalar(select(User).where(User.email == "bob@example.com"))
    ada_headers, bob_headers = auth_headers, login_as(client, "bob@example.com")

    for attempt in range(8):
        barrier = threading.Barrier(2)  # both requests are released at the same instant
        results: dict[str, int] = {}

        def disable(who: str, target_id, headers):
            local_client = TestClient(app)  # one client per thread
            barrier.wait()
            results[who] = local_client.patch(
                f"/api/users/{target_id}", json={"is_active": False}, headers=headers
            ).status_code

        threads = [
            threading.Thread(target=disable, args=("ada", bob.id, ada_headers)),
            threading.Thread(target=disable, args=("bob", ada.id, bob_headers)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        with SessionLocal() as check:
            active_admins = check.scalar(
                select(func.count())
                .select_from(User)
                .where(User.organization_id == organization.id, User.is_active.is_(True))
            )
        assert active_admins >= 1, f"attempt {attempt}: organization left without an admin {results}"

        # Re-enable both for the next round.
        with engine.begin() as c:
            c.execute(text("UPDATE users SET is_active = true"))


# --- 4. Registration is all-or-nothing -----------------------------------------------


def test_failed_registration_leaves_no_partial_data(client, register, db):
    assert register().status_code == 201
    counts_before = [db.scalar(select(func.count()).select_from(t)) for t in (Organization, User, Role, AuditLog)]

    # Same email again: the user insert fails, so the organization, Admin role and audit
    # row prepared in the same transaction must all be rolled back.
    assert register(organization_name="Second Org").status_code == 409

    db.expire_all()
    counts_after = [db.scalar(select(func.count()).select_from(t)) for t in (Organization, User, Role, AuditLog)]
    assert counts_after == counts_before
