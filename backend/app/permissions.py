"""The permission catalogue: every permission the application can enforce.

Permissions are defined here, in code, because code can only enforce what it knows
about (ADR 0005). The `permissions` table is a copy of this list that roles can
point to with foreign keys. Adding a permission means: add it here, then write a
migration that inserts it into the table.
"""

# key -> human-readable description. Keys follow "resource.action".
PERMISSIONS: dict[str, str] = {
    "org.view": "See organization details",
    "org.manage": "Edit organization details",
    "users.view": "List users and their roles",
    "users.manage": "Create, edit and disable users; assign roles",
    "roles.view": "List roles and their permissions",
    "roles.manage": "Create, edit and delete roles",
    "audit.view": "Read the audit log",
}

ADMIN_ROLE_NAME = "Admin"
