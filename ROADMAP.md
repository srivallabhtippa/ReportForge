# ReportForge Roadmap

## Product vision

ReportForge is a multi-tenant data platform. An organization registers, and its first user becomes the **admin**. During onboarding the admin describes what the organization tracks (supermarket sales per area, software downloads, rents, anything else) and a dataset is set up for it. The admin then creates roles and users and decides what each role can see: users, organization details, datasets and reports. Data is imported from CSV/Excel, stored safely, and turned into reports and PDFs. AI agents come last, once the full product works.

**Learning goal:** understand how a production web application works end to end (Docker, security, databases, APIs, optimization). Each version is a release with a clear stakeholder outcome.

**Stack:** FastAPI, React + Vite, PostgreSQL, Redis, Docker. An analytical database (ClickHouse is the leading candidate) is introduced in v4 only if measurements show Postgres is too slow.
**Pace:** about 5-8 hours per week. The AI-agent version (v5) is built only after v1-v4 work as a full product.

## Versions

| Version | Release | Stakeholder outcome | Concepts |
|---|---|---|---|
| v0 (done) | Skeleton | FastAPI + React + compose + nginx proxy | Containers, reverse proxy |
| **v1** | **Foundation** | An admin registers an organization, logs in, and sees an empty workspace. Full stack starts with one command. | Relational design, migrations, auth (hashing, JWT), tenancy, API design, Docker |
| **v2** | **Access control** | Admin creates roles and users, assigns roles, and controls what each role sees. Audit log records actions. | RBAC, permission modelling, central enforcement, audit trails, GDPR basics |
| **v3** | **Data platform** | Onboarding questionnaire (templates: sales, downloads, rent) defines datasets. CSV/Excel import with validation driven by the dataset definition, running in background jobs. | Dynamic schemas, metadata-driven validation, queues/workers, Redis |
| **v4** | **Insights and production readiness** | Reports, PDFs, dashboards. Hardened, monitored and load-tested. Analytical database added if measurements justify it. | Analytical storage, caching, query tuning, hardening, OWASP testing, observability |
| **v5** | **AI agents** | An assistant answers questions about an organization's data and helps with setup, always inside the asking user's permissions. | Agent design, tool use, guardrails, evaluation |

v4 is the heaviest release and is split into milestone 4a (reports and analytics) and 4b (hardening and observability).

## v1 Foundation: scope

**In:** config via `.env`, Postgres connection (SQLAlchemy), `organizations` and `users` tables, Alembic migrations, organization registration with first admin, password hashing, login with JWT, protected `/me` endpoint, frontend sign-up/login/workspace pages, basic tests, full stack in Docker.

**Out (deliberately):** roles beyond a plain `admin` column (v2), datasets and imports (v3), reports and the analytical database (v4), email verification and password reset.

**Demo script:** register "Acme Supermarkets" with an admin, log in, see the workspace, confirm `/me` rejects requests without a token, start everything with one command.

**Steps:** 1 config, 2 DB connection, 3 models, 4 Alembic, 5 registration + hashing, 6 login + JWT, 7 `/me`, 8 frontend, 9 tests, 10 Docker, 11 review.

## Review at the end of every version

1. **Demo:** show it working end to end.
2. **Code review:** correctness, security, structure.
3. **Explain it back:** 3-5 "why" questions, interview style.
4. **ADR:** a short decision record in `docs/adr/` (what was chosen, what was rejected, why).
5. **Changelog:** one entry saying what improved and why.
6. **Tag:** `git tag vN`.

## Open decisions

- Dynamic data storage approach (JSONB with field definitions is the leading option). ADR to be written before v3.
- Permission depth: features and whole datasets in v2; column and row restrictions later.
- Analytical database: decided in v4 from measurements.
