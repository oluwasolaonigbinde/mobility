PASS

Safe to commit: Yes. Commit Slice 11 before starting Slice 12.

Codex questions resolved:

Selecting the latest stored current-formula impression estimate per trip is the preferred anti-double-counting rule for Slice 11 heatmap allocation. It keeps the heatmap read-only, avoids double-counting repeated estimates, and aligns with the existing current-formula reporting approach.

Omitting optional final_payout is acceptable for Slice 11. Multi-currency payout heatmaps and advertiser cost-privacy handling should remain deferred unless a later explicit product requirement makes them necessary.

Basis: Slice 11 added the approved read-only advertiser/admin heatmap endpoints, introduced no migration or new tables, preserved Alembic head 0010_payouts_and_earnings, uses bounded PostGIS bbox/grid aggregation, supports the required metrics, enforces advertiser/admin scoping and privacy boundaries, passed host/PostGIS/Docker pytest, ruff, Alembic, and Python 3.12 Docker verification, and avoided deferred scope such as heatmap caches, map tiles, raw GPS export, new calculations, billing, settlement, seed data, and frontend work. 

Pasted text

Recommended commit message:

feat: add heatmap geospatial aggregation APIs

Full Slice 12 implementation prompt:

You are implementing Slice 12 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, Slice 5 campaign assignment/activation, Slice 6 trip tracking/GPS ping ingestion, Slice 7 route analytics/fraud flags, Slice 8 impression estimation, Slice 9 payout calculations/driver earnings ledger, Slice 10 advertiser dashboard/reporting APIs, and Slice 11 heatmap/geospatial aggregation APIs have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 11 has been committed or that the working tree contains only the accepted Slice 11 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, heatmap-ready geospatial data, and demo-ready frontend integration.

Slice 12 goal:
Implement seed/demo data and API documentation hardening. This slice should make the backend immediately usable by frontend teams and demos: a developer should be able to start the stack, run an idempotent seed command, log in as admin/advertiser/driver demo users, and see realistic campaign, assignment, trip, analytics, impression, payout, reporting, and heatmap data. This slice should improve OpenAPI examples and README usage without adding product scope, new tables, background jobs, or production deployment.

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
- JWT bearer auth
- Existing password hashing/JWT/RBAC from Slice 1
- Existing driver/vehicle foundation from Slice 2
- Existing campaign/creative foundation from Slice 3
- Existing campaign zone/geofence foundation from Slice 4
- Existing campaign assignment/activation foundation from Slice 5
- Existing trip/session/location ping foundation from Slice 6
- Existing route analytics/fraud flag foundation from Slice 7
- Existing impression estimation foundation from Slice 8
- Existing payout/earnings foundation from Slice 9
- Existing advertiser reporting foundation from Slice 10
- Existing heatmap foundation from Slice 11
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 11 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing factories/test fixtures for users, organizations, drivers, vehicles, campaigns, zones, assignments, trips, pings, analytics, impressions, payouts, reports, and heatmaps.
6. Inspect existing README and OpenAPI doc conventions.
7. Confirm the existing API prefix is `/api/v1`.
8. Confirm the existing standard error envelope and reuse it.
9. Confirm the current Alembic head is `0010_payouts_and_earnings`.
10. Confirm no seed/demo table or demo-only migration already exists.
11. Determine existing password hashing and user creation service patterns and reuse them.
12. Determine existing Decimal serialization conventions and reuse them.
13. Determine existing PostGIS geometry patterns and reuse them for seeded zones/pings.
14. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 12:

1. Idempotent local/dev seed command or script.
2. Demo data creation using existing tables only.
3. Demo users:
   - admin
   - advertiser owner/manager/viewer as useful
   - one or more drivers
4. Demo advertiser organization.
5. Demo driver profiles and vehicles.
6. Demo campaign with creative metadata.
7. Demo campaign zones/geofences.
8. Demo campaign assignment and activation records.
9. Demo trip sessions and location pings.
10. Demo route analytics and fraud flags, preferably by invoking/reusing existing services where practical.
11. Demo traffic density profile and impression estimates, preferably by invoking/reusing existing services where practical.
12. Demo campaign payout rule, payout calculation, and driver earnings ledger entry, preferably by invoking/reusing existing services where practical.
13. Ensure advertiser reporting and heatmap endpoints have meaningful seeded data to return.
14. OpenAPI examples/tags/docstrings improvement for existing MVP endpoints where low-risk and useful.
15. README updates for:
    - seeding
    - demo credentials
    - demo workflow
    - frontend integration endpoints
    - known local-only safety notes
