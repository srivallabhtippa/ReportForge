# ReportForge Roadmap

ReportForge is a personal learning project: a reporting platform for multiple client companies. Users import CSV/Excel files (validated), the data is stored in PostgreSQL, processing runs in background jobs, and PDF reports are generated on demand, with role-based access and an audit log.

**Goal:** learn how a production web application works end to end (Docker, security, database, APIs, optimization). Each version is one improvement with a clear reason.

**Stack:** FastAPI, React + Vite, PostgreSQL, Redis, Docker Compose (local hosting for now).
**Pace:** about 5-8 hours per week, roughly one version per 1-2 weeks.

## Versions

| Version | Theme | What gets built | Concepts |
|---|---|---|---|
| v0 (done) | Skeleton | FastAPI, React, compose, nginx proxy | Containers, reverse proxy |
| v1 | Persistence | Postgres in compose, SQLAlchemy, Alembic migrations, `clients` and `reports` tables, basic CRUD | Data modelling, migrations, volumes, env config |
| v2 | Ingestion | CSV/Excel upload, schema validation, row-level error reports | API design, file handling, validation |
| v3 | Auth + RBAC | Login, password hashing, JWT, roles (admin/analyst/viewer), `tenant_id` on every row | AuthN vs AuthZ, multi-tenancy |
| v4 | Background jobs | Redis, worker (Celery/ARQ), job status, retries, progress | Async processing, queues, idempotency |
| v5 | PDF reports | PDF generation job, templates, downloads, file storage (MinIO) | Rendering pipelines, object storage |
| v6 | Audit + compliance | Append-only audit log, GDPR basics (retention, deletion, export) | Auditability, data protection |
| v7 | Performance | Indexes, EXPLAIN, N+1 fixes, pagination, Redis caching | Query tuning, cache invalidation |
| v8 | Hardening | TLS via proxy, secrets handling, rate limiting, security headers, dependency scanning, non-root containers | Defence in depth |
| v9 | Attack practice | Test own app against OWASP Top 10, fix findings | Threat modelling |
| v10 | Observability + load | Structured logs, Prometheus/Grafana, k6 load tests, tuning | Measure before optimizing |
| v11 | Polish | Tests, CI, architecture diagrams, ADRs, changelog write-up | Interview storytelling |

## Review at the end of every version

1. **Demo:** show it working end to end.
2. **Code review:** correctness, security, structure.
3. **Explain it back:** 3-5 "why" questions, interview style.
4. **ADR:** a short decision record in `docs/adr/` (what was chosen, what was rejected, why).
5. **Changelog:** one entry saying what improved and why.
6. **Tag:** `git tag vN`.

## Open decisions

- Whether the audit log and `tenant_id` move earlier (into v3), since they are cheaper to build in than to retrofit.
- The domain and public dataset used for sample data (to be chosen).
