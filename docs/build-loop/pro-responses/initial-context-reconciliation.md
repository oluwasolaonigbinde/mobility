Verdict: SIGNED OFF

1. Context reconciliation

The orchestrator’s local setup matches the expected starting state.

The packet confirms that local git is initialized, build-loop ledger files exist under docs/build-loop/, an initial setup commit exists, and no backend stack, package manager, schema, API framework, source tree, or tests have been scaffolded yet. It also confirms that the only local constraints source is currently agent.md, even though the orchestration brief references AGENTS.md; this is not a blocker. Treat agent.md as the active local coding-guidelines file for now. 

Pasted text

No conflicts were found between the local context packet and the existing roadmap. The product scope in the packet remains aligned with the brief: campaigns on shared ride vehicles, GPS movement ingestion, route analytics, impression estimation, payouts, advertiser reporting, heatmap-ready geospatial data, and basic fraud/anomaly flags. 

Pasted text

The product brief also supports the selected stack direction: it explicitly names FastAPI, PostgreSQL, Redis, Docker, and Mapbox among suggested technologies, while the MVP scope includes driver tracking, GPS analytics, impression estimation, payouts, campaign management, advertiser dashboard, and heatmaps. 

Developer_Product_Brief_Mobilit…

No blocking questions.

2. Roadmap status

The existing roadmap remains valid.

Only one local adjustment is needed: Codex must inspect and follow agent.md instead of AGENTS.md unless it chooses to perform a safe normalization later. For Slice 0, no file rename is required. This keeps the first implementation slice focused and avoids unnecessary repo churn.

The approved architecture remains:

Python 3.12

FastAPI

Pydantic v2 / pydantic-settings

SQLAlchemy 2.x async

asyncpg

Alembic

PostgreSQL + PostGIS

Redis

Docker Compose

pytest

ruff

Modular monolith

REST JSON API under /api/v1

3. Backend stack decision

Approved backend stack:

Layer	Decision
Language	Python 3.12
API framework	FastAPI
Validation/config	Pydantic v2 + pydantic-settings
Database	PostgreSQL + PostGIS
ORM	SQLAlchemy 2.x async
DB driver	asyncpg
Migrations	Alembic
Cache/job foundation	Redis
Local runtime	Docker Compose
Tests	pytest + httpx/FastAPI test client
Linting	ruff
API style	REST JSON under /api/v1
Architecture	Modular monolith

Rationale: this project is API-first, geospatial, analytics-heavy, and relational. PostgreSQL/PostGIS is the correct durable core for campaigns, users, vehicles, assignments, location pings, zones, route analytics, heatmaps, and reporting. FastAPI gives strong request validation, OpenAPI docs, async support, and clean frontend/mobile contracts without forcing premature microservices.

4. Architecture summary

The backend should be a modular monolith with clear domain modules, not microservices.

Expected runtime shape:

Admin dashboard / Advertiser dashboard / Driver app
        │
        ▼
FastAPI REST API
        │
        ├── API routers
        ├── auth/RBAC dependencies
        ├── domain services
        ├── analytics services
        ├── payout services
        └── repository/data-access layer
                │
                ├── PostgreSQL + PostGIS
                └── Redis

Expected code shape over time:

app/
  main.py
  api/
    v1/
      router.py
      health.py
      auth.py
      users.py
      organizations.py
      drivers.py
      vehicles.py
      campaigns.py
      creatives.py
      zones.py
      assignments.py
      tracking.py
      analytics.py
      payouts.py
      reports.py
      heatmaps.py
  core/
    config.py
    errors.py
    middleware.py
    security.py
    pagination.py
  db/
    base.py
    session.py
  models/
  schemas/
  services/
  repositories/
  workers/
alembic/
tests/
docs/build-loop/

Rules:

Keep routers thin.

Put business logic in services.

Put persistence logic in repositories where helpful.

Store geospatial data in PostGIS.

Expose GeoJSON at API boundaries where relevant.

Use UUID primary keys.

Use UTC timestamps.

Use standard error envelopes.

Add tests with each slice.

Do not introduce deferred scope without explicit approval.

5. Backend slice roadmap remains approved
Slice	Name	Purpose
Slice 0	Project foundation	FastAPI app, settings, health endpoints, DB session foundation, Alembic, Docker Compose, PostGIS/Redis, tests, linting.
Slice 1	Auth, users, roles, advertiser organizations	Identity, JWT login, RBAC, admin user management, advertiser tenancy.
Slice 2	Driver and vehicle foundations	Driver profiles, vehicle profiles, admin/driver access boundaries.
Slice 3	Campaign management and creative metadata	Campaign CRUD, statuses, budgets, date windows, creative metadata.
Slice 4	Campaign zones/geofences	GeoJSON campaign target/exclusion/bonus zones stored in PostGIS.
Slice 5	Campaign assignment and activation	Assign campaigns to drivers/vehicles; driver accept/activate/deactivate lifecycle.
Slice 6	GPS ingestion and trip/session tracking	Trip lifecycle, batched location pings, idempotency, timestamp/coordinate validation.
Slice 7	Route analytics v1 and fraud flags	Distance, duration, dwell, zone overlap, quality metrics, basic anomaly flags.
Slice 8	Impression estimation v1	Transparent formula-versioned impression estimates and campaign rollups.
Slice 9	Payout calculation v1 and earnings ledger	Formula-versioned payouts, immutable driver ledger, campaign cost summaries.
Slice 10	Advertiser dashboard and campaign reports	Summary cards, campaign reports, daily metrics, aggregate trip/performance views.
Slice 11	Heatmap/geospatial aggregation APIs	Bounded geospatial aggregation for frontend map heatmaps.
Slice 12	Seed/demo data and API docs hardening	Demo data, OpenAPI examples, frontend-ready smoke path.
Slice 13	MVP hardening and contract freeze	Security review, indexes, pagination, rate limits, contract snapshot, README hardening.

Approved dependency order remains linear:

0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13
6. Required tests/checks for Slice 1 later

These are not Slice 0 work, but they remain the required Slice 1 bar:

python -m pytest
ruff check .
alembic upgrade head

Slice 1 tests must cover:

Login succeeds with correct credentials.

Login fails with bad password.

Login fails for suspended/disabled users.

Password hashes are not stored as plaintext.

/api/v1/me requires auth.

/api/v1/me returns user role/status and advertiser organization context when applicable.

Admin-only endpoints reject advertiser and driver users.

Admin can create, list, and update users.

Admin can create advertiser organizations.

Advertiser user can retrieve only their own organization context.

Duplicate email is rejected.

Email normalization is enforced.

Migration applies cleanly.

Slice 1 explicit non-goals:

No driver profiles.

No vehicle profiles.

No campaigns.

No creatives.

No zones/geofences.

No assignments.

No GPS tracking.

No analytics.

No impressions.

No payouts.

No heatmaps.

No refresh-token complexity unless already trivial.

No OAuth/social login.

No public self-registration.

No frontend.

No cloud deployment.

Slice 1 acceptance criteria:

Authenticated requests work with JWT bearer auth.

RBAC is enforced.

Admin user management works.

Advertiser organization tenancy exists.

Passwords are securely hashed.

Suspended/disabled users cannot log in.

Tests and lint pass.

Alembic migration applies cleanly.

No post-Slice-1 domain scope is introduced.

7. Risks to track

Windows local path compatibility: the repo path is Windows-style, so commands and README instructions should avoid Unix-only assumptions where possible.

PostGIS availability: Docker Compose should use a PostGIS-capable PostgreSQL image from the start.

Async SQLAlchemy/Alembic setup complexity: keep Slice 0 minimal and verify alembic upgrade head.

Scope creep: do not add auth or business tables in Slice 0.

agent.md naming: treat it as the local guideline source; do not block on renaming.

Frontend contract stability: API prefix, error envelope, and OpenAPI docs should be established now.

8. Approved next action for Codex

Codex may begin Slice 0 only.

The slice is safe to implement locally. It is not yet safe to commit until Codex returns the implementation packet and it receives PASS or PASS WITH PACKET FORMAT CORRECTION.

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

REQUIRED PRO REVIEW PACKET FORMAT

The orchestrator must send the Pro reviewer a packet with:

PRO REVIEW PACKET

Slice:
Repo state summary:
Commit status:
Files changed:
Diff summary:
Database migrations:
API endpoints:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED
10. Ongoing review loop rules

For every future implementation packet from Codex/orchestrator, I will respond exactly in this top-level verdict format:

Verdict: PASS | PASS WITH PACKET FORMAT CORRECTION | FIX REQUIRED | BLOCKED

If PASS, I will state whether the slice is safe to commit, then provide the exact next-slice instruction and the full next implementation prompt.

If PASS WITH PACKET FORMAT CORRECTION, I will state whether the slice is safe to commit, give the exact packet-format correction for future packets, and provide the full next implementation prompt.

If FIX REQUIRED, I will give only the exact fixes needed for the current slice and a narrow Codex fix prompt. I will not introduce next-slice work.

If BLOCKED, I will state the blocker, classify it as product decision, design ambiguity, technical ambiguity, external config, missing repo evidence, or user decision, and give the smallest action needed to unblock.