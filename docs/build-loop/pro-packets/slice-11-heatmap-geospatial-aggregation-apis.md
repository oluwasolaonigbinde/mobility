PRO REVIEW PACKET

Slice:
Slice 11 - Heatmap/geospatial aggregation APIs.

Repo state summary:
- Branch: `slice-11-heatmaps`.
- Slice 10 was accepted by Pro and committed before this work.
- Current Alembic head remains `0010_payouts_and_earnings`.
- Slice 11 implements bounded read-only heatmap/geospatial aggregation APIs over
  existing stored Slice 0-10 data only.
- Clean subagents were used:
  - Einstein implemented the feature slice.
  - Lorentz performed a read-only risk checklist.
  - Gibbs performed a clean review/fix pass for validation and SQL scoping.
- The orchestrator reviewed the patch, ran full host/PostGIS/Docker checks, and
  prepared this packet.

Commit status:
- Not committed yet.
- Slice 11 should only be committed after Pro PASS and local reconciliation.

Files changed:
- `.env.example`
- `README.md`
- `app/api/v1/heatmaps.py`
- `app/api/v1/router.py`
- `app/core/config.py`
- `app/schemas/heatmaps.py`
- `app/services/heatmaps.py`
- `docs/build-loop/reports/slice-11-heatmaps.md`
- `docs/build-loop/slice-log.md`
- `tests/test_heatmaps.py`

Diff summary:
- Adds heatmap settings and validation for default/min/max resolution, max bbox area,
  max date range, max cells, and min trips per cell.
- Adds GeoJSON response schemas with Decimal-as-string properties.
- Adds a heatmap API router mounted under the existing v1 router.
- Adds read-only PostGIS heatmap service logic with bbox filtering and EPSG:3857
  meter-grid aggregation.
- Adds deterministic distance and impression allocation by trip ping share in the
  requested bbox/date window.
- Adds tests for validation, RBAC, tenant scoping, admin filters, PostGIS aggregation,
  privacy, no mutation, empty results, and no migration/table guardrails.
- Updates README with Slice 11 endpoints and scope notes.
- Updates the slice log to mark Slice 11 in progress.

Database migrations:
- None.
- No new Alembic revision was added.
- No new database tables were added.
- Existing head remains `0010_payouts_and_earnings`.

API endpoints:
- `GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap`
- `GET /api/v1/admin/heatmap`

Security/validation implemented:
- Advertiser endpoint is advertiser-only and uses the existing advertiser campaign
  tenancy lookup.
- Admin endpoint is admin-only.
- Driver users, crossed roles, and unauthenticated users are rejected.
- Cross-organization advertiser campaign access returns non-leaking 404 via existing
  campaign lookup.
- `bbox` is required and validated for numeric/finite values, coordinate bounds,
  ordering, max area, and estimated max cell count.
- `resolution_m` defaults only when omitted and is rejected outside configured min/max.
- `metric` is limited to `ping_count`, `trip_count`, `distance_m`, and
  `estimated_impressions`.
- `start_at` and `end_at` must be timezone-aware; invalid ordering and over-limit
  date ranges are rejected.
- Admin `campaign_id` plus `organization_id` mismatch returns
  `INVALID_HEATMAP_FILTERS`.
- Expected errors use the existing `AppError` standard error envelope.

Heatmap aggregation implemented:
- Aggregates existing stored rows only:
  - `location_pings`
  - `trip_sessions`
  - `trip_analytics`
  - `impression_estimates`
  - `campaigns`
  - `vehicles`
- Does not auto-run or create analytics, estimates, payouts, ledger entries, trips,
  pings, campaigns, zones, or creatives.
- Empty results return valid GeoJSON FeatureCollections with `features: []`.

PostGIS grid implemented:
- Bbox filtering uses `location_pings.geom && bbox.geom` and
  `ST_Intersects(location_pings.geom, bbox.geom)`.
- Grid grouping transforms pings to EPSG:3857 and groups by:
  `floor(ST_X(ST_Transform(lp.geom, 3857)) / resolution_m) * resolution_m`
  and the equivalent y coordinate.
- Feature cell polygons are built with `ST_MakeEnvelope(..., 3857)`, transformed back
  to SRID 4326, and returned using `ST_AsGeoJSON`.

Metric allocation implemented:
- `ping_count`: direct cell ping count.
- `trip_count`: distinct trip count per cell.
- `distance_m`: stored current-formula `trip_analytics.distance_m` allocated by each
  trip's ping share within the requested bbox/date window.
- `estimated_impressions`: latest stored current-formula
  `impression_estimates.estimated_impressions` per trip allocated by each trip's ping
  share within the requested bbox/date window.
- `average_quality_score`: average stored current-formula trip analytics quality score.
- Optional `final_payout` was omitted because admin-only/multi-currency representation
  and advertiser cost privacy are better handled in a later explicit slice.

Privacy/sensitivity controls implemented:
- Responses return aggregate GeoJSON polygon cells, not raw ping rows or point features.
- Cell properties include `cell_id`, `metric`, `weight`, `ping_count`, `trip_count`,
  `distance_m`, `estimated_impressions`, and `average_quality_score`.
- Responses do not expose driver user ids, driver names, driver emails, driver phones,
  driver license numbers, driver profile ids, vehicle plate numbers, raw GPS point
  rows, raw ping ids, batch ids, idempotency keys, ledger details, payment data,
  password hashes, or audit events.

Tests/checks run:
- `python -m pytest tests/test_heatmaps.py -q`
  - `4 passed, 3 skipped, 1 warning`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_heatmaps.py -q`
  - `7 passed, 1 warning`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
  - current revision: `0010_payouts_and_earnings (head)`
- `python -m ruff check .`
  - `All checks passed!`
- `python -m pytest -q`
  - `199 passed, 24 skipped, 1 warning`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
  - `223 passed, 1 warning`
- `docker compose run --rm api python --version`
  - `Python 3.12.13`
- `docker compose run --rm api python -m ruff check .`
  - `All checks passed!`
- `docker compose run --rm api python -m pytest -q`
  - `223 passed, 1 warning`

Exact command outputs or concise failure excerpts:
- No command failures remain.
- The only warning is the existing Starlette TestClient/httpx deprecation warning.

Known issues:
- None known.

Out-of-scope confirmation:
- No new database tables.
- No new Alembic migration.
- No heatmap cache or materialized cells.
- No map tiles or vector tile endpoint.
- No Mapbox integration.
- No frontend implementation.
- No route polyline generation/export.
- No raw GPS ping export.
- No background jobs or scheduled rollups.
- No new analytics, impression, payout, billing, settlement, withdrawal, seed, audience,
  retargeting, notification, or deployment scope.

Acceptance criteria checklist:
- No new database tables: yes.
- No new Alembic migration: yes.
- Alembic head remains `0010_payouts_and_earnings`: yes.
- Advertiser can read own campaign heatmap: yes.
- Advertiser cannot read another organization's campaign heatmap: yes.
- Admin can read bounded aggregate heatmap: yes.
- Admin filters by campaign and organization: yes.
- Admin filters by vehicle type: yes.
- Bbox is required and validated: yes.
- Resolution, metric, date range, and request size are validated: yes.
- PostGIS spatial filtering and meter-grid grouping are used: yes.
- Response is a GeoJSON FeatureCollection: yes.
- Cells include aggregate properties and selected metric weight: yes.
- Required metrics are supported: yes.
- Distance/impression values use stored records and ping-share allocation: yes.
- Empty data returns stable empty FeatureCollection: yes.
- Endpoints are read-only and do not auto-run calculations: yes.
- Sensitive data is not exposed: yes.
- Admin/advertiser/driver/unauthenticated boundaries are enforced: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 Docker verification performed: yes.
- No deferred/future scope implemented: yes.

Codex questions:
- Please confirm that selecting the latest stored current-formula impression estimate
  per trip is the preferred anti-double-counting rule for heatmap allocation.
- Please confirm that omitting optional `final_payout` is acceptable for Slice 11.

Orchestrator recommendation: PASS_CANDIDATE
