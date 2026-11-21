# ADR 0005: Role-based access control (RBAC) model

**Status:** Accepted (v2, 2026-11).

## Context
v1 has one hard-coded role, `admin`, stored in `users.role`. v2 must let an admin create roles, create users, assign roles and control what each role can do, and it must record security-relevant actions. Datasets and reports do not exist yet (v3, v4), so the model must be able to cover them later without redesign.

## Decisions

1. **Four new tables.** `permissions` (the catalogue), `roles` (per organization), `role_permissions` (which role holds which permission), `user_roles` (which user holds which role). The last two are join tables with composite primary keys, so a pair cannot be stored twice.

2. **Permissions are a fixed catalogue defined in code.** A permission is a string `resource.action`, for example `users.manage`. The list lives in one Python module and is synchronised into the `permissions` table by a migration. Admins can only combine existing permissions into roles, never invent new ones. Reason: code can only enforce a permission it knows about. A permission invented in the UI would protect nothing.

   Initial catalogue:
   | Permission | Allows |
   |---|---|
   | `org.view` | see organization details |
   | `org.manage` | edit organization details |
   | `users.view` | list users and their roles |
   | `users.manage` | create, edit, disable users; assign roles |
   | `roles.view` | list roles and their permissions |
   | `roles.manage` | create, edit, delete roles |
   | `audit.view` | read the audit log |

   v3 and v4 add `datasets.*` and `reports.*` the same way: a new catalogue entry plus a migration.

3. **Roles belong to one organization** (`roles.organization_id`, indexed, `ON DELETE CASCADE`). Role names are unique per organization. One organization's "Viewer" is unrelated to another's.

4. **A user can hold many roles; effective permissions are the union.** There are no deny rules, so adding a role can never remove access, which keeps the reasoning simple ("what can this user do?" is a union, not a conflict resolution).

5. **System role "Admin".** `roles.is_system = true`. Registration creates it for the new organization with every permission and assigns it to the first user. System roles cannot be renamed, deleted or have permissions removed, so an organization cannot lock itself out through the role editor.

6. **Central enforcement.** One FastAPI dependency, `require_permission("users.manage")`, is the only way routes check access. Routes never inspect roles by name. It answers 401 if not authenticated and 403 if authenticated but missing the permission.

7. **Permissions are read from the database on every request, not stored in the JWT.** Same reasoning as v1's fresh user lookup: a token says who you were at login, the database says what you may do now. Removing a role takes effect on the next request instead of when the token expires. Cost: one extra query per request, accepted for now and revisited in v4 (caching).

8. **Tenant isolation returns 404, not 403.** Asking for a role or user of another organization behaves as if it does not exist, so ids cannot be used to discover other tenants' data.

9. **Four guards in the endpoints:**
   - the last active user holding the Admin role cannot be disabled or lose that role;
   - a user can only grant roles whose permissions they already hold (no privilege escalation);
   - system roles are immutable (decision 5);
   - nobody can edit, disable or re-role a user, or edit or delete a role, that holds permissions they lack. A holder of only `users.manage` cannot disable an admin, and a holder of only `roles.manage` cannot gut a more powerful role (added after the v2 code review for roles; users had it from the start). Shared in `app/authz.py`.

   The last-admin check takes a row lock, only when a change could remove an active admin and before reading the target's state, (`SELECT ... FOR UPDATE`) on the organization's Admin role, so two admins demoting each other at the same moment are handled one after the other, and one of them is refused.

10. **Audit log is a separate append-only table** (`audit_log`: organization, actor user, action, target type and id, JSON details, timestamp). Rows are inserted in the same transaction as the change they describe, so a change and its record succeed or fail together. The API exposes read access only. The log stores no passwords or tokens.

    Recorded in v2: registration, successful login, role created/updated/deleted, user created, and per-kind user changes (`user.updated`, `user.disabled`, `user.enabled`, `user.roles_changed`). **Failed logins are not recorded**: logging only for existing emails would make those responses slower and reveal which emails are registered. Rate limiting and lockout in v4 cover failed attempts. `target_id` is not a foreign key, so the log still describes deleted roles. Append-only is by convention (no code path updates or deletes rows, and the API is read-only); database-level enforcement is a v4 hardening item.

11. **Migration of `users.role`.** For each existing organization the migration creates the Admin role, gives it all permissions, assigns it to users whose `role = 'admin'`, then drops the `role` column and its CHECK constraint. `UserOut.role` in the API is replaced by a list of role names.

## Alternatives considered
- **One role per user** (`users.role_id`): simpler, but forces duplicate roles such as "Editor+Auditor" and needs a migration when two roles are needed.
- **Admin-defined permissions:** flexible, but unenforceable (decision 2).
- **Permissions inside the JWT:** no extra query, but stale until expiry and the token grows with every permission. Rejected until measurements say otherwise.
- **Global roles shared by all organizations:** fewer rows, but organizations could not customise roles, which is the product's point.
- **Full ABAC / policy engine (OPA, Casbin):** powerful, but heavy for feature-level permissions. Revisit if column or row restrictions arrive.

## Consequences
- Every new feature adds a catalogue entry, a migration and a `require_permission` call; that is a small, reviewable checklist.
- A permission check costs a query per request until caching (v4).
- Column and row restrictions are out of scope. The `resource.action` naming leaves room to scope a permission to a dataset later (for example a `dataset_id` on a role assignment).
- Because email is globally unique (ADR 0004), creating a user with an email that exists in another organization answers 409, so a `users.manage` holder can test whether an email is registered somewhere. Accepted for now; rate limiting in v4, and per-organization emails would remove it at the cost of asking for the organization at login.
- Audit paging uses offset, so new events arriving between page loads can repeat a row; keyset paging on `(created_at, id)` is the fix if it matters.
- Audit rows grow without bound; retention and export are future work (GDPR section of v4).
