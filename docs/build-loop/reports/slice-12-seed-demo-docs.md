CODEX BUILD REPORT

Slice:
Slice 12 - Seed/demo data and API docs hardening

Status: PASS_CANDIDATE

Summary:
Implemented an explicit local/demo seed command and light OpenAPI/README hardening.
The seed command creates a realistic, idempotent demo dataset using existing tables
only: demo users, advertiser organization, driver profile and vehicle, active
campaign and creative, Lagos zones, assignment, trips/pings, route analytics,
impression estimates, payout calculations, and driver ledger entries. It is not wired
to app startup or Docker Compose and refuses production-like environments.

Local investigation performed:
- Read `agent.md` and the Slice 12 prompt.
- Reviewed accepted Slice 0 through Slice 11 reports and Pro responses.
- Confirmed Slice 11 is committed and current branch is `slice-12-seed-demo-docs`.
- Confirmed `/api/v1` API prefix and standard `AppError` envelope.
- Confirmed Alembic head remains `0010_payouts_and_earnings`.
- Confirmed no seed/demo table or migration exists.
- Reviewed user/password, org, driver/vehicle, campaign/creative, zone, assignment,
  trip/ping, analytics, impression, payout, reporting, and heatmap patterns.
- Confirmed PostGIS geometry and test strategy.

Files changed:
- `.env.example`
- `README.md`
- `app/api/v1/admin.py`
- `app/api/v1/advertiser_organizations.py`
- `app/api/v1/advertiser_reports.py`
- `app/api/v1/auth.py`
- `app/api/v1/campaign_assignments.py`
- `app/api/v1/campaign_zones.py`
- `app/api/v1/campaigns.py`
- `app/api/v1/driver_profiles.py`
- `app/api/v1/health.py`
- `app/api/v1/heatmaps.py`
- `app/api/v1/impressions.py`
- `app/api/v1/me.py`
- `app/api/v1/payouts.py`
- `app/api/v1/trip_analytics.py`
- `app/api/v1/trips.py`
- `app/api/v1/vehicles.py`
- `app/core/config.py`
- `app/main.py`
- `app/schemas/auth.py`
- `app/seeds/__init__.py`
- `app/seeds/demo.py`
- `docs/build-loop/reports/slice-12-seed-demo-docs.md`
- `docs/build-loop/slice-log.md`
- `tests/test_seed_demo.py`
- `tests/test_seed_smoke.py`

Database migrations:
- None.
- No Alembic revision was added.
- No database tables were added.
- Current head remains `0010_payouts_and_earnings`.

API endpoints implemented:
- No new API endpoints were added.
- Existing endpoint metadata/tags/descriptions/examples were hardened for frontend
  docs and demo workflow clarity.

Security/validation implemented:
- Added `ALLOW_DEMO_SEED`, default `false`.
- Seed refuses production-like environments even with override.
- Seed requires explicit `ALLOW_DEMO_SEED=true` outside test.
- Seed requires `DATABASE_URL`.
- Seed requires PostgreSQL/PostGIS and Alembic head `0010_payouts_and_earnings`.
- Demo credentials are documented as local-only.
- Seed command is not called from app startup, Docker Compose, Alembic, or any API
  endpoint.

Seed command implemented:
- Preferred module entry point: `python -m app.seeds.demo`.
- Uses existing async DB/session setup.
- Prints concise created/found summary, demo credentials, and sample frontend
  endpoints.
- Exits nonzero with concise error codes/messages on expected failures.

Seed idempotency implemented:
- Stable natural keys and metadata markers are used for demo users, organization,
  memberships, driver profile, vehicle, campaign, creative, zones, assignment, trips,
  and ping batches.
- Reuses the existing analytics, impression, and payout services for computed rows.
- Reuses a stable active demo payout rule to avoid payout/ledger churn.
- Re-running the command preserves the same demo ids and counts.

Demo dataset implemented:
- Admin user: `admin@demo.mobility.local`.
- Advertiser owner: `advertiser@demo.mobility.local`.
- Advertiser viewer: `viewer@demo.mobility.local`.
- Driver user: `driver@demo.mobility.local`.
- Advertiser organization: `Demo Mobility Advertiser`.
- Active Lagos driver profile and `DEMO-001` car.
- Active `Demo Lagos Mobility Campaign`.
- Ready `Demo Exterior Wrap` creative.
- Target, bonus, and exclusion Lagos zones.
- Active campaign assignment and activation events.
- Two ended trips across different UTC days.
- Twelve PostGIS location pings in the documented bbox.
- Two route analytics rows.
- Two impression estimates.
- Two payout calculations.
- Two pending driver earnings ledger entries.

