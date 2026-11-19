"""Shared test setup.

Tests run against a REAL PostgreSQL database, but never the development one.
The environment is switched to "<dev database>_test" BEFORE any app code is
imported, because the app reads its settings once at import time.
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parent.parent

# A fixed, throwaway signing key for tests. It beats the real key in .env, so tests
# never touch the real secret, and tests can forge tokens with a key they know.
TEST_SECRET_KEY = "test-only-secret-key-0123456789abcdef0123456789abcdef"


def _test_database_url() -> str:
    from app.config import Settings

    # Credentials come from DATABASE_URL (environment) or backend/.env.
    base = os.environ.get("DATABASE_URL") or Settings(
        _env_file=BACKEND_DIR / ".env"
    ).database_url.get_secret_value()
    url = make_url(base)
    if not url.database.endswith("_test"):
        url = url.set(database=f"{url.database}_test")
    return url.render_as_string(hide_password=False)


os.environ["DATABASE_URL"] = _test_database_url()
os.environ["SECRET_KEY"] = TEST_SECRET_KEY
os.environ["APP_ENV"] = "test"

# Imported only now, after the environment points at the test database.
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    # Safety net: the tests delete data, so refuse to run on anything but a test DB.
    assert engine.url.database.endswith("_test"), "refusing to run on a non-test database"

    # Build the schema with the real Alembic migrations, so the migrations are
    # tested too. If a migration is broken, the whole suite fails right here.
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables(migrated_database):
    # Every test starts with empty tables, so tests cannot affect each other.
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE users, organizations CASCADE"))
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    # A session for tests that need to look at, or change, the database directly.
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


VALID_REGISTRATION = {
    "organization_name": "Acme Supermarkets",
    "full_name": "Ada Admin",
    "email": "ada@example.com",
    "password": "correct-horse-battery",
}


@pytest.fixture
def register(client):
    """register(**overrides) -> response. Starts from a valid sign-up payload."""

    def _register(**overrides):
        return client.post("/api/auth/register", json={**VALID_REGISTRATION, **overrides})

    return _register


@pytest.fixture
def login(client):
    """login(email, password) -> response."""

    def _login(email=VALID_REGISTRATION["email"], password=VALID_REGISTRATION["password"]):
        return client.post("/api/auth/login", json={"email": email, "password": password})

    return _login


@pytest.fixture
def auth_headers(register, login):
    """Registers the default admin, logs in, returns the Authorization header."""
    assert register().status_code == 201
    token = login().json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
