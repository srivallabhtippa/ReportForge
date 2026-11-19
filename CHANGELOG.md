# Changelog

Each version is a release with a stakeholder outcome. See [ROADMAP.md](ROADMAP.md) for the plan.

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