OpenAPI/docs hardening implemented:
- Router tags normalized to frontend-facing names such as `Auth`, `Campaigns`,
  `Advertiser Reports`, `Heatmaps`, and `Payouts`.
- Login request schema includes local demo examples.
- Heatmap docs include the demo bbox.
- Key report/heatmap/me/login endpoints include useful descriptions.
- README documents seed prerequisites, command, credentials, smoke workflow, demo bbox,
  and production caveats.

Frontend smoke workflow documented:
- README walks through advertiser login, `/me`, dashboard summary, campaign list,
  campaign summary, daily metrics, trips, report, impressions summary, cost summary,
  heatmap, driver login, earnings summary, and ledger.

Tests added/updated:
- `tests/test_seed_demo.py`
- `tests/test_seed_smoke.py`
- Covers production refusal, local confirmation, test-mode allowance, password policy,
  no startup seed route, no migration/table guardrails, README docs, OpenAPI tags and
  examples, PostGIS seed idempotency, and seeded frontend smoke endpoints.

Commands run:
- `python -m ruff check app/seeds/demo.py tests/test_seed_demo.py tests/test_seed_smoke.py app/core/config.py app/api/v1 app/schemas/auth.py app/main.py`
- `python -m pytest tests/test_seed_demo.py -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_seed_demo.py tests/test_seed_smoke.py -q`
- `python -m ruff check .`
- `python -m pytest -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; $env:ALLOW_DEMO_SEED='true'; python -m app.seeds.demo`
- repeated seed command with same environment
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m ruff check .`
- `docker compose run --rm api python -m pytest tests/test_seed_demo.py tests/test_seed_smoke.py -q`
- `docker compose run --rm api python -m pytest -q`

Command results:
- Focused seed tests without PostGIS: `8 passed, 1 skipped, 1 warning`.
- Focused seed/smoke with PostGIS: `10 passed, 1 warning`.
- Host ruff: `All checks passed!`.
- Host pytest without PostGIS URL: `207 passed, 26 skipped, 1 warning`.
- Alembic current with PostGIS: `0010_payouts_and_earnings (head)`.
- Seed command run 1: success, 4 users, 3 zones, 2 trips, 12 pings, 2 analytics,
  2 estimates, 2 payouts, 2 ledger entries.
- Seed command run 2: success with the same ids and counts.
- Host full PostGIS pytest: `233 passed, 1 warning`.
- Docker Python: `Python 3.12.13`.
- Docker ruff: `All checks passed!`.
- Docker seed/smoke tests: `10 passed, 1 warning`.
- Docker full pytest: `233 passed, 1 warning`.
- The only warning is the existing Starlette TestClient/httpx deprecation warning.

Known issues:
- No known implementation blockers.
- Existing TestClient deprecation warning remains unrelated to Slice 12.

Out-of-scope compliance:
- No new database tables.
- No new Alembic migration.
- No production seed automation.
- No app-startup or Docker Compose auto-seed.
- No new API endpoints.
- No frontend/mobile implementation.
- No map tiles, raw GPS export, route polyline export, or new heatmap metrics.
- No new analytics, impression, or payout formulas.
- No billing, settlement, withdrawals, payment providers, taxes, audience identity,
  retargeting, external providers, deployment, or AI scope.

Acceptance criteria checklist:
- No new tables: yes.
- No new migration: yes.
- Alembic head remains `0010_payouts_and_earnings`: yes.
- Documented local/demo seed command exists: yes.
- Seed refuses production-like environments: yes.
- Seed is idempotent: yes.
- Seed creates/fetches required demo graph: yes.
- Demo users can log in: yes, covered by smoke tests.
- Demo advertiser reporting/heatmap endpoints return meaningful data: yes.
- Demo driver earnings endpoints return meaningful data: yes.
- OpenAPI schema generates: yes.
- Frontend-facing tags/summaries/examples improved where practical: yes.
- README documents seed usage, demo credentials, smoke workflow, and production caveats:
  yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 Docker verification performed: yes.
- No deferred/future scope implemented: yes.

Manual verification steps:
- `docker compose up -d db redis`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head`
- `$env:ALLOW_DEMO_SEED='true'; python -m app.seeds.demo`
- Log in with `advertiser@demo.mobility.local` / `DemoAdvertiser12345!`.
- Follow the README smoke workflow.

Questions for Pro reviewer:
- Please confirm that requiring `ALLOW_DEMO_SEED=true` for local/dev but allowing tests
  without override is acceptable.