16. Tests for seed idempotency, demo login path, dashboard/reporting/heatmap smoke path, no new migration/table guardrails, and production-safety checks.
17. Build-loop report and slice log update.

IMPORTANT DATA MODEL DECISION

Do not create new database tables in Slice 12.

Do not create a new Alembic migration in Slice 12.

Use existing tables and services only.

If you discover a local technical reason that a new table or migration is required, stop and report the reason instead of adding it.

DO NOT IMPLEMENT

- New database tables
- New Alembic migration
- Production seed automation
- Background jobs/Celery workers
- Scheduled data generation
- Synthetic data API endpoints
- Public demo reset endpoint
- CSV/PDF export
- Frontend/mobile implementation
- Mapbox integration
- Map tiles or vector tiles
- Raw GPS export
- Route polyline export
- New analytics algorithms
- New impression formulas
- New payout formulas
- New heatmap metrics
- Billing/invoicing
- Advertiser charging
- Settlement/payment APIs
- Withdrawal/cash-out APIs
- Tax handling
- Payment provider integration
- Manual fraud review workflow
- Notifications
- External traffic provider integrations
- External map matching
- Geocoding/reverse-geocoding
- Audience identity, retargeting, or device pooling
- Creative binary upload/storage pipeline
- Public self-registration
- OAuth/social login
- Refresh-token flow
- GitHub remote/PR setup
- Production cloud deployment
- AI/computer vision

SEEDING PRINCIPLES

1. Seed data is for local/dev/demo use only.
2. Seed command must be idempotent.
3. Re-running the seed command must not create duplicate users, organizations, campaigns, vehicles, assignments, trips, pings, analytics, estimates, payouts, or ledger entries.
4. Seed command must be safe by default:
   - It must refuse to run in production-like environments.
   - It must check `ENVIRONMENT`.
   - It must require an explicit flag or setting if `ENVIRONMENT` is not `local`, `development`, `dev`, or `test`.
5. Do not commit real secrets.
6. Demo credentials must be clearly marked local-only.
7. Demo passwords must satisfy the existing password policy.
8. Demo data should be realistic enough for frontend integration:
   - campaign summary has nonzero campaign/trip/impression/cost metrics
   - daily metrics returns multiple days
   - campaign trips returns trip summaries
   - heatmap returns non-empty FeatureCollection for documented bbox
   - driver earnings summary returns a nonzero pending balance
9. Prefer using existing services to create computed records, especially:
   - route analytics recompute
   - impression estimation
   - payout calculation
10. Direct inserts are acceptable only where service usage is impractical, but must respect model constraints and formulas.
11. Seed command should run after `alembic upgrade head`.
12. Seed command should not automatically run during app startup.
13. Seed command should not depend on external network access.

EXPECTED SEED DATA

Create a coherent demo dataset, using stable identifiers or stable natural keys where helpful.

Required demo identities:

1. Admin user:
   - email: `admin@demo.mobility.local`
   - role: `admin`
   - status: `active`
   - password: safe local demo password, for example `DemoAdmin12345!`

2. Advertiser owner:
   - email: `advertiser@demo.mobility.local`
   - role: `advertiser`
   - status: `active`
   - organization membership role: `owner`
   - password: safe local demo password, for example `DemoAdvertiser12345!`

3. Optional advertiser viewer:
   - email: `viewer@demo.mobility.local`
   - role: `advertiser`
   - status: `active`
   - organization membership role: `viewer`
   - password: safe local demo password

4. Driver user:
   - email: `driver@demo.mobility.local`
   - role: `driver`
   - status: `active`
   - password: safe local demo password, for example `DemoDriver12345!`

Optional:
- Add a second driver and vehicle if useful for dashboard/heatmap variety, but keep seed scope modest.

Required demo advertiser organization:

- name: `Demo Mobility Advertiser`
- currency: `NGN`
- status: `active`
- country code: `NG`

Required demo driver profile:

