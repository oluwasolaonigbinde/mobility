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

This repo currently contains Slice 0 only: project foundation, app boot, settings, health endpoints, request IDs, expected error envelope, SQLAlchemy/Alembic foundation, Docker Compose, tests, and linting.

Business features such as auth, users, campaigns, drivers, vehicles, GPS tracking, analytics, payouts, reports, heatmaps, and seed data begin in later approved slices.

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

The initial migration enables `pgcrypto` and `postgis`. It does not create business tables.

## Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose starts the API, PostgreSQL/PostGIS, and Redis.
