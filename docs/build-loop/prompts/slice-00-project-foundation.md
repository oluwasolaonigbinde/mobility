9. Full self-contained Codex implementation prompt for Slice 0
You are implementing Slice 0 of a greenfield Mobility AdTech & Audience Attribution backend.

You are operating locally in the repo. There is no existing backend app code yet. Local git is initialized. Build-loop ledger files exist under docs/build-loop/. The local constraints file is named agent.md, even if other instructions mention AGENTS.md. Treat agent.md as the current local coding-guidelines source.

You must implement only the approved Slice 0 foundation. Do not implement users, auth, roles, advertiser organizations, drivers, vehicles, campaigns, creatives, zones, campaign assignments, GPS tracking, analytics, impression estimation, payouts, reports, heatmaps, seed/demo data, frontend code, cloud deployment, retargeting, AI/computer vision, or payment settlement.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, the system ingests GPS movement data, and analytics later support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 0 goal:
Create a clean backend foundation that boots, documents itself, connects to local infrastructure, supports future Alembic migrations, and has basic tests/checks. Slice 0 should give future slices a stable API, config, DB, migration, Docker, and test foundation.

FIXED STACK — DO NOT CHANGE

- Python 3.12
- FastAPI
- Pydantic v2
- pydantic-settings
- SQLAlchemy 2.x async
- asyncpg
- Alembic
- PostgreSQL + PostGIS
- Redis in Docker Compose
- pytest
- httpx or FastAPI TestClient for tests
- ruff
- Docker Compose

ARCHITECTURE DIRECTION

Use a modular monolith. Keep the foundation simple and ready for future domain modules.

Expected future-friendly structure:

- app/main.py
- app/api/v1/router.py
- app/api/v1/health.py
- app/core/config.py
- app/core/errors.py
- app/core/middleware.py or equivalent
- app/core/logging.py or equivalent if useful
- app/db/session.py
- app/db/base.py
- alembic/
- tests/

You may adjust exact filenames if there is a better local convention, but keep the structure obvious, minimal, and future-ready.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the repo root.
2. Read agent.md and follow its constraints.
3. Inspect docs/build-loop/ if present.
4. Confirm no backend package/app has already been scaffolded.
5. Confirm whether pyproject.toml, requirements files, Docker files, or Alembic files already exist.
6. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement the Slice 0 foundation only:

1. Python project configuration.
2. FastAPI app.
3. Versioned API router under /api/v1.
4. Health endpoints.
5. Settings/configuration from environment variables.
6. Standard expected-error envelope.
7. Request ID middleware or equivalent request ID propagation.
8. CORS configuration from environment allowlist.
9. SQLAlchemy async DB session infrastructure.
10. Alembic setup.
11. Initial migration enabling PostgreSQL extensions:
    - pgcrypto
    - postgis
12. Dockerfile for the API.
13. docker-compose.yml with:
    - API service
    - PostgreSQL/PostGIS service
    - Redis service
14. .env.example.
15. README with local setup commands.
16. pytest tests for foundation behavior.
17. ruff configuration.

REQUIRED API ENDPOINTS

Implement:

1. GET /health
   - Public liveness endpoint.
   - Should not require DB.
   - Returns JSON with at least service name and status.

2. GET /api/v1/health
   - Public versioned liveness endpoint.
   - Should not require DB.
   - Returns JSON with at least service name, API version, and status.

3. GET /api/v1/health/ready
   - Readiness endpoint.
   - Should check DB connectivity when DATABASE_URL is configured.
   - If DB is not reachable, return an appropriate non-2xx readiness failure.
   - Keep behavior deterministic and documented.
   - If local test config intentionally disables DB access, tests may override settings or use dependency-safe behavior.

CONFIGURATION REQUIREMENTS

Use pydantic-settings.

Required environment-driven settings should include at minimum:

- APP_NAME, default mobility-adtech-api
- ENVIRONMENT, default local
- API_V1_PREFIX, default /api/v1
- DATABASE_URL
- REDIS_URL
- BACKEND_CORS_ORIGINS
- LOG_LEVEL
- REQUEST_ID_HEADER, default X-Request-ID

Rules:

- Do not hardcode secrets.
- Do not commit real secrets.
- Do not use wildcard CORS for non-local environments.
- Keep .env.example safe and explicit.
- Make local defaults developer-friendly but not production-dangerous.

ERROR FORMAT REQUIREMENTS

Create a standard JSON error envelope for expected app errors:

{
  "error": {
    "code": "SOME_CODE",
    "message": "Human-readable message",
    "details": {},
    "request_id": "..."
  }
}

At minimum, ensure custom/expected application errors can use this envelope. Do not over-engineer a full exception hierarchy.

REQUEST ID REQUIREMENTS

Add middleware that:

- Reads request ID from the configured request ID header if supplied.
- Generates one if missing.
- Includes the request ID in the response header.
- Makes the request ID available to error responses where practical.

DATABASE/MIGRATION REQUIREMENTS

1. Configure SQLAlchemy 2.x async engine/session infrastructure.
2. Configure Alembic to use project settings.
3. Initial migration must enable:
   - pgcrypto
   - postgis
4. No business tables in Slice 0.
5. No user/auth/campaign/driver/tracking models in Slice 0.
6. app/db/base.py may define a Declarative Base for future models, but should not include business models.

DOCKER REQUIREMENTS

docker-compose.yml must include:

1. API service
2. PostgreSQL/PostGIS service
3. Redis service

PostgreSQL service must use a PostGIS-capable image.

Docker Compose should support:

docker compose up --build

README REQUIREMENTS

Add or update README with:

- Project name.
- Stack summary.
- Local prerequisites.
- Environment setup using .env.example.
- Run API locally.
- Run tests.
- Run lint.
- Run migrations.
- Docker Compose startup.
- Current Slice 0 scope and explicit note that business features begin in later slices.

TEST REQUIREMENTS

Add tests for:

1. GET /health returns success and expected JSON shape.
2. GET /api/v1/health returns success and expected JSON shape.
3. OpenAPI schema generation works.
4. Settings import/initialization works.
5. Request ID header is returned or generated.
6. Optional: expected application error envelope works if a small test route or unit-level test is appropriate without adding business scope.

Do not make tests require a live database unless specifically isolated. If readiness endpoint DB behavior is tested, make it deterministic using dependency overrides/mocks or a clearly documented integration path.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
ruff check .
alembic upgrade head
docker compose up --build

If a command cannot be run locally due to missing external runtime such as Docker availability, report that honestly with the exact error/evidence.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Likely create/change:

- pyproject.toml
- README.md
- .env.example
- .gitignore if absent or incomplete
- Dockerfile
- docker-compose.yml
- alembic.ini
- alembic/env.py
- alembic/versions/<initial_revision>_enable_extensions.py
- app/__init__.py
- app/main.py
- app/api/__init__.py
- app/api/v1/__init__.py
- app/api/v1/router.py
- app/api/v1/health.py
- app/core/__init__.py
- app/core/config.py
- app/core/errors.py
- app/core/middleware.py
- app/db/__init__.py
- app/db/base.py
- app/db/session.py
- tests/conftest.py
- tests/test_health.py
- tests/test_openapi.py
- tests/test_config.py
- tests/test_request_id.py

Do not rename agent.md unless there is a clear reason and the orchestrator approves it. For this slice, simply read and follow it.

EXPLICIT NON-GOALS

Do not implement:

- Auth
- JWT
- Users
- Roles
- Advertiser organizations
- Driver profiles
- Vehicle profiles
- Campaigns
- Creatives
- Geofences/zones
- Assignments/activation
- GPS pings
- Trip sessions
- Route analytics
- Fraud flags
- Impression estimation
- Payout calculation
- Earnings ledger
- Advertiser dashboard/reporting APIs
- Heatmap APIs
- Seed/demo data
- Celery/background jobs
- Frontend/mobile app
- GitHub remote/PR setup
- Cloud deployment
- Retargeting
- Audience pooling
- AI/computer vision
- Real payment settlement

ACCEPTANCE CRITERIA

Slice 0 is acceptable only if:

1. FastAPI app boots.
2. /health works.
3. /api/v1/health works.
4. /api/v1/health/ready exists and has documented DB-readiness behavior.
5. OpenAPI docs generate.
6. Settings load from environment.
7. Request ID behavior works.
8. CORS is config-driven.
9. SQLAlchemy async session foundation exists.
10. Alembic is configured.
11. Initial Alembic migration enables pgcrypto and postgis.
12. Docker Compose defines API, PostGIS PostgreSQL, and Redis services.
13. README explains local usage.
14. python -m pytest passes or any failure is clearly reported with evidence.
15. ruff check . passes or any failure is clearly reported with evidence.
16. alembic upgrade head passes or any failure is clearly reported with evidence.
17. No business/domain code is added.

STOP CONDITIONS

Stop immediately and produce a reconciliation report if:

1. Existing backend code is discovered that conflicts with this prompt.
2. Existing project configuration implies a materially different stack.
3. agent.md contains instructions that conflict with this prompt.
4. Alembic/PostGIS cannot be configured without a product/architecture decision.
5. You are tempted to add Slice 1 or later scope.

Otherwise, stop after Slice 0 implementation. Do not continue to Slice 1.

REQUIRED CODEX PLAN FORMAT BEFORE CODING

Before coding, output:

CODEX PLAN

Slice:
Scope understood:
Local investigation findings:
Files to create/change:
Database migrations:
API endpoints:
Tests to add/update:
Security/validation checks:
Explicitly out of scope:
Assumptions:
Risks or blockers:

REQUIRED CODEX BUILD REPORT FORMAT AFTER CODING

After coding, output:

CODEX BUILD REPORT

Slice:
Status: PASS_CANDIDATE | PARTIAL | BLOCKED

Summary:
Local investigation performed:
Files changed:
Database migrations:
API endpoints implemented:
Security/validation implemented:
Tests added/updated:
Commands run:
Command results:
Known issues:
Out-of-scope compliance:
Acceptance criteria checklist:
Manual verification steps:
Questions for Pro reviewer:

