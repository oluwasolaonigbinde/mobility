CODEX BUILD REPORT

Slice:
Slice 11 - Heatmap/geospatial aggregation APIs

Status: PASS_CANDIDATE

Summary:
Implemented bounded read-only heatmap APIs for advertiser campaign maps and admin
geospatial inspection. The implementation adds no tables and no Alembic migration;
it aggregates existing stored location pings, trip sessions, route analytics, and
impression estimates into GeoJSON polygon cells using PostGIS bbox filtering and a
meter-based grid.

Local investigation performed:
- Read `agent.md` and the Slice 11 prompt.
- Reviewed accepted Slice 0 through Slice 10 reports and Pro responses.
- Confirmed `/api/v1` is mounted from `settings.api_v1_prefix`.
- Confirmed standard errors use `AppError` and the existing error envelope.
- Confirmed advertiser scoping should reuse `get_advertiser_campaign`.
- Confirmed PostGIS point storage through `LocationPing.geom` and `point_value`.
- Confirmed current Alembic head remains `0010_payouts_and_earnings`.
- Confirmed no existing heatmap, heatmap cache, or materialized heatmap table exists.
- Confirmed PostGIS tests use `TEST_DATABASE_URL` or `DATABASE_URL`.

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

Database migrations:
- None.
- No Alembic revision was added.
- No new database tables were added.
- Existing Alembic head remains `0010_payouts_and_earnings`.

API endpoints implemented:
- `GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap`
- `GET /api/v1/admin/heatmap`

Security/validation implemented:
- Advertiser endpoint uses the existing advertiser dependency and campaign tenancy
  lookup.
- Admin endpoint uses the existing admin dependency.
- Admin, driver, advertiser, and unauthenticated cross-role boundaries are tested.
- Required `bbox` is parsed as `min_lon,min_lat,max_lon,max_lat`.
- Bbox numeric, finite, coordinate range, ordering, area, and estimated cell-count
  limits are enforced.
- `resolution_m` defaults only when omitted and is rejected outside configured min/max.
- `metric` supports only `ping_count`, `trip_count`, `distance_m`, and
  `estimated_impressions`.
- `start_at` and `end_at` must be timezone-aware; ordering and max date range are
  enforced exactly.
- Admin `campaign_id` plus `organization_id` mismatch returns
  `INVALID_HEATMAP_FILTERS`.

Heatmap aggregation implemented:
- Aggregates existing stored rows only.
- Does not create route analytics, impression estimates, payouts, ledger entries,
  campaigns, trips, pings, creatives, or zones.
- Returns stable empty FeatureCollections when no pings match.
- Uses stored route analytics for distance/quality and stored impression estimates
  for impression weights.

PostGIS grid implemented:
- Uses `location_pings.geom && ST_MakeEnvelope(...)`.
- Uses `ST_Intersects(location_pings.geom, bbox)`.
- Transforms ping points to EPSG:3857.
- Groups cells with `floor(ST_X/ST_Y / resolution_m) * resolution_m`.
- Builds cell polygons with `ST_MakeEnvelope(..., 3857)`.
- Transforms cell polygons back to SRID 4326 and serializes with `ST_AsGeoJSON`.

Metric allocation implemented:
- `ping_count`: cell ping count.
- `trip_count`: distinct trip count per cell.
- `distance_m`: stored current-formula trip analytics distance allocated by each
  trip's ping share within the requested bbox/date window.
- `estimated_impressions`: latest stored current-formula impression estimate per
  trip allocated by that trip's ping share within the requested bbox/date window.
- Optional `final_payout` was intentionally omitted to avoid multi-currency and
  advertiser-cost ambiguity.

Privacy/sensitivity controls implemented:
- Responses expose GeoJSON aggregate polygon cells only.
- Response properties include aggregate cell id, selected metric, weight, ping count,
  trip count, distance, estimated impressions, and average quality score.
- Responses do not expose driver user ids, driver names/emails/phones/license numbers,
  driver profile ids, vehicle plate numbers, raw point rows, raw ping ids, batch ids,
  idempotency keys, ledger details, payment data, or password hashes.

Tests added/updated:
- Added `tests/test_heatmaps.py`.
- Covered heatmap settings defaults and validation.
- Covered bbox, resolution, metric, date, and max-cell validation.
- Covered timezone-aware date enforcement and exact date-range cap behavior.
- Covered advertiser own campaign and cross-organization 404 behavior.
- Covered admin global, campaign, organization, vehicle type, empty, and mismatch
  filter behavior.
- Covered PostGIS aggregation shape, metric weights, date filtering, privacy, and no
  mutation behavior.
- Covered SQL guardrails for bbox filtering and meter-grid aggregation.
- Covered no Slice 11 migration/table guardrails.

Commands run:
- `python -m ruff check app/core/config.py app/schemas/heatmaps.py app/services/heatmaps.py app/api/v1/heatmaps.py tests/test_heatmaps.py`
- `python -m pytest tests/test_heatmaps.py -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest tests/test_heatmaps.py -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head; if ($LASTEXITCODE -eq 0) { python -m alembic current }`
- `python -m ruff check .`
- `python -m pytest -q`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest -q`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m ruff check .`
- `docker compose run --rm api python -m pytest -q`

Command results:
- Focused heatmap pytest without PostGIS: `4 passed, 3 skipped, 1 warning`.
- Focused heatmap pytest with PostGIS: `7 passed, 1 warning`.
- Alembic current with PostGIS: `0010_payouts_and_earnings (head)`.
- Host ruff: `All checks passed!`.
- Host pytest without PostGIS URL: `199 passed, 24 skipped, 1 warning`.
- Host pytest with PostGIS URL: `223 passed, 1 warning`.
- Docker Python: `Python 3.12.13`.
- Docker ruff: `All checks passed!`.
- Docker pytest: `223 passed, 1 warning`.
- The only warning is the existing Starlette TestClient/httpx deprecation warning.

Known issues:
- No known implementation blockers.
- Existing TestClient deprecation warning remains unrelated to Slice 11.

Out-of-scope compliance:
- No new tables.
- No new Alembic migration.
- No heatmap cache/materialized cells.
- No map tiles or vector tile endpoint.
- No route polyline or raw GPS export.
- No auto analytics, impression, payout, or ledger calculation.
- No background jobs, seed data, billing, settlement, withdrawals, retargeting, or
  frontend work.

Acceptance criteria checklist:
- No new database tables: yes.
- No new Alembic migration: yes.
- Existing Alembic head remains `0010_payouts_and_earnings`: yes.
- Advertiser can read own campaign heatmap: yes.
- Advertiser cannot read another organization's campaign heatmap: yes.
- Admin can read bounded aggregate heatmap: yes.
- Admin can filter by campaign and organization: yes.
- Admin can filter by vehicle type: yes.
- Bbox is required and validated: yes.
- Resolution, metric, date range, and request-size limits are validated: yes.
- PostGIS spatial filtering and meter-grid cell grouping are used: yes.
- Response is valid GeoJSON FeatureCollection: yes.
- Required metrics are supported: yes.
- Distance/impression allocation uses stored records and deterministic ping share: yes.
- Empty data returns a stable FeatureCollection with no features: yes.
- Endpoints are read-only and do not auto-run calculations: yes.
- Sensitive data is not exposed: yes.
- RBAC boundaries are enforced: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 Docker verification completed: yes.

Manual verification steps:
- Start local services with `docker compose up -d db redis`.
- Run Alembic against local PostGIS:
  `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head`
- Use bearer auth to call:
  `GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap?bbox=3.30,6.40,3.55,6.60&resolution_m=500&metric=estimated_impressions`
- Use admin bearer auth to call:
  `GET /api/v1/admin/heatmap?bbox=3.30,6.40,3.55,6.60&resolution_m=500`

Questions for Pro reviewer:
- Please confirm that using the latest stored current-formula impression estimate per
  trip is the preferred anti-double-counting rule for `estimated_impressions`.
- Please confirm that omitting optional `final_payout` is the right Slice 11 privacy
  and multi-currency tradeoff.