- onboarding status: `active`
- service city: `Lagos`
- country code: `NG`

Required demo vehicle:

- plate number: `DEMO-001`
- plate country code: `NG`
- vehicle type: `car`
- make/model/year/color realistic
- status: `active`

Required demo campaign:

- name: `Demo Lagos Mobility Campaign`
- status: `active`
- start/end dates chosen so the campaign is currently active when seed runs.
- currency: `NGN`
- budget fields nonzero.
- metadata includes a clear demo marker, such as:
  - `"demo": true`
  - `"seed_version": "slice_12_v1"`

Required demo creative:

- name: `Demo Exterior Wrap`
- creative type: `image`
- placement: `vehicle_exterior`
- asset_url: safe placeholder HTTPS URL
- mime_type: `image/png`
- status: `ready`
- metadata demo marker

Required demo zones:

- at least one target zone
- at least one bonus zone
- optional exclusion zone
- Use valid Lagos-like GeoJSON Polygon/MultiPolygon coordinates.
- Ensure the seeded trip pings intersect target/bonus zones so analytics/reporting/heatmap data is meaningful.
- Use existing zone validation/storage service if practical.

Required demo assignment:

- campaign: demo campaign
- driver profile: demo driver
- vehicle: demo vehicle
- status lifecycle should support trip data.
- The final assignment state should be `active` or appropriate for seeded ended trips without breaking data model constraints.
- Use existing assignment services if practical.

Required demo trip/pings:

- At least one ended trip with enough valid pings to compute analytics.
- Prefer two ended trips across different UTC dates if practical, so daily metrics are useful.
- Pings should:
  - be within the demo campaign date window
  - be near/inside the demo zones
  - have realistic timestamps
  - have valid accuracy/speed/heading values
  - create a non-empty heatmap within a documented bbox
- Avoid excessive ping volume. Around 10–30 pings total is enough.

Required demo analytics/fraud:

- Route analytics should be computed for seeded ended trips using existing service if practical.
- It is acceptable if one low/medium fraud flag is generated naturally, but do not force severe fraud unless useful for testing.
- Dashboard/reporting should still look healthy enough for demo.

Required demo impression estimation:

- Create or reuse a traffic density profile.
- Estimate impressions for seeded analyzed trips using existing service if practical.
- Ensure advertiser campaign impression summary returns nonzero estimated impressions.

Required demo payout/earnings:

- Create an active campaign payout rule.
- Calculate payout for seeded trips using existing service if practical.
- Ensure driver earnings summary returns nonzero pending earnings.
- Ensure advertiser cost summary and Slice 10 reporting return nonzero cost values.

RECOMMENDED SEED COMMAND

Implement a simple, documented seed entry point.

Acceptable options:

Preferred:

```bash
python -m app.seeds.demo

Acceptable:

Bash
python -m app.scripts.seed_demo

or a console script in pyproject.toml, for example:

Bash
seed-demo

If adding a console script, also keep the module form available.

The command should:

Load existing settings.

Refuse production-like environments.

Open an async DB session.

Upsert or find existing demo records by stable natural keys.

Use existing password hashing for demo users.

Use existing service methods where practical.

Print a concise summary:

users created/found

organization created/found

campaign id

trip ids

analytics count

impression estimate count

payout calculation count

ledger entry count

demo login credentials

sample endpoints/bbox

Exit with nonzero status on unrecoverable errors.

ENVIRONMENT SAFETY REQUIREMENTS

Add settings only as needed.

Possible setting:

ALLOW_DEMO_SEED, default false

Required behavior:

If ENVIRONMENT is production, prod, or similar, refuse to seed unless an explicit local override is present.

Prefer refusing production unconditionally even if an override is set.

Do not run seed automatically in Docker Compose.

Do not include seed command in app startup.

.env.example may show ALLOW_DEMO_SEED=true only if clearly marked local/demo.

README must clearly say demo credentials are local-only and must not be used in production.

OPENAPI/DOCUMENTATION HARDENING

Improve API docs without broad refactoring.

Allowed documentation improvements:

Ensure major routers have tags:

Health

Auth

Admin Users

Advertiser Organizations

Drivers

Vehicles

Campaigns

Campaign Zones

Campaign Assignments

Trips

Analytics

Impressions

Payouts

Advertiser Reports

Heatmaps

Add request/response examples where straightforward and low-risk.

Add operation summaries/descriptions for key frontend-facing endpoints:

login

/me

advertiser campaigns

campaign zones

driver assignments

driver trips/pings

analytics summary

impression summary

driver earnings summary/ledger

advertiser dashboard/reporting

heatmap

Do not rewrite all endpoint implementations merely for documentation.

Do not change existing stable response shapes unless fixing a documented bug.

Do not add new product endpoints only for documentation.

README REQUIREMENTS

Update README with:

Slice 12 scope.

Demo seed prerequisites:

database running

migrations applied

environment safety

Demo seed command.

Demo credentials.

Suggested smoke workflow:

run app

log in as advertiser

call /api/v1/me

call dashboard summary

call campaign summary

call campaign daily metrics

call campaign trips

call campaign report

call campaign heatmap with documented bbox

log in as driver

call driver earnings summary

Sample PostGIS URL commands for Windows PowerShell, matching existing README style.

Clear out-of-scope note:

no frontend

no production deployment

no real payments

no seed automation in production

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 11 conventions. Likely create/change:

app/seeds/__init__.py

app/seeds/demo.py

or app/scripts/seed_demo.py

app/core/config.py

.env.example

README.md

Existing routers/schemas only for OpenAPI examples/tags/summaries

tests/test_seed_demo.py

tests/test_openapi_docs.py

tests/test_seed_smoke.py

tests/test_migration_slice12.py or update migration guard tests to assert no new tables

Possibly fixture updates in tests/conftest.py

docs/build-loop/reports/slice-12-seed-demo-docs.md

docs/build-loop/slice-log.md

Do not create or modify Alembic migration files unless stopped/reconciled and explicitly approved.

TEST REQUIREMENTS

Add/extend tests for:

Seed command safety:

Seed refuses to run in production-like environment.

Seed can run in local/development/test environment.

Seed does not run automatically on app startup.

Seed command exits successfully in allowed environment.

Demo passwords satisfy existing password minimum length.

Demo users are active and can authenticate.

Seed idempotency:

Running the seed command once creates or finds the demo dataset.

Running the seed command twice does not duplicate users.

Running the seed command twice does not duplicate advertiser organization.

Running the seed command twice does not duplicate driver profile.

Running the seed command twice does not duplicate vehicle.

Running the seed command twice does not duplicate campaign.

Running the seed command twice does not duplicate creative.

Running the seed command twice does not duplicate campaign zones beyond expected count.

Running the seed command twice does not duplicate assignments beyond expected count.

Running the seed command twice does not duplicate trip sessions beyond expected count.

Running the seed command twice does not duplicate ping batches/pings beyond expected count.

Running the seed command twice does not duplicate analytics rows.

Running the seed command twice does not duplicate impression estimates.

Running the seed command twice does not duplicate payout calculations.

Running the seed command twice does not duplicate ledger entries.

Seed data usefulness:

Demo advertiser login succeeds.

Demo driver login succeeds.

Demo admin login succeeds.

Demo advertiser /api/v1/me returns organization context.

Demo advertiser dashboard summary returns at least one campaign.

Demo campaign summary returns nonzero or meaningful metrics.

Demo daily metrics returns at least one item.

Demo campaign trips endpoint returns at least one trip summary.

Demo campaign report returns stable bundled sections.

Demo campaign impression summary returns stable shape and preferably nonzero estimates.

Demo campaign cost summary returns stable shape and preferably nonzero costs.

Demo campaign heatmap returns valid FeatureCollection, preferably non-empty for documented bbox.

Demo driver earnings summary returns stable shape and preferably nonzero pending earnings.

Demo driver ledger returns at least one entry if payout calculation produced positive payout.

Documentation/OpenAPI:

OpenAPI schema generates successfully.

New/updated tags appear in OpenAPI.

Key endpoints have operation summaries or descriptions.

Seed command and demo credentials are documented in README.

README includes the demo bbox and smoke workflow.

Migration/scope guardrails:

No new Alembic migration is added.

No new database tables are added.

Existing Alembic head remains 0010_payouts_and_earnings.

Existing Slice 0-Slice 11 tests continue to pass.

No frontend, production deployment, payment settlement, billing, background job, external map/traffic provider, retargeting, audience, AI, or new product feature scope is added.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

Use existing services where practical.

PostGIS is required for the full seed smoke path because zones, pings, analytics, and heatmaps use PostGIS.

If the default host test suite skips PostGIS-backed seed smoke tests without a PostGIS URL, ensure the Docker/PostGIS test run executes them.

Keep tests deterministic.

Do not require external network access.

Do not run the seed command against a real production database.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Postgres/PostGIS migration, full-test, and seed verification are required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; $env:ALLOW_DEMO_SEED='true'; python -m app.seeds.demo

If the seed command path differs, report the actual path and update README accordingly.

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

After this slice, frontend developers should be able to:

Start the backend and database.

Run migrations.

Run the demo seed command.

Log in as the demo advertiser.

Retrieve current user/org context.

Render dashboard summary.

Render campaign summary, daily metrics, trip summaries, report, and heatmap.

Log in as the demo driver.

Render driver earnings summary and ledger.

Key frontend endpoints to validate with seed data:

http
POST /api/v1/auth/login
GET  /api/v1/me

GET /api/v1/advertiser/dashboard/summary
GET /api/v1/advertiser/campaigns
GET /api/v1/advertiser/campaigns/{campaign_id}
GET /api/v1/advertiser/campaigns/{campaign_id}/summary
GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics
GET /api/v1/advertiser/campaigns/{campaign_id}/trips
GET /api/v1/advertiser/campaigns/{campaign_id}/report
GET /api/v1/advertiser/campaigns/{campaign_id}/impressions/summary
GET /api/v1/advertiser/campaigns/{campaign_id}/cost-summary
GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap

GET /api/v1/driver/earnings/summary
GET /api/v1/driver/earnings/ledger

All protected endpoints use bearer token auth:

http
Authorization: Bearer <token>

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 11 error envelope for expected errors.

Expected examples:

Missing database config

Demo seed disallowed in current environment

Duplicate/conflicting demo natural key that cannot be reconciled

Existing corrupted/incompatible demo data

Missing prerequisite migration

Invalid seed geometry or generated route data

Do not return raw stack traces through API endpoints. For CLI seed command failures, print concise actionable messages and exit nonzero.

ACCEPTANCE CRITERIA

Slice 12 is acceptable only if:

No new database tables are created.

No new Alembic migration is created.

Existing Alembic head remains 0010_payouts_and_earnings.

A documented local/demo seed command exists.

Seed command refuses production-like environments.

Seed command is idempotent.

Seed command creates or finds demo admin, advertiser, driver, organization, profile, vehicle, campaign, creative, zones, assignment, trip/pings, analytics, impression estimate, payout calculation, and ledger data.

Demo users can log in.

Demo advertiser dashboard/reporting/heatmap endpoints return meaningful stable data.

Demo driver earnings endpoints return meaningful stable data.

OpenAPI schema still generates.

Key frontend-facing endpoints have useful tags/summaries/examples where practical.

README documents seed usage, demo credentials, smoke workflow, and out-of-scope production caveats.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No frontend, deployment, real payments, billing, background jobs, seed automation, new analytics formulas, new heatmap/product features, retargeting, audience, or AI scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 11 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

Existing service APIs cannot create the necessary demo dataset without changing product behavior.

Seed data would require a new table or migration.

Seed data would require external network access.

Seed data would require real payment/settlement behavior.

Seed command cannot be made idempotent without a design decision.

Demo credentials or production-safety behavior requires a product decision.

You are tempted to add frontend, deployment, background jobs, billing, settlement, real payments, new analytics/impression/payout formulas, heatmap cache/tile infrastructure, retargeting, audience identity, or AI scope.

Otherwise, stop after Slice 12. Do not continue to Slice 13.

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
Seed command approach:
Seed idempotency approach:
Demo dataset approach:
OpenAPI/docs hardening approach:
Frontend smoke workflow:
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
Seed command implemented:
Seed idempotency implemented:
Demo dataset implemented:
OpenAPI/docs hardening implemented:
Frontend smoke workflow documented:
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
Security/validation implemented:
Seed command implemented:
Seed idempotency implemented:
Demo dataset implemented:
OpenAPI/docs hardening implemented:
Frontend smoke workflow documented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED