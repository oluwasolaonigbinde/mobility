PASS

Safe to commit: Yes. Commit Slice 10 before starting Slice 11.

Codex questions resolved:

The current-state campaign and assignment status counts are acceptable for Slice 10 because the schema does not yet have campaign or assignment status-history tables. Keep that behavior documented as “current-state counts,” while trip, analytics, impression, payout, and fraud metrics continue to use the documented date fields.

The bundled report’s compact summary field may remain campaign metadata plus separate aggregate sections. Do not duplicate the full campaign-summary response inside the bundled report unless frontend requirements later prove that duplication useful.

Basis: Slice 10 added the approved read-only advertiser reporting endpoints, introduced no migration or new tables, preserved Alembic head 0010_payouts_and_earnings, aggregates stored Slice 0–9 data only, enforces advertiser org scoping and privacy boundaries, rejects admin/driver/unauthenticated access, and passed host/PostGIS/Docker pytest, ruff, Alembic, and Python 3.12 Docker verification. 

Pasted text

Recommended commit message:

feat: add advertiser dashboard and campaign reporting APIs

Full Slice 11 implementation prompt:

You are implementing Slice 11 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, Slice 5 campaign assignment/activation, Slice 6 trip tracking/GPS ping ingestion, Slice 7 route analytics/fraud flags, Slice 8 impression estimation, Slice 9 payout calculations/driver earnings ledger, and Slice 10 advertiser dashboard/reporting APIs have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 10 has been committed or that the working tree contains only the accepted Slice 10 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 11 goal:
Implement bounded heatmap/geospatial aggregation APIs using existing stored location pings, trip sessions, route analytics, impression estimates, and payout calculations. This slice should let the future advertiser dashboard render campaign map heatmaps and let admin tools inspect aggregate geospatial activity. It must not introduce map tiles, heatmap cache tables, raw GPS exports, route polyline export, background jobs, or new analytics calculations.

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
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 10 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing campaign, campaign zone, trip session, location ping, trip analytics, impression estimate, payout calculation, and advertiser organization service patterns.
6. Inspect existing Slice 10 reporting service logic and privacy conventions.
7. Confirm the existing API prefix is `/api/v1`.
8. Confirm the existing standard error envelope and reuse it.
9. Confirm the current Alembic head is `0010_payouts_and_earnings`.
10. Confirm no Slice 11 heatmap or heatmap cache table already exists.
11. Determine current PostGIS geometry implementation patterns from Slice 4 and Slice 6 and reuse them.
12. Determine existing Postgres/PostGIS test strategy and preserve it.
13. Determine existing Decimal serialization conventions and reuse them.
14. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 11:

1. Advertiser campaign heatmap API.
2. Admin heatmap API.
3. Heatmap request/query schemas.
4. Heatmap GeoJSON response schemas.
5. Read-only heatmap/geospatial aggregation service logic.
6. Bounded PostGIS grid aggregation over existing stored location pings.
7. Metric aggregation from existing stored records only:
   - `location_pings`
   - `trip_sessions`
   - `trip_analytics`
   - `impression_estimates`
   - `payout_calculations`, only if useful for admin or internal aggregate properties
   - `campaigns`
   - `campaign_assignments`
   - `vehicles`, only for non-sensitive aggregate filtering/properties such as vehicle type where useful
8. Advertiser org scoping for campaign heatmaps.
9. Admin global heatmap filtering by campaign, organization, and date range.
10. Tests for PostGIS aggregation, GeoJSON response shape, bbox/resolution/date validation, advertiser scoping, admin filters, privacy boundaries, zero states, no mutation/no auto-calculation behavior, migration guardrails, and out-of-scope guardrails.
11. README/OpenAPI documentation updates only where needed for Slice 11 usage.

IMPORTANT DATA MODEL DECISION

Do not create new heatmap, geospatial aggregation, or cache tables in Slice 11.

For MVP, use on-demand bounded PostGIS aggregation over existing stored location pings and stored analytics/estimate/payout records. This avoids premature materialized heatmap infrastructure before frontend usage patterns and traffic volume are known.

No new Alembic migration is expected for Slice 11.

If you discover a local technical reason that a new table or migration is required, stop and report the reason instead of adding it.

