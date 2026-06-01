CODEX BUILD REPORT

Slice:
Slice 10 - Advertiser dashboard summary and campaign reporting APIs

Status: PASS_CANDIDATE

Summary:
Implemented read-only advertiser reporting APIs that aggregate existing stored
campaign, creative, zone, assignment, trip, route analytics, fraud, impression,
payout, and ledger data. The slice adds no database tables and no Alembic migration.
Reporting remains advertiser-tenant scoped, does not run missing analytics,
impression, or payout calculations, and avoids driver PII, vehicle plate numbers,
raw pings, idempotency keys, ledger details, and payment data.

Local investigation performed:
- Read `agent.md`.
- Read `docs/build-loop/prompts/slice-10-advertiser-dashboard-and-campaign-reports.md`.
- Reviewed accepted Slice 0 through Slice 9 reports as needed, especially Slice 9.
- Confirmed API prefix is `/api/v1`.
- Confirmed existing standard error envelope uses `AppError`.
- Confirmed advertiser tenancy helpers are in `app/services/campaigns.py`.
- Confirmed current Alembic head remains `0010_payouts_and_earnings`.
- Confirmed Decimal response convention serializes numeric values as strings.
- Confirmed no existing Slice 10 reporting tables are present.
- Clean worker Huygens produced the implementation plan and patch before hitting the
  subagent usage limit; the orchestrator completed local verification and this report.

Files changed:
- `README.md`
- `app/api/v1/advertiser_reports.py`
- `app/api/v1/router.py`
- `app/schemas/reports.py`
- `app/services/reports.py`
- `docs/build-loop/reports/slice-10-advertiser-dashboard-and-campaign-reports.md`
- `docs/build-loop/slice-log.md`
- `tests/test_advertiser_reports.py`

Database migrations:
- None.
- No Alembic migration file was added.
- Existing Alembic head remains `0010_payouts_and_earnings`.
- Slice 10 reporting uses on-demand aggregation over existing stored Slice 0-9 data.

API endpoints implemented:
- `GET /api/v1/advertiser/dashboard/summary`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/summary`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/trips`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/report`

Security/validation implemented:
- All Slice 10 endpoints use the existing advertiser-only dependency.
- Admin, driver, and unauthenticated users are rejected from Slice 10 endpoints.
- Campaign-specific endpoints reuse existing advertiser campaign tenancy lookup and
  return non-leaking 404 for cross-organization campaigns.
- `start_at` and `end_at` query params must be timezone-aware.
- `start_at > end_at` returns `INVALID_DATE_RANGE`.
- Pagination limits and offsets use FastAPI query validation.
- Trip filters use existing enum validation for trip, analytics, impression, and payout
  statuses.
- Reporting schemas omit driver user/profile ids, driver name/email/phone/license,
  vehicle plate numbers, raw GPS coordinates, raw pings, idempotency keys, ledger
  entry ids/details, payment account data, audit events, and password hashes.

Dashboard aggregation implemented:
- Aggregates campaign status counts across the current advertiser organization.
- Aggregates assignment status counts across the current advertiser organization.
- Aggregates trip counts by status using `trip_sessions.started_at` date filters.
- Aggregates stored impression estimates by current formula version and
  `impression_estimates.estimated_at`.
- Aggregates stored payout calculations by current formula version and
  `payout_calculations.calculated_at`.
- Aggregates fraud flag counts by `fraud_flags.detected_at`.
- Returns stable zero cost/impression/quality shapes when no downstream data exists.

Campaign summary implemented:
- Uses existing organization-scoped campaign lookup.
- Returns campaign metadata plus creative status counts, zone type counts, assignment
  status counts, trip status counts, route analytics totals, stored impression
  aggregates, stored payout/cost aggregates, and fraud flag counts.
- Returns stable zero shapes for campaigns with no downstream data.

Daily metrics aggregation implemented:
- Groups by UTC calendar date derived from `trip_sessions.started_at`.
- Aggregates trip count, analyzed trip count, distance, stored impressions, average
  confidence, stored payout totals, open fraud flag count, and average quality.
- Supports `start_at`, `end_at`, `limit`, and `offset`.
- Uses Python-side merging of simple grouped/source queries instead of a materialized
  reporting table.

Campaign trip reporting/privacy implemented:
- Lists campaign-scoped trip summaries with pagination.
- Supports filters for trip status, fraud presence, analytics status, impression
  status, and payout status.
- Includes only opaque trip and assignment ids, vehicle type, trip status/timestamps,
  analytics summary, impression summary, cost summary, and fraud flag counts.
- Does not expose driver PII, driver profile ids, vehicle plate numbers, raw pings,
  idempotency keys, ledger ids, or ledger details.
- Returns null nested analytics/impression/cost sections when optional downstream rows
  are absent.

Bundled report implemented:
- Returns compact campaign report JSON for frontend convenience.
- Reuses campaign summary and daily metrics service logic.
- Includes summary, daily metrics, creative, zone, assignment, trip, impression, cost,
  and fraud sections.
- Does not include a huge unpaginated trip list, PDF/CSV export, records creation, or
  calculation triggers.

Tests added/updated:
- Added advertiser dashboard aggregation, organization scoping, zero-state, date
  validation, and no-auto-calculation coverage.
- Added campaign summary aggregation and stable zero-shape coverage.
- Added daily metrics grouping, pagination, and UTC date coverage.
- Added campaign trip privacy, filtering, RBAC, and validation coverage.
- Added bundled report coverage.
- Added migration/scope guardrail asserting no Slice 10 migration/table additions.
- Updated README endpoint and reporting behavior notes.

Commands run:
- `python -m ruff check .`
- `python -m pytest tests/test_advertiser_reports.py -q`
- `python -m pytest tests/test_advertiser_reports.py tests/test_campaigns.py tests/test_impression_estimates.py tests/test_payouts.py -q`
- `python -m pytest -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m ruff check .`
- `docker compose run --rm api python -m pytest -q`

Command results:
- Host `python -m ruff check .`: all checks passed.
- Host focused reporting tests: 4 passed, 1 existing FastAPI/TestClient warning.
- Host related reporting/campaign/impression/payout tests: 36 passed, 1 existing
  FastAPI/TestClient warning.
- Host full `python -m pytest -q`: 195 passed, 21 skipped, 1 existing
  FastAPI/TestClient warning.
- Host Alembic with local PostGIS URL: current reported
  `0010_payouts_and_earnings (head)`.
- Host full PostGIS `python -m pytest -q`: 216 passed, 1 existing
  FastAPI/TestClient warning.
- Docker `docker compose build api`: image built successfully.
- Docker Python version: Python 3.12.13.
- Docker `python -m ruff check .`: all checks passed.
- Docker `python -m pytest -q`: 216 passed, 1 existing FastAPI/TestClient warning in
  525.15 seconds.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified
  Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests
  pass.
- Plain host tests skip PostGIS-specific checks when no PostGIS URL is configured;
  full PostGIS tests pass with the local PostGIS URL and in Docker.
- Dashboard campaign and assignment status counts are current-state counts rather than
  date-windowed lifecycle counts because the existing campaign/assignment models do not
  expose event-history tables. Trip, analytics, impression, payout, and fraud metrics
  use the documented date fields.

Out-of-scope compliance:
- No new database tables.
- No Alembic migration.
- No materialized campaign daily metrics.
- No heatmap APIs, heatmap cache tables, map tiles, map matching, geocoding, or
  geospatial grid aggregation.
- No new route analytics, impression estimation, or payout calculation triggers.
- No background jobs, scheduled rollups, or automatic report materialization.
- No CSV/PDF export.
- No billing, advertiser charging, settlement, withdrawal, payment provider, invoice,
  or tax handling.
- No notifications, manual fraud review workflow, seed/demo data, audience identity,
  retargeting, device pooling, frontend/mobile, OAuth, refresh tokens, GitHub/PR setup,
  deployment, or AI/computer vision.

Acceptance criteria checklist:
- No new database tables created: yes.
- No new Alembic migration created: yes.
- Existing Alembic head remains `0010_payouts_and_earnings`: yes.
- Advertiser can read organization dashboard summary: yes.
- Dashboard aggregates only current organization data: yes.
- Advertiser can read own campaign summary: yes.
- Advertiser can read own campaign daily metrics: yes.
- Advertiser can read own campaign trip summaries: yes.
- Advertiser can read own campaign bundled report: yes.
- Cross-organization campaign reporting access is blocked with non-leaking behavior:
  yes.
- Date filters are validated and applied consistently to trip/analytics, impression,
  payout, and fraud metrics: yes.
- Pagination is enforced where applicable: yes.
- Reporting aggregates stored data only and does not auto-run calculations: yes.
- Reporting endpoints return stable zero shapes when no data exists: yes.
- Reporting endpoints do not expose driver PII, vehicle plate numbers, raw pings,
  idempotency keys, ledger details, payment account data, password hashes, or unrelated
  sensitive data: yes.
- Admin/driver/unauthenticated access boundaries are enforced: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Manual verification steps:
- Use an advertiser bearer token to call
  `GET /api/v1/advertiser/dashboard/summary`.
- Use the same advertiser bearer token to call
  `GET /api/v1/advertiser/campaigns/{campaign_id}/summary`.
- Call `GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics` with and without
  `start_at`, `end_at`, `limit`, and `offset`.
- Call `GET /api/v1/advertiser/campaigns/{campaign_id}/trips` with trip, analytics,
  impression, payout, and fraud filters.
- Call `GET /api/v1/advertiser/campaigns/{campaign_id}/report`.
- Use another advertiser organization's token for the same campaign id and confirm 404.
- Use admin, driver, and missing auth and confirm expected rejections.

Questions for Pro reviewer:
- Please review whether current-state campaign/assignment status counts are acceptable
  for Slice 10 date-filtered dashboard/summary responses given the current schema lacks
  campaign/assignment status event history.
- Please review whether the bundled report's compact `summary` field as campaign
  metadata plus separate aggregate sections is the preferred frontend contract, or
  whether `summary` should duplicate the full campaign summary object.
