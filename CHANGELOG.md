# Changelog

Each version is a release with a stakeholder outcome. See [ROADMAP.md](ROADMAP.md) for the plan.

## v2 Access control

**Outcome:** an admin creates roles and users, assigns roles, and controls what each role can see and do. Every security-relevant action is recorded in an audit log.

### Added
- **Data model:** `permissions` (fixed catalogue), `roles` (per organization), `role_permissions`, `user_roles` and `audit_log`. The v1 `users.role` column is replaced; the migration turns every existing user into a holder of their organization's new system "Admin" role (ADR 0005).
- **Central enforcement:** `require_permission("...")` is the only way routes check access. 401 if not logged in, 403 if the permission is missing. Permissions are the union of all of a user's roles and are read from the database on every request, so removing a role takes effect immediately. A typo in a permission name fails when the app starts.
- **Roles API:** `GET /api/permissions`, `GET/POST /api/roles`, `GET/PATCH/DELETE /api/roles/{id}`. The Admin role is a protected system role.
- **Users API:** `GET/POST /api/users`, `GET/PATCH /api/users/{id}` (name, enable/disable, replace roles).
- **Audit log:** registration, successful login, role created/updated/deleted, user created and per-kind user changes. Written in the same transaction as the change. Read with `GET /api/audit-log` (filter by action, paging).
- **`/api/me` returns `permissions`**, and `UserOut` returns `roles` and `is_active` instead of a single `role`.
- **Frontend:** Users, Roles and Audit log pages inside a shared shell. Menu entries and buttons appear only for permissions the user holds; pages are guarded; checkboxes for permissions you cannot grant are disabled.
- **Tests:** 88 backend tests (61 new), including a route inventory that fails if any `/api` route lacks authentication, a data-migration test on v1-shaped rows, and a two-thread concurrency test for the last-admin guard.
- **Docs:** ADR 0005 (RBAC model); ADR 0004 marked as superseded for the role column.

### Security notes
- **Four guards:** the last active admin cannot be disabled or lose the Admin role (row lock prevents two admins removing each other at once); you cannot grant permissions you do not hold; system roles are immutable; you cannot manage a user who holds permissions you lack.
- Other organizations' roles, users and audit rows answer 404 (not 403), so ids reveal nothing.
- The audit log never stores passwords or hashes. Failed logins are deliberately not logged (it would reveal which emails exist through response timing); rate limiting in v4 covers them.
- Found in the v2 code review and fixed: roles could be edited or deleted by someone who lacked their permissions; the last-admin check read state before taking its lock; list endpoints ran one query per row; deleting a role left no per-user audit events; the migration's downgrade made every user an admin (it now disables non-admins).
- Found during the work and fixed: SQLAlchemy inserted an audit row before its organization during registration (foreign key error). Relationships now declare the order.
- The test for the last-admin race was verified to fail (0 admins left) when the row lock is removed.

### Known limitations (planned)
- **No password change or reset.** The admin sets a user's first password and the user cannot change it yet. No email invitations or verification.
- Users cannot be deleted, only disabled.
- Creating a user with an email that exists in another organization answers 409, so an admin can test whether an email is registered somewhere (global email uniqueness, ADR 0004; rate limiting in v4).
- Audit log paging is offset-based and can repeat a row if events arrive between page loads.
- `org.view` and `org.manage` exist in the catalogue but no endpoint uses them yet (organization editing comes later).
- No column or row restrictions and no dataset permissions (v3).
- One extra permission query per request (caching in v4). Tokens are still in `localStorage` and not revocable before expiry (v4, ADR 0003), although permissions and the disabled flag are checked live.
- No rate limiting. The audit log is append-only by convention, not enforced by the database; no retention or export (v4).
- Role names are unique case-sensitively ("Viewer" and "viewer" can coexist). The audit page's action filter list is hardcoded in the frontend.
- No frontend tests. The Docker stack was not re-run for v2 (the migrations run on container start, and tests use real migrations, but a full `docker compose up` is part of the v2 review).

## v1 Foundation

**Outcome:** an admin registers an organization, logs in, and sees a protected, empty workspace. The whole stack starts with one command.

### Added
- **Backend:** FastAPI application with configuration from environment variables (`pydantic-settings`), SQLAlchemy connection with a session per request, and Alembic migrations.
- **Data model:** `organizations` and `users` tables (UUID keys, tenancy via `organization_id`).
- **Auth:** `POST /api/auth/register` (organization and first admin in one transaction), `POST /api/auth/login` (Argon2id check, JWT), `GET /api/me` (protected).
- **Frontend:** React sign-up, login and workspace pages with client-side routing and route guards.
- **Tests:** 27 automated backend tests against a separate PostgreSQL test database, built with the real migrations.
- **Docker:** Compose stack with PostgreSQL (non-superuser app role created by an init script), backend (non-root, runs migrations on start) and nginx-served frontend, with health-based start order.
- **Docs:** ADRs 0001-0004 and this changelog.

### Security notes
- Passwords stored only as Argon2id hashes; never returned by the API.
- Login gives identical answers for unknown email and wrong password.
- Tokens with a bad signature, wrong algorithm, expiry, edited payload or disabled user are refused.
- Found in review and fixed: the public `/health/db` endpoint revealed the database user and name. It now returns only a status.

### Known limitations (planned)
- No rate limiting on login or registration; anyone can create organizations (v4).
- Token kept in `localStorage`; no refresh or revocation (v4, ADR 0003).
- No email verification or password reset.
- `/docs` is always enabled; disable or protect it in production (v4).
- Dependencies are pinned directly but not fully locked; Docker uses Python 3.12 while local development used 3.15.
- No frontend tests; no handling of mid-session token expiry.
- Roles are a single `admin` value (v2).
