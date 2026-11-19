import pytest
from sqlalchemy import func, select

from app.models import Organization, User
from tests.conftest import VALID_REGISTRATION


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


# --- Registration --------------------------------------------------------------


def test_register_creates_organization_and_admin(register, db):
    response = register(email="Ada@Example.COM")

    assert response.status_code == 201
    body = response.json()
    assert body["organization"]["name"] == "Acme Supermarkets"
    assert body["user"]["email"] == "ada@example.com"  # stored in lowercase
    assert body["user"]["role"] == "admin"
    assert count(db, Organization) == 1
    assert count(db, User) == 1


def test_register_never_exposes_or_stores_the_plain_password(register, db):
    response = register()

    assert "password" not in response.text  # neither "password" nor "password_hash"
    stored = db.scalar(select(User.password_hash))
    assert stored != VALID_REGISTRATION["password"]
    assert stored.startswith("$argon2id$")


def test_register_rejects_duplicate_email_ignoring_case_and_creates_nothing(register, db):
    assert register().status_code == 201

    second = register(organization_name="Other Org", email="ADA@example.com")

    assert second.status_code == 409
    # Atomicity: the failed attempt must not leave a half-created organization.
    assert count(db, Organization) == 1
    assert count(db, User) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"email": "not-an-email"},
        {"organization_name": "x"},
        {"full_name": ""},
    ],
    ids=["short-password", "bad-email", "short-org-name", "empty-name"],
)
def test_register_validates_input(register, db, overrides):
    response = register(**overrides)

    assert response.status_code == 422
    assert count(db, Organization) == 0


# --- Login ---------------------------------------------------------------------


def test_login_returns_a_bearer_token(register, login):
    register()

    response = login()

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 30 * 60
    assert body["access_token"].count(".") == 2  # header.payload.signature


def test_login_ignores_email_case(register, login):
    register()

    assert login(email="ADA@EXAMPLE.COM").status_code == 200


def test_wrong_password_and_unknown_email_look_identical(register, login):
    register()

    wrong_password = login(password="not-the-right-password")
    unknown_email = login(email="nobody@example.com")

    # Same status and same message: an attacker cannot tell which emails exist.
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_disabled_user_cannot_log_in(register, login, db):
    register()
    db.execute(User.__table__.update().values(is_active=False))
    db.commit()

    assert login().status_code == 401
