import base64
import json
from datetime import datetime, timedelta, timezone

import jwt

from app.models import User
from tests.conftest import TEST_SECRET_KEY


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def good_claims(client, auth_headers) -> dict:
    """The claims inside a genuine token (we know the test key, so we can read it)."""
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    return jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])


# --- The happy path ------------------------------------------------------------


def test_me_returns_the_logged_in_user_and_organization(client, auth_headers):
    response = client.get("/api/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "ada@example.com"
    assert body["organization"]["name"] == "Acme Supermarkets"
    assert "users.manage" in body["permissions"]  # the registering admin holds everything


def test_me_lists_only_the_permissions_the_user_holds(client, db, org):
    from tests.conftest import login_as, make_role, make_user

    make_user(db, org, "v@example.com", [make_role(db, org, "Viewer", ["users.view"])])
    body = client.get("/api/me", headers=login_as(client, "v@example.com")).json()
    assert body["permissions"] == ["users.view"]


# --- Requests that must be refused ---------------------------------------------


def test_me_without_a_token_is_refused(client):
    assert client.get("/api/me").status_code == 401


def test_me_with_a_garbage_token_is_refused(client):
    assert client.get("/api/me", headers=bearer("not.a.token")).status_code == 401


def test_me_with_an_expired_token_is_refused(client, auth_headers):
    claims = good_claims(client, auth_headers)
    claims["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = jwt.encode(claims, TEST_SECRET_KEY, algorithm="HS256")

    assert client.get("/api/me", headers=bearer(token)).status_code == 401


def test_me_with_a_token_signed_by_someone_else_is_refused(client, auth_headers):
    claims = good_claims(client, auth_headers)
    token = jwt.encode(claims, "an-attackers-own-secret-0123456789abcdef", algorithm="HS256")

    assert client.get("/api/me", headers=bearer(token)).status_code == 401


def test_me_with_an_unsigned_alg_none_token_is_refused(client, auth_headers):
    claims = good_claims(client, auth_headers)
    token = jwt.encode(claims, None, algorithm="none")

    assert client.get("/api/me", headers=bearer(token)).status_code == 401


def test_me_with_an_edited_payload_is_refused(client, auth_headers):
    # Change the organization inside the token but keep the old signature.
    header, payload, signature = auth_headers["Authorization"].split(" ")[1].split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["org"] = "00000000-0000-0000-0000-000000000000"
    edited = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()

    token = f"{header}.{edited}.{signature}"

    assert client.get("/api/me", headers=bearer(token)).status_code == 401


def test_me_with_a_valid_token_of_a_disabled_user_is_refused(client, auth_headers, db):
    db.execute(User.__table__.update().values(is_active=False))
    db.commit()

    # The token itself is still perfectly valid; the database says "no longer allowed".
    assert client.get("/api/me", headers=auth_headers).status_code == 401


# --- Tenant isolation ----------------------------------------------------------


def test_each_user_only_ever_sees_their_own_organization(client, register, login):
    register(organization_name="Org One", email="one@example.com")
    register(organization_name="Org Two", email="two@example.com")

    def organization_seen_by(email: str) -> str:
        token = login(email=email).json()["access_token"]
        return client.get("/api/me", headers=bearer(token)).json()["organization"]["name"]

    assert organization_seen_by("one@example.com") == "Org One"
    assert organization_seen_by("two@example.com") == "Org Two"
