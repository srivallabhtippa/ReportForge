from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# The engine owns a pool of database connections. It is created once, at import
# time, and shared by the whole app. get_secret_value() reveals the URL only here.
engine = create_engine(
    get_settings().database_url.get_secret_value(),
    pool_pre_ping=True,  # test a connection before using it, so stale ones are replaced
)

# A factory for sessions. A session is one "conversation" with the database:
# it tracks the objects you load and the changes you make until you commit.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Parent class of every table model (organizations, users, ...) in step 3."""


def get_db() -> Iterator[Session]:
    # FastAPI dependency: each request gets its own session, and the session is
    # always closed afterwards, even if the endpoint raised an error.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
