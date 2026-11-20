"""add roles, permissions and user_roles; replace users.role

Revision ID: a3c91e7d4b20
Revises: f48135c8c951
Create Date: 2026-11-20 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3c91e7d4b20"
down_revision: Union[str, Sequence[str], None] = "f48135c8c951"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The catalogue as it was in v2. It is copied here on purpose instead of imported
# from app/permissions.py: a migration describes one moment in history and must
# keep working unchanged even after the catalogue in code grows in v3 and v4.
V2_PERMISSIONS = {
    "org.view": "See organization details",
    "org.manage": "Edit organization details",
    "users.view": "List users and their roles",
    "users.manage": "Create, edit and disable users; assign roles",
    "roles.view": "List roles and their permissions",
    "roles.manage": "Create, edit and delete roles",
    "audit.view": "Read the audit log",
}


def upgrade() -> None:
    op.create_table(
        "permissions",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), server_default="", nullable=False),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),
    )
    op.create_index(op.f("ix_roles_organization_id"), "roles", ["organization_id"], unique=False)
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_key", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_key"], ["permissions.key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_key"),
    )
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
    )
    op.create_index(op.f("ix_user_roles_role_id"), "user_roles", ["role_id"], unique=False)

    # --- Data: fill the catalogue ---
    permissions = sa.table(
        "permissions", sa.column("key", sa.String), sa.column("description", sa.String)
    )
    op.bulk_insert(
        permissions,
        [{"key": k, "description": d} for k, d in V2_PERMISSIONS.items()],
    )

    # --- Data: turn the old users.role column into real roles ---
    # Every existing organization gets a system "Admin" role holding every permission,
    # and every user with role = 'admin' (all of them in v1) is assigned to it.
    # Plain SQL, set-based: one statement per step, no Python loop over rows.
    op.execute(
        """
        INSERT INTO roles (organization_id, name, description, is_system)
        SELECT id, 'Admin', 'Full access to everything in the organization', true
        FROM organizations
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions (role_id, permission_key)
        SELECT r.id, p.key
        FROM roles r CROSS JOIN permissions p
        WHERE r.is_system AND r.name = 'Admin'
        """
    )
    op.execute(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users u
        JOIN roles r ON r.organization_id = u.organization_id
                    AND r.is_system AND r.name = 'Admin'
        WHERE u.role = 'admin'
        """
    )

    # --- Finally remove the old column (its CHECK constraint goes with it) ---
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")


def downgrade() -> None:
    # Lossy by design: custom roles and fine-grained permissions cannot be expressed in the
    # old single column, which only allows 'admin'. To avoid silently turning every Viewer
    # into a full admin, only holders of the system Admin role stay active; everyone else is
    # disabled (is_active = false) and must be re-enabled by hand after the rollback.
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=20), server_default="admin", nullable=False),
    )
    op.create_check_constraint("ck_users_role", "users", "role in ('admin')")
    op.execute(
        """
        UPDATE users SET is_active = false
        WHERE NOT EXISTS (
            SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = users.id AND r.is_system AND r.name = 'Admin'
        )
        """
    )
    op.drop_index(op.f("ix_user_roles_role_id"), table_name="user_roles")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_roles_organization_id"), table_name="roles")
    op.drop_table("roles")
    op.drop_table("permissions")