DO NOT IMPLEMENT

- New database tables
- New Alembic migration
- Heatmap cache table
- Materialized heatmap cells
- Map tiles
- Tile server
- Vector tile endpoint
- Mapbox integration
- Frontend map implementation
- Route polyline generation/export
- Raw GPS ping export
- Raw trip coordinate export
- Driver route playback
- New route analytics calculations
- New zone-overlap analytics calculations
- New impression estimation calculations
- New payout calculations
- Campaign daily metrics materialization
- Background jobs/Celery workers
- Scheduled heatmap rollups
- WebSockets or realtime heatmap streaming
- PDF/CSV export
- Billing/invoicing
- Advertiser charging
- Settlement/payment APIs
- Withdrawal/cash-out APIs
- Tax handling
- Manual fraud review workflow
- Notifications
- Seed/demo data
- External traffic provider integrations
- External map matching
- Geocoding/reverse-geocoding
- Audience identity, retargeting, or device pooling
- Creative binary upload/storage pipeline
- Public self-registration
- OAuth/social login
- Refresh-token flow
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- AI/computer vision

HEATMAP PRINCIPLES

1. Heatmap endpoints are read-only.
2. Heatmap endpoints aggregate existing stored records only.
3. Heatmap endpoints must not auto-run route analytics, impression estimation, or payout calculation.
4. Heatmap endpoints must not mutate campaigns, assignments, trips, pings, analytics, impressions, payouts, ledger entries, fraud flags, creatives, or zones.
5. Heatmap endpoints must require a bounded `bbox`.
6. Heatmap endpoints must clamp or reject excessive resolution/cell sizes and excessive bbox/date ranges.
7. Heatmap endpoints must return aggregate cells, not raw location pings.
8. Advertiser campaign heatmaps must be strictly tenant-scoped.
9. Advertiser campaign heatmaps must show only data for campaigns in the current advertiser organization.
10. Cross-organization campaign access must not leak data. Prefer non-leaking 404.
11. Admin heatmap may aggregate across organizations but must be bounded by bbox and optional filters.
12. Heatmap responses must not expose:
    - driver user id
    - driver full name
    - driver email
    - driver phone
    - driver license number
    - driver profile id
    - vehicle plate number
    - raw GPS coordinate rows
    - idempotency keys
    - raw ping ids
    - ledger entry ids/details
    - payment account data
    - internal audit events
    - password hashes
13. Heatmap responses may expose aggregate or opaque operational identifiers only where necessary:
    - campaign id in advertiser campaign-specific endpoint
    - metric name
    - aggregate cell properties
    - aggregate counts/totals
14. Use the existing standard error envelope for expected errors.

POSTGIS GRID APPROACH

Use PostGIS for authoritative spatial filtering and grid aggregation.

Recommended approach:

1. Parse required `bbox` as:
   - `min_lon,min_lat,max_lon,max_lat`
2. Validate:
   - longitudes in `[-180, 180]`
   - latitudes in `[-90, 90]`
   - `min_lon < max_lon`
   - `min_lat < max_lat`
   - finite numeric values
3. Create bbox geometry:
   - `ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)`
4. Filter pings using bbox:
   - `location_pings.geom && bbox`
   - `ST_Intersects(location_pings.geom, bbox)`
5. Use a meter-based grid for cells:
   - Transform ping point to EPSG:3857.
   - Calculate grid x/y using `floor(ST_X(transformed_geom) / resolution_m) * resolution_m` and same for y.
   - Build a cell polygon with `ST_MakeEnvelope(x, y, x + resolution_m, y + resolution_m, 3857)`.
   - Transform the cell polygon back to SRID 4326 for GeoJSON response.
6. Return cell geometry using `ST_AsGeoJSON`.
7. Use `location_pings.recorded_at` for date filtering.
8. Do not return raw point geometries.
9. Do not generate route lines or route polylines.

If the existing project already has a simpler, well-tested PostGIS grid helper, reuse it. If using `ST_SnapToGrid` instead, document the approximation and ensure `resolution_m` semantics remain clear.

HEATMAP METRICS

Support the following `metric` values:

1. `ping_count`
   - Primary weight is number of pings in the cell.

