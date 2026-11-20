# ReportForge

A multi-tenant data platform, built as a learning project. An organization registers, its first user becomes the admin, and (in later versions) the admin defines what the organization tracks, imports data, creates roles and users, and controls what each role can see. See [ROADMAP.md](ROADMAP.md) for the plan and [CHANGELOG.md](CHANGELOG.md) for what each version added.

**Status:** v2 Access control (roles, users, permissions, audit log) built on the v1 Foundation (register, log in, protected workspace).

**Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, React, Vite, TypeScript, Docker.

## Run with Docker (everything in containers)

```bash
cp .env.example .env     # then fill in the three values (see comments in the file)
docker compose up --build
```

Open http://localhost:8080. Stop with `Ctrl+C`; `docker compose down -v` also deletes the database volume.

## Run for development (reloads on every change)

Needs PostgreSQL running locally with a `reportforge` database and role.

```bash
# Terminal 1: backend
cd backend
cp .env.example .env     # fill in DATABASE_URL and SECRET_KEY
source .venv/bin/activate   # first time: python -m venv .venv && pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. API docs: http://localhost:8000/docs.

## Tests

Tests run against a separate `reportforge_test` database (created once by an admin) and never touch the development database.

```bash
cd backend && source .venv/bin/activate && pytest -q
```

## Ports

| Port | What | Mode |
|---|---|---|
| 5173 | Vite dev server (proxies `/api` to 8000) | development |
| 8000 | FastAPI | both |
| 5432 | Local PostgreSQL | development |
| 8080 | nginx serving the frontend and proxying `/api` | Docker |
| 5433 | Docker PostgreSQL, published to your machine only | Docker |

Do not run Docker's backend and a local `uvicorn` at the same time; both use port 8000.

## Permissions in short

Every organization gets an **Admin** role (all permissions, cannot be edited). Admins create roles by combining permissions from a fixed catalogue (`backend/app/permissions.py`), create users and assign roles. A route is protected with `Depends(require_permission("users.manage"))`; to add a permission, add it to the catalogue and write a migration (see ADR 0005). Every change is recorded in the audit log.

## Documentation

Architecture decisions are recorded in [docs/adr](docs/adr).
