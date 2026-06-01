PRO REVIEW PACKET

Slice:
Slice 10 - Advertiser dashboard summary and campaign reporting APIs.

Repo state summary:
- Branch: `slice-10-advertiser-reporting`.
- Slice 9 was accepted by Pro and committed before this work.
- Current Alembic head remains `0010_payouts_and_earnings`.
- Slice 10 implements read-only advertiser reporting over existing stored Slice 0-9
  data only.
- A clean implementation subagent was used for the implementation plan and patch, but
  it hit the subagent usage limit before final reporting; the orchestrator completed
  verification and packet preparation locally.

Commit status:
- Not committed yet.
- Slice 10 should only be committed after Pro PASS and local reconciliation.

Files changed:
- `README.md`
- `app/api/v1/advertiser_reports.py`
- `app/api/v1/router.py`
- `app/schemas/reports.py`
- `app/services/reports.py`
- `docs/build-loop/reports/slice-10-advertiser-dashboard-and-campaign-reports.md`
- `docs/build-loop/slice-log.md`
- `tests/test_advertiser_reports.py`

Diff summary:
- Adds a new advertiser reports router and mounts it under the existing `/api/v1`
  router.
- Adds reporting response schemas with Decimal-as-string serialization.
- Adds read-only reporting service logic using simple SQL aggregation and Python-side
  merging for daily metrics.
- Adds focused tests for dashboard, campaign summary, daily metrics, trips, bundled
  report, RBAC/privacy, zero states, date validation, no auto-calculation, and no
  migration/table guardrails.
- Updates README with Slice 10 endpoint and behavior notes.
- Updates the build-loop slice log to mark Slice 10 in progress and record the report
  path.

Database migrations:
- None.
- No new Alembic revision was added.
- No new database tables were added.
- Existing head remains `0010_payouts_and_earnings`.

API endpoints:
- `GET /api/v1/advertiser/dashboard/summary`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/summary`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/daily-metrics`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/trips`
- `GET /api/v1/advertiser/campaigns/{campaign_id}/report`

Security/validation implemented:
- All endpoints are advertiser-only through the existing advertiser user dependency.
- Admin, driver, and unauthenticated requests are rejected.
- Campaign-specific endpoints use the existing advertiser campaign lookup, preserving
  organization scoping and non-leaking 404 behavior for cross-organization campaigns.
- Date filters require timezone-aware `start_at`/`end_at`.
- `start_at > end_at` returns `INVALID_DATE_RANGE`.
- Pagination is bounded with FastAPI query validation.
- Trip, analytics, impression, and payout filters use existing enum validation.
- Schemas omit driver ids, driver profile ids, driver name/email/phone/license, vehicle
  plate numbers, raw GPS coordinates, raw ping rows, idempotency keys, ledger entry
  ids/details, payment account data, internal audit events, and password hashes.

Dashboard aggregation implemented:
- Campaign counts by current campaign status for the current advertiser organization.
- Assignment counts by current assignment status for campaigns in the organization.
- Trip counts by `trip_sessions.started_at` window.
- Stored impression totals by current impression formula and `estimated_at` window.
- Stored payout/cost totals by current payout formula and `calculated_at` window.
- Fraud flag counts by `detected_at` window.
- Average quality from stored trip analytics.
- Stable zero cost/impression/quality shapes when there is no data.

Campaign summary implemented:
- Uses existing advertiser campaign tenancy lookup.
- Returns campaign metadata, creative counts, zone counts, assignment counts, trip
  counts, route analytics totals, stored impression summary, stored payout/cost
  summary, and fraud flag counts.
- Returns stable zero shapes for campaigns with no downstream rows.

Daily metrics aggregation implemented:
- Groups by UTC calendar date derived from `trip_sessions.started_at`.
- Aggregates trip count, analyzed trip count, distance, stored impressions, average
  confidence, stored payout totals, open fraud flag count, and average quality.
- Supports `start_at`, `end_at`, `limit`, and `offset`.
- Does not add or use a materialized daily metrics table.

Campaign trip reporting/privacy implemented:
- Lists campaign-scoped trip summaries with pagination.
- Supports filters for trip status, `has_fraud_flags`, analytics status, impression
  status, and payout status.
- Includes opaque trip id, assignment id, vehicle type, trip status/timestamps,
  analytics summary, impression summary, cost summary, and fraud counts.
- Returns null analytics/impression/cost sections when optional downstream rows are
  missing.
- Does not expose driver PII, driver profile ids, vehicle plates, raw pings,
  idempotency keys, ledger ids, or ledger details.

Bundled report implemented:
- Returns compact campaign report JSON for frontend convenience.
- Reuses campaign summary and daily metrics service logic.
- Includes campaign metadata as `summary`, plus daily metrics, creative, zone,
  assignment, trip, impression, cost, and fraud sections.
- Does not include an unpaginated trip list, CSV/PDF export, record creation, or
  calculation triggers.

Tests/checks run:
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

Exact command outputs or concise failure excerpts:
- Host `python -m ruff check .`: all checks passed.
- Host focused reporting tests: `4 passed, 1 warning`.
- Host related reporting/campaign/impression/payout tests: `36 passed, 1 warning`.
- Host full `python -m pytest -q`: `195 passed, 21 skipped, 1 warning in 384.46s`.
- Host Alembic/PostGIS current: `0010_payouts_and_earnings (head)`.
- Host full PostGIS `python -m pytest -q`: `216 passed, 1 warning in 549.22s`.
- Docker `docker compose build api`: image built successfully.
- Docker Python version: `Python 3.12.13`.
- Docker `python -m ruff check .`: all checks passed.
- Docker `python -m pytest -q`: `216 passed, 1 warning in 525.15s`.
- Existing warning: FastAPI/TestClient emits a StarletteDeprecationWarning about
  `httpx`; tests pass.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verifies
  Python 3.12.13 successfully.
- Plain host tests skip PostGIS-specific checks when no PostGIS URL is configured;
  full PostGIS tests pass with the local PostGIS URL and in Docker.
- Dashboard campaign and assignment status counts are current-state counts, not
  date-windowed lifecycle counts, because the current schema lacks campaign/assignment
  status history tables. Trip, analytics, impression, payout, and fraud metrics use
  the documented date fields.

Out-of-scope confirmation:
- No new tables.
- No Alembic migration.
- No materialized campaign daily metrics table.
- No heatmap APIs, heatmap cache, map tiles, geospatial grid aggregation, route
  polyline generation, or raw GPS export.
- No new route analytics, impression estimation, or payout calculations.
- No automatic report materialization, background jobs, or scheduled rollups.
- No PDF/CSV export.
- No billing, invoicing, advertiser charging, settlement, withdrawal, payment provider,
  or tax handling.
- No manual fraud review workflow, notifications, seed/demo data, external traffic/map
  providers, audience identity, retargeting, device pooling, creative binary upload,
  OAuth, refresh tokens, frontend/mobile, GitHub/PR, deployment, or AI/computer vision.

Acceptance criteria checklist:
- No new database tables are created: yes.
- No new Alembic migration is created: yes.
- Existing Alembic head remains `0010_payouts_and_earnings`: yes.
- Advertiser can read organization dashboard summary: yes.
- Dashboard summary aggregates only current organization data: yes.
- Advertiser can read own campaign summary: yes.
- Advertiser can read own campaign daily metrics: yes.
- Advertiser can read own campaign trip summaries: yes.
- Advertiser can read own campaign bundled report: yes.
- Cross-organization campaign reporting access is blocked with non-leaking behavior:
  yes.
- Date filters are validated and applied to trip/analytics, impression, payout, and
  fraud metrics: yes.
- Pagination is enforced where applicable: yes.
- Reporting aggregates stored data only and does not auto-run analytics, impression
  estimation, or payout calculation: yes.
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

Codex questions:
- Is current-state counting for campaign/assignment statuses acceptable under Slice 10's
  date-filtered endpoints, given there is no status-history/event table to support
  historical counts?
- Should the bundled report's compact `summary` field remain campaign metadata plus
  separate aggregate sections, or should `summary` duplicate the full campaign summary
  response object?

Orchestrator recommendation: PASS_CANDIDATE
