import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Index,
    Table,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# Join tables. The composite primary key (both columns together) means the database
# itself refuses to store the same pair twice. ON DELETE CASCADE removes the link
# rows when either side is deleted, so no orphan links remain.
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_key",
        ForeignKey("permissions.key", ondelete="CASCADE"),
        primary_key=True,
    ),
)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        # The primary key index starts with user_id; this one serves
        # "which users hold this role?" lookups.
        index=True,
    ),
)


class Organization(Base):
    """A tenant: one company using the platform. Everything else belongs to one."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base):
    """A person who can log in. Always belongs to exactly one organization."""

    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users")


class Permission(Base):
    """One entry of the fixed catalogue in app/permissions.py, copied into the DB."""

    __tablename__ = "permissions"

    # The key itself is the primary key ("users.manage"). It is stable, readable in
    # queries and logs, and never changes, so a surrogate id would add nothing.
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    description: Mapped[str] = mapped_column(String(255))


class Role(Base):
    """A named set of permissions, owned by one organization."""

    __tablename__ = "roles"
    # Names are unique inside an organization, but two organizations can both have "Viewer".
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255), server_default="")
    # System roles (the "Admin" role created at registration) cannot be edited or deleted.
    is_system: Mapped[bool] = mapped_column(server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    organization: Mapped["Organization"] = relationship()
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions)
    users: Mapped[list["User"]] = relationship(secondary=user_roles, back_populates="roles")


class AuditLog(Base):
    """One security-relevant event: who did what to what, and when. Append-only."""

    __tablename__ = "audit_log"
    # The audit screen always asks "newest events of MY organization".
    __table_args__ = (Index("ix_audit_log_org_created", "organization_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    # SET NULL, not CASCADE: if a user row ever disappears, the history must stay.
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(100))  # e.g. "role.created"
    target_type: Mapped[str | None] = mapped_column(String(50))  # "role", "user", ...
    # Deliberately NOT a foreign key: the target may be deleted (a role) and the log
    # must still say what it was.
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # These two relationships are never read. They exist so SQLAlchemy knows an audit row
    # depends on its organization and user, and inserts those first when everything is
    # saved in one commit (registration creates all three at once). Without them the
    # insert order is undefined and the foreign key can fail.
    organization: Mapped["Organization"] = relationship()
    actor: Mapped["User | None"] = relationship()
