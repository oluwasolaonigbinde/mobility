PRO REVIEW PACKET

Slice:
Slice 12 - Seed/demo data and API docs hardening.

Repo state summary:
- Branch: `slice-12-seed-demo-docs`.
- Slice 11 was accepted by Pro and committed before this work.
- Current Alembic head remains `0010_payouts_and_earnings`.
- Slice 12 implements local/demo seeding and documentation hardening only.
- Clean subagents were used:
  - Sagan implemented the slice.
  - Averroes performed a read-only seed/docs risk checklist.
  - Darwin performed a clean review/fix pass and found no blockers.
- The orchestrator completed full host/PostGIS/Docker verification and prepared this
  packet.

Commit status:
- Not committed yet.
- Slice 12 should only be committed after Pro PASS and local reconciliation.

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

Diff summary:
- Adds `ALLOW_DEMO_SEED=false` to settings and `.env.example`.
- Adds explicit seed entry point `python -m app.seeds.demo`.
- Adds idempotent demo graph creation using existing models and services.
- Adds demo safety checks for production-like environments, explicit confirmation,
  database URL, PostGIS dialect, and Alembic head.
- Adds local-only demo credentials, seed command, smoke workflow, and frontend endpoint
  notes to README.
- Normalizes OpenAPI tags and adds focused login/report/heatmap descriptions/examples.
- Adds seed safety, idempotency, OpenAPI/docs, and frontend smoke tests.
- Updates slice log to mark Slice 12 in progress.

Database migrations:
- None.
- No new Alembic revision was added.
- No new tables were added.
- Existing head remains `0010_payouts_and_earnings`.

API endpoints:
- No new endpoints.
- Existing endpoint documentation metadata was improved only.

Security/validation implemented:
- `ALLOW_DEMO_SEED` defaults to false.
- `ENVIRONMENT=production`, `prod`, or `staging` is refused even if override is set.
- Local/dev/development requires `ALLOW_DEMO_SEED=true`.
- Test environment may run seed without override for testability.
- `DATABASE_URL` is required.
- Seed command requires PostgreSQL/PostGIS and Alembic head
  `0010_payouts_and_earnings`.
- Seed does not run at app startup, during Docker Compose startup, or through any API.
- Demo credentials are documented as local-only and not production secrets.

Seed command implemented:
- Module entry point: `python -m app.seeds.demo`.
- Loads settings, opens an async SQLAlchemy session, checks DB readiness, builds the
  graph, commits, prints a summary, and returns nonzero on expected failures.

Seed idempotency implemented:
- Users are found by normalized email.
- Organization is found by stable demo name.
- Memberships are found by organization and user.
- Driver profile is found by driver user id.
- Vehicle is found by normalized plate/country.
- Campaign, creative, and zones are found by stable campaign/name keys.
- Trips are found by stable `seed_trip_key` in metadata.
- Ping batches are found by stable idempotency keys and regenerated only when payload
  hash/count mismatch.
- Traffic profile and payout rule are found by stable name/metadata.
- Existing analytics, impression, payout, and ledger service idempotency is reused.
- Repeated real seed runs produced the same ids and counts.

Demo dataset implemented:
- Demo users:
  - `admin@demo.mobility.local`
  - `advertiser@demo.mobility.local`
  - `viewer@demo.mobility.local`
  - `driver@demo.mobility.local`
- Organization: `Demo Mobility Advertiser`.
- Active driver profile and `DEMO-001` vehicle.
- Active `Demo Lagos Mobility Campaign`.
- Ready `Demo Exterior Wrap` creative.
- Target, bonus, and exclusion Lagos zones.
- Active assignment and activation events.
- Two ended trips across separate UTC days.
- Twelve PostGIS location pings in documented bbox `3.35,6.43,3.47,6.56`.
- Two route analytics rows.
- Two impression estimates.
- Two payout calculations.
- Two pending driver ledger entries.

OpenAPI/docs hardening implemented:
- Major router tags use frontend-facing names.
- Login request has demo credential examples.
- Heatmap endpoint descriptions include demo bbox.
- Report and `/me` descriptions were clarified.
- README documents seed command, credentials, smoke workflow, demo bbox, and production
  caveats.

Frontend smoke workflow documented:
- README includes advertiser login, `/me`, dashboard, campaign list, summary, daily
  metrics, trips, report, impressions summary, cost summary, heatmap, driver login,
  earnings summary, and ledger.

Tests/checks run:
- `python -m pytest tests/test_seed_demo.py -q`
  - `8 passed, 1 skipped, 1 warning`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_seed_demo.py tests/test_seed_smoke.py -q`
  - `10 passed, 1 warning`
- `python -m ruff check .`
  - `All checks passed!`
- `python -m pytest -q`
  - `207 passed, 26 skipped, 1 warning`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
  - `0010_payouts_and_earnings (head)`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; $env:ALLOW_DEMO_SEED='true'; python -m app.seeds.demo`
  - success: 4 users, 3 zones, 2 trips, 12 pings, 2 analytics, 2 estimates,
    2 payouts, 2 ledger entries
- repeated seed command
  - success with the same ids and counts
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
  - `233 passed, 1 warning`
- `docker compose run --rm api python --version`
  - `Python 3.12.13`
- `docker compose run --rm api python -m ruff check .`
  - `All checks passed!`
- `docker compose run --rm api python -m pytest tests/test_seed_demo.py tests/test_seed_smoke.py -q`
  - `10 passed, 1 warning`
- `docker compose run --rm api python -m pytest -q`
  - `233 passed, 1 warning`

Exact command outputs or concise failure excerpts:
- No command failures remain.
- The only warning is the existing Starlette TestClient/httpx deprecation warning.

Known issues:
- None known.

Out-of-scope confirmation:
- No new database tables.
- No new Alembic migration.
- No production seed automation.
- No app startup or Docker Compose auto-seed.
- No synthetic data API or public reset endpoint.
- No frontend/mobile implementation.
- No map tiles, raw GPS export, route polyline export, or new heatmap metrics.
- No new analytics, impression, or payout formulas.
- No billing, settlement, withdrawals, real payment integration, tax, notifications,
  external providers, deployment, retargeting, audience identity, or AI scope.

Acceptance criteria checklist:
- No new database tables: yes.
- No new Alembic migration: yes.
- Alembic head remains `0010_payouts_and_earnings`: yes.
- Documented local/demo seed command exists: yes.
- Seed refuses production-like environments: yes.
- Seed is idempotent: yes.
- Seed creates/fetches all required demo records: yes.
- Demo users can log in: yes.
- Demo advertiser dashboard/reporting/heatmap returns meaningful data: yes.
- Demo driver earnings endpoints return meaningful data: yes.
- OpenAPI schema generates: yes.
- Key frontend endpoints have useful tags/summaries/examples where practical: yes.
- README documents seed usage, credentials, smoke workflow, and caveats: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 Docker verification performed: yes.
- No deferred/future scope implemented: yes.

Codex questions:
- Please confirm that requiring `ALLOW_DEMO_SEED=true` for local/dev while allowing
  test environment without override is acceptable.

Orchestrator recommendation: PASS_CANDIDATE