2. `trip_count`
   - Primary weight is distinct trip count in the cell.

3. `distance_m`
   - Primary weight is estimated distance attributed to the cell.
   - Use stored `trip_analytics.distance_m`.
   - MVP allocation rule:
     - For each trip, allocate the trip’s stored distance across cells in proportion to that trip’s ping count in each cell within the requested bbox/date window.
   - Store/report this as an approximation in response metadata.

4. `estimated_impressions`
   - Primary weight is estimated impressions attributed to the cell.
   - Use stored `impression_estimates.estimated_impressions`.
   - MVP allocation rule:
     - For each trip, allocate the trip’s stored estimated impressions across cells in proportion to that trip’s ping count in each cell within the requested bbox/date window.
   - Include only stored estimates. Do not generate estimates.

Optional if straightforward and privacy-safe:

5. `final_payout`
   - Primary weight is final payout attributed to the cell.
   - Use stored `payout_calculations.final_payout`.
   - Prefer admin endpoint only unless implementation can clearly keep advertiser campaign-level cost heatmap aggregate-safe.
   - MVP allocation rule:
     - Allocate stored final payout across cells in proportion to trip ping distribution.
   - Do not expose ledger entry details.

If optional `final_payout` complicates privacy or implementation, do not include it in Slice 11. Required metrics are `ping_count`, `trip_count`, `distance_m`, and `estimated_impressions`.

Every cell should include common properties:

```json
{
  "cell_id": "string-or-stable-id",
  "metric": "estimated_impressions",
  "weight": "123.45",
  "ping_count": 42,
  "trip_count": 3,
  "distance_m": "1000.00",
  "estimated_impressions": "250.00",
  "average_quality_score": "0.88"
}

Rules:

weight equals the selected metric value.

Decimal values should follow the existing project convention. If existing Decimal values serialize as strings, use strings.

Empty result should return a valid GeoJSON FeatureCollection with empty features.

CONFIGURATION REQUIREMENTS

Extend existing settings only as needed.

Add settings such as:

HEATMAP_DEFAULT_RESOLUTION_M, default 500

HEATMAP_MIN_RESOLUTION_M, default 50

HEATMAP_MAX_RESOLUTION_M, default 5000

HEATMAP_MAX_BBOX_AREA_SQ_KM, default 2500

HEATMAP_MAX_DATE_RANGE_DAYS, default 90

HEATMAP_MAX_CELLS, default 5000

HEATMAP_MIN_TRIPS_PER_CELL, default 1

Update .env.example and Docker Compose only if needed.

Validation:

Resolution values must be positive.

Min resolution must be less than or equal to default and max.

Max bbox area must be positive.

Max date range days must be positive.

Max cells must be positive.

Min trips per cell must be at least 1.

BBOX AND RESOLUTION VALIDATION

Required query parameters:

bbox

optional resolution_m

optional metric

optional start_at

optional end_at

Validation:

bbox is required.

bbox must have exactly four comma-separated numbers:

min_lon,min_lat,max_lon,max_lat

Reject invalid coordinate bounds.

Reject bbox with min_lon >= max_lon.

Reject bbox with min_lat >= max_lat.

Reject bbox area above HEATMAP_MAX_BBOX_AREA_SQ_KM.

Compute area with geography-safe PostGIS behavior or a safe approximate service check if PostGIS is unavailable during schema-only validation.

resolution_m, if omitted, defaults to HEATMAP_DEFAULT_RESOLUTION_M.

Reject or clamp resolution outside configured bounds. Prefer rejection with a clear standard error.

Estimate max cells from bbox area and resolution. Reject requests exceeding HEATMAP_MAX_CELLS.

metric, if omitted, defaults to ping_count.

Reject unsupported metrics.

start_at and end_at, if supplied, must be timezone-aware if that is the existing project convention.

If both dates are supplied, start_at <= end_at.

If date range exceeds HEATMAP_MAX_DATE_RANGE_DAYS, reject with a clear standard error.

Date filters apply to location_pings.recorded_at.

API ENDPOINTS

Implement these endpoints under /api/v1.

GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap

Advertiser-only.

Query parameters:

required bbox, format min_lon,min_lat,max_lon,max_lat

optional resolution_m, integer/meters

optional metric, one of:

ping_count

trip_count

distance_m

estimated_impressions

optional start_at

optional end_at

Example:

http
GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap?bbox=3.30,6.40,3.55,6.60&resolution_m=500&metric=estimated_impressions

Output:

JSON
{
  "type": "FeatureCollection",
  "metadata": {
    "campaign_id": "uuid",
    "metric": "estimated_impressions",
    "bbox": [3.30, 6.40, 3.55, 6.60],
    "resolution_m": 500,
    "start_at": null,
    "end_at": null,
    "generated_at": "2026-05-31T12:35:00Z",
    "aggregation_version": "heatmap_v1",
    "aggregation_method": "postgis_grid_ping_weighted",
    "distance_allocation": "trip_distance_allocated_by_ping_share",
    "impression_allocation": "trip_impressions_allocated_by_ping_share"
  },
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": []
      },
      "properties": {
        "cell_id": "string",
        "metric": "estimated_impressions",
        "weight": "250.00",
        "ping_count": 42,
        "trip_count": 3,
        "distance_m": "1000.00",
        "estimated_impressions": "250.00",
        "average_quality_score": "0.88"
      }
    }
  ]
}

Rules:

Campaign must belong to the current advertiser organization.

Cross-organization campaign access must not leak data. Prefer 404.

Aggregate only trips/pings tied to that campaign.

Return aggregate cells only.

Do not expose driver identities, vehicle plates, raw coordinates, raw pings, or ledger details.

Do not auto-generate analytics, estimates, or payouts.

Empty data returns a valid FeatureCollection with features: [].

GET /api/v1/admin/heatmap

Admin-only.

Query parameters:

required bbox, format min_lon,min_lat,max_lon,max_lat

optional resolution_m

optional metric, one of:

ping_count

trip_count

distance_m

estimated_impressions

optional final_payout only if implemented safely

optional start_at

optional end_at

optional campaign_id

optional organization_id

optional vehicle_type

Output shape:

Same GeoJSON FeatureCollection shape as advertiser endpoint, but metadata may include the applied admin filters.

Rules:

Admin-only.

Admin may aggregate across all campaigns when no campaign/organization filter is supplied, but bbox and max-cell/date limits still apply.

If campaign_id is supplied, filter to that campaign.

If organization_id is supplied, filter to campaigns in that organization.

If both campaign_id and organization_id are supplied, ensure the campaign belongs to the organization or return a clear standard error / empty data consistently. Prefer clear validation error for mismatched filters.

If vehicle_type is supplied, filter through the campaign assignment/vehicle relationship.

Return aggregate cells only.

Do not expose raw pings, driver PII, vehicle plates, ledger entry details, or payment data.

Do not auto-generate analytics, estimates, or payouts.

RESPONSE SHAPE REQUIREMENTS

Use valid GeoJSON FeatureCollection.

Top-level fields:

JSON
{
  "type": "FeatureCollection",
  "metadata": {},
  "features": []
}

Feature shape:

JSON
{
  "type": "Feature",
  "geometry": {
    "type": "Polygon",
    "coordinates": []
  },
  "properties": {}
}

Metadata should include:

metric

bbox

resolution_m

start_at

end_at

generated_at

aggregation_version, value heatmap_v1

aggregation_method

applied filters:

campaign_id where applicable

organization_id where applicable

vehicle_type where applicable

Properties should include:

cell_id

metric

weight

ping_count

trip_count

distance_m

estimated_impressions

average_quality_score

Optional if implemented:

final_payout

currency, only if aggregation has a single currency or is otherwise unambiguous

Avoid returning multi-currency payout heatmap values unless the representation is very clear. It is acceptable to omit final_payout in Slice 11.

SECURITY AND VALIDATION REQUIREMENTS

Advertiser campaign heatmap endpoint requires role advertiser.

Admin heatmap endpoint requires role admin.

Driver users must be rejected from all Slice 11 endpoints.

Admin users must be rejected from advertiser heatmap endpoint unless the existing project has an explicit accepted admin-on-advertiser route pattern. Prefer rejection.

Advertiser users must be rejected from admin heatmap endpoint.

Unauthenticated users must be rejected from all Slice 11 endpoints.

Advertiser users must see only campaigns in their own organization.

Cross-organization campaign heatmap access must return non-leaking 404 where practical.

Advertiser users without an active/invited organization membership should receive the existing advertiser organization error behavior.

Use existing standard error envelope for expected errors.

Do not introduce a new auth scheme.

Do not expose password hashes.

Do not expose raw pings.

Do not expose raw GPS coordinates as point data.

Do not expose driver PII.

Do not expose vehicle plate numbers.

Do not expose ledger entry details or payment account/settlement data.

Validate bbox, resolution, metric, date range, and admin filter combinations.

Reject unbounded or excessive requests.

Use deterministic error codes/messages consistent with existing style.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 10 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/heatmaps.py

app/schemas/heatmaps.py

app/services/heatmaps.py

app/core/config.py

.env.example

README.md

tests/test_heatmaps.py

tests/test_heatmap_privacy.py or combined heatmap tests

tests/test_migration_slice11.py or update existing migration guard tests to assert no new tables

Possibly fixture updates in tests/conftest.py

docs/build-loop/reports/slice-11-heatmaps.md

docs/build-loop/slice-log.md

Do not create or modify Alembic migration files unless stopped/reconciled and explicitly approved.

TEST REQUIREMENTS

Add/extend tests for:

Advertiser campaign heatmap:

Advertiser can read heatmap for own campaign.

Advertiser cannot read heatmap for another organization’s campaign.

Advertiser endpoint returns valid GeoJSON FeatureCollection.

Advertiser endpoint returns stable empty FeatureCollection when campaign has no pings.

Advertiser heatmap aggregates only pings/trips tied to the campaign.

Advertiser heatmap supports ping_count metric.

Advertiser heatmap supports trip_count metric.

Advertiser heatmap supports distance_m metric using stored analytics allocation.

Advertiser heatmap supports estimated_impressions metric using stored estimate allocation.

Advertiser heatmap applies start_at and end_at filters to ping recorded times.

Advertiser heatmap does not auto-create analytics, impression estimates, payout calculations, or ledger entries.

Advertiser heatmap does not expose driver PII, driver profile ids, vehicle plate numbers, raw pings, raw point coordinates, idempotency keys, ledger details, or payment data.

Admin heatmap:

Admin can read global heatmap with bbox.

Admin can filter heatmap by campaign id.

Admin can filter heatmap by organization id.

Admin can filter heatmap by vehicle type if implemented.

Admin campaign/organization mismatch is rejected or handled deterministically.

Admin heatmap returns valid GeoJSON FeatureCollection.

Admin heatmap does not expose driver PII, plate numbers, raw pings, ledger details, or payment data.

Grid/PostGIS aggregation:

Heatmap uses PostGIS bbox filtering.

Heatmap uses meter-based resolution to group cells.

Feature geometries are polygons, not raw points.

Cell properties include selected metric as weight.

Cell properties include ping count and trip count.

Distance and impression allocation are deterministic.

Average quality score is aggregated from stored trip analytics where present.

Empty cells are not returned unless local implementation intentionally returns them; prefer only non-empty cells.

Results are stable/deterministic for repeated identical requests.

Validation:

Missing bbox is rejected.

Malformed bbox is rejected.

Out-of-range longitude/latitude is rejected.

Reversed bbox is rejected.

Excessive bbox area is rejected.

Resolution below min is rejected.

Resolution above max is rejected.

Excessive estimated cell count is rejected.

Unsupported metric is rejected.

Invalid date range is rejected.

Date range beyond configured max is rejected.

Invalid admin filter UUIDs are rejected through existing validation behavior.

Invalid vehicle type filter is rejected if vehicle type filter is implemented.

RBAC:

Driver user is rejected from all Slice 11 endpoints.

Admin user is rejected from advertiser heatmap endpoint unless existing accepted pattern explicitly permits admin; prefer rejection.

Advertiser user is rejected from admin heatmap endpoint.

Unauthenticated user is rejected from all Slice 11 endpoints.

Standard error envelope is used for expected errors.

Migration/scope guardrails:

No new Alembic migration is added.

No new database tables are added.

Existing Alembic head remains 0010_payouts_and_earnings.

Existing Slice 0-Slice 10 tests continue to pass.

No map tile, heatmap cache, route polyline, raw GPS export, new analytics, new impressions, new payouts, seed, billing, settlement, withdrawal, background-job, audience, retargeting, or frontend scope is added.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

Reuse existing campaign, trip, ping, analytics, impression estimate, payout calculation, and advertiser organization fixtures where available.

This slice depends on PostGIS. Do not fake all geospatial behavior with JSON-only tests.

It is acceptable to run heatmap aggregation tests against a real PostgreSQL/PostGIS test database if SQLite cannot support the geometry behavior.

If the existing default test suite uses SQLite for speed, update the test strategy carefully so python -m pytest still passes and PostGIS-specific tests are either:

run against a configured Postgres/PostGIS test database, or

explicitly skipped only when PostGIS is unavailable, while Docker-based pytest must run them.

Migration verification against Postgres/PostGIS remains required.

Keep tests deterministic.

Do not require external network access.

Avoid making any heatmap endpoint perform automatic calculations.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Postgres/PostGIS migration and full-test verification is required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Advertiser campaign map can use:

http
GET /api/v1/advertiser/campaigns/{campaign_id}/heatmap

Admin tools can use:

http
GET /api/v1/admin/heatmap

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

The heatmap response is GeoJSON FeatureCollection.

Frontend should pass:

bbox

optional resolution_m

optional metric

optional start_at

optional end_at

Available required metrics:

ping_count

trip_count

distance_m

estimated_impressions

Heatmap values are aggregate approximations intended for visual dashboard rendering. They are not raw GPS exports and should not be treated as audited measurement or payout calculations.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 10 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Advertiser organization missing

Campaign not found

Campaign belongs to another organization

Missing bbox

Invalid bbox

Bbox too large

Invalid resolution

Too many heatmap cells

Invalid metric

Invalid date range

Date range too large

Invalid admin filter combination

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 11 is acceptable only if:

No new database tables are created.

No new Alembic migration is created.

Existing Alembic head remains 0010_payouts_and_earnings.

Advertiser can read own campaign heatmap.

Advertiser cannot read another organization’s campaign heatmap.

Admin can read bounded aggregate heatmap.

Admin can filter heatmap by campaign and organization.

Heatmap endpoints require and validate bbox.

Heatmap endpoints validate resolution, metric, date range, and max request size.

Heatmap aggregation uses PostGIS spatial filtering and grid cell grouping.

Heatmap response is valid GeoJSON FeatureCollection.

Heatmap cells include aggregate properties and selected metric weight.

Required metrics ping_count, trip_count, distance_m, and estimated_impressions are supported.

Distance and impression heatmap values use stored analytics/estimate records and deterministic ping-share allocation.

Heatmap endpoints return stable empty FeatureCollection when no data exists.

Heatmap endpoints aggregate stored data only and do not auto-run analytics, impression estimation, or payout calculation.

Heatmap endpoints do not expose driver PII, driver profile ids, vehicle plate numbers, raw GPS point rows, idempotency keys, ledger details, payment data, password hashes, or unrelated sensitive data.

Admin/advertiser/driver/unauthenticated access boundaries are enforced.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 10 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

Existing trip/location ping/analytics/impression models make heatmap aggregation ambiguous in a way that requires a product decision.

Existing advertiser campaign tenancy behavior makes heatmap scoping ambiguous in a way that requires a product decision.

Implementing Slice 11 would require a new heatmap/cache/materialized table.

Implementing Slice 11 would require returning raw GPS points or route polylines.

Implementing Slice 11 would require generating missing analytics, impression estimates, or payout calculations automatically.

You are tempted to add map tiles, frontend map code, seed/demo data, background jobs, billing, settlement, withdrawals, invoices, audience identity, or retargeting.

Otherwise, stop after Slice 11. Do not continue to Slice 12.

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
Heatmap aggregation approach:
PostGIS grid approach:
Metric allocation approach:
Privacy/sensitivity controls:
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
Heatmap aggregation implemented:
PostGIS grid implemented:
Metric allocation implemented:
Privacy/sensitivity controls implemented:
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
Heatmap aggregation implemented:
PostGIS grid implemented:
Metric allocation implemented:
Privacy/sensitivity controls implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED