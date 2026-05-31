# Mobility AdTech API

Backend foundation for the Mobility AdTech & Audience Attribution Platform.

## Stack

- Python 3.12
- FastAPI
- Pydantic v2 and pydantic-settings
- SQLAlchemy 2.x async with asyncpg
- Alembic
- PostgreSQL with PostGIS
- Redis
- pytest and ruff
- Docker Compose

## Current Scope

This repo currently contains Slice 1: project foundation, request IDs, expected error
envelope, SQLAlchemy/Alembic foundation, JWT login, current-user context, RBAC, admin
user management, advertiser organizations, organization memberships, audit events,
Docker Compose, tests, and linting.

Business features such as campaigns, drivers, vehicles, GPS tracking, analytics,
payouts, reports, heatmaps, and seed data begin in later approved slices.

## Local Prerequisites

- Python 3.12
- Docker and Docker Compose

## Environment

Create a local environment file from the example:

```powershell
Copy-Item .env.example .env
```

The example is safe for local Docker Compose development. Do not commit real secrets.

## Install

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run The API

```powershell
uvicorn app.main:app --reload
```

Health endpoints:

- `GET /health`
- `GET /api/v1/health`
- `GET /api/v1/health/ready`

Readiness checks the database only when `DATABASE_URL` is configured. Without a configured database URL, it returns `database: not_configured`.

Slice 1 auth and organization endpoints:

- `POST /api/v1/auth/login`
- `GET /api/v1/me`
- `POST /api/v1/admin/users`
- `GET /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{user_id}`
- `POST /api/v1/admin/advertiser-organizations`
- `GET /api/v1/advertiser/organization`

Protected endpoints use bearer auth:

```http
Authorization: Bearer <access_token>
```

Admin-created users require passwords at least `PASSWORD_MIN_LENGTH` characters long.
Emails are normalized to lowercase before storage and login lookup. JWT signing uses
`JWT_SECRET_KEY`, `JWT_ALGORITHM`, and `ACCESS_TOKEN_EXPIRE_MINUTES`.

## Tests

```powershell
python -m pytest
```

## Lint

```powershell
ruff check .
```

## Migrations

Run PostGIS locally before applying migrations:

```powershell
docker compose up -d db
$env:DATABASE_URL = "postgresql+asyncpg://mobility:mobility@localhost:5433/mobility"
alembic upgrade head
```

The initial migration enables `pgcrypto` and `postgis`. Slice 1 adds only the approved
identity and tenancy tables: `users`, `advertiser_organizations`,
`organization_memberships`, and `audit_events`.

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose starts the API, PostgreSQL/PostGIS, and Redis.
