# ADR 0001: PostgreSQL as the primary database

**Status:** Accepted (v1, 2026-11)

## Context
ReportForge is a multi-tenant platform: organizations, users, roles, datasets and imported business data. We need strict correctness for identity and permissions, bulk CSV import, and later fast aggregate reports. The developer is learning database design, security and tuning.

## Decision
Use **PostgreSQL 17** as the system of record. Redis is added later as cache and job queue (v3-v4). Postgres runs natively on the developer's Mac for development (port 5432) and as a container in Docker Compose (host port 5433).

## Alternatives considered
| Option | Why not (for now) |
|---|---|
| MySQL / MariaDB | Works, but weaker tooling for the security and tuning topics being learned |
| SQL Server | Common in German Mittelstand; adds licensing and Docker friction. Revisit if job targets demand it |
| SQLite | Single-user, too limited for multi-user and multi-service work |
| MongoDB | The core data (organizations, users, roles) is relational |
| ClickHouse / DuckDB | Columnar analytics stores, a different problem. Considered for v4 |

## Consequences
- Foreign keys, constraints and transactions enforce correctness in the database, not only in Python.
- Row-Level Security is available for tenant isolation later.
- **Staged plan:** one database until v4. A second, analytical database (ClickHouse is the leading candidate) is added only if measurements show Postgres is too slow for reports. Postgres remains the source of truth and the analytical store must be rebuildable from it.
