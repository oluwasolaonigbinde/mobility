You are implementing Slice 7 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, Slice 5 campaign assignment/activation, and Slice 6 trip tracking/GPS ping ingestion have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 6 has been committed or that the working tree contains only the accepted Slice 6 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 7 goal:
Implement deterministic route analytics v1 and basic fraud/anomaly flags from completed trip/location ping data. This slice converts raw GPS pings into trip-level movement, quality, and campaign-zone overlap metrics, and records basic anomaly flags for suspicious or low-quality movement. Later slices will use these analytics for impression estimation, payout calculation, advertiser reporting, and heatmaps.

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
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 6 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing trip, location ping, campaign zone, campaign assignment, driver profile, vehicle, and audit patterns.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the existing standard error envelope and reuse it.
8. Confirm the current Alembic head is `0007_trip_tracking`.
9. Confirm no Slice 7 route analytics or fraud flag tables already exist.
10. Determine existing PostGIS geometry implementation patterns from Slice 4 and Slice 6 and reuse them where appropriate.
11. Determine current Postgres/PostGIS test strategy and preserve it.
12. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 7:

1. Trip analytics model, schema, service, and API support.
2. Fraud/anomaly flag model, schema, service, and API support.
3. Deterministic route analytics calculation from stored location pings.
4. Trip-level distance, duration, moving time, dwell/stationary time, ping count, ping quality, speed quality, and campaign-zone overlap metrics.
5. Basic anomaly/fraud flag generation from deterministic rules.
6. Admin endpoint to recompute analytics for an ended trip.
7. Admin endpoint to read analytics for a trip.
8. Admin endpoint to list fraud/anomaly flags.
9. Driver endpoint to read a simple analytics summary for one of their own trips.
10. Alembic migration for exactly the Slice 7 analytics and fraud tables, constraints, and indexes.
11. Tests for analytics calculation, PostGIS usage, zone overlap, anomaly flag generation, idempotent recompute behavior, RBAC, ownership boundaries, migration behavior, and out-of-scope guardrails.
12. README/OpenAPI documentation updates only where needed for Slice 7 usage.

DO NOT IMPLEMENT

- Impression estimation
- Traffic density profile tables
- Impression estimate tables
- Payout calculation
- Earnings ledger
- Advertiser dashboard/reporting APIs
- Heatmap APIs
- Campaign daily metrics
- Driver earnings APIs
- Billing/invoicing
- Settlement/payment APIs
- Advanced ML fraud detection
- External map matching
- External traffic provider integration
- Map tiles
- Mapbox integration
- Geocoding/reverse-geocoding
- Background jobs/Celery workers
- Automated analytics scheduling
- Seed/demo trip data
- Creative binary upload/storage pipeline
- Public self-registration
- OAuth/social login
- Refresh-token flow
- Frontend/mobile implementation
- GitHub remote/PR setup
- Production cloud deployment
- Retargeting
- Audience pooling
- AI/computer vision
- Real payment settlement

DATA MODEL REQUIREMENTS

Create a new Alembic migration after the Slice 6 migration.

Expected migration name:
`0008_route_analytics_and_fraud_flags`

Expected down revision:
`0007_trip_tracking`

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()`.

Use timezone-aware timestamps.

Use numeric/decimal columns where precision matters. Match existing project conventions for Decimal serialization.

Use either PostgreSQL enums or string columns with database check constraints. Match the existing repo style unless there is a strong local reason not to.

Create exactly these new business tables:

1. `trip_analytics`

Required columns:

- `id` UUID primary key
- `trip_session_id` UUID foreign key to `trip_sessions.id`, not null, unique
- `assignment_id` UUID foreign key to `campaign_assignments.id`, not null
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `vehicle_id` UUID foreign key to `vehicles.id`, not null
- `formula_version` text not null, default `route_analytics_v1`
- `status` constrained to:
  - `computed`
  - `insufficient_data`
  - `blocked`
- `ping_count` integer not null
- `valid_ping_count` integer not null
- `invalid_ping_count` integer not null
- `started_at` timezone-aware timestamp nullable
- `ended_at` timezone-aware timestamp nullable
- `first_ping_at` timezone-aware timestamp nullable
- `last_ping_at` timezone-aware timestamp nullable
- `duration_seconds` integer not null, default 0
- `active_tracking_seconds` integer not null, default 0
- `moving_seconds` integer not null, default 0
- `stationary_seconds` integer not null, default 0
- `distance_m` numeric not null, default 0
- `avg_speed_mps` numeric nullable
- `max_observed_speed_mps` numeric nullable
- `avg_accuracy_m` numeric nullable
- `poor_accuracy_ping_count` integer not null, default 0
- `target_zone_distance_m` numeric not null, default 0
- `bonus_zone_distance_m` numeric not null, default 0
- `exclusion_zone_distance_m` numeric not null, default 0
- `target_zone_seconds` integer not null, default 0
- `bonus_zone_seconds` integer not null, default 0
- `exclusion_zone_seconds` integer not null, default 0
- `quality_score` numeric not null
- `computed_at` timezone-aware timestamp not null
- `metadata` JSON/JSONB not null, default empty object
- `created_at` timezone-aware timestamp not null
- `updated_at` timezone-aware timestamp not null

Rules:

- Exactly one current analytics row per trip is acceptable for v1.
- Recomputing analytics for a trip should update the existing row rather than create duplicate rows.
- Analytics may be computed only for ended trips.
- Trips with too few valid pings should produce `status = insufficient_data` and deterministic zero/low metrics rather than server errors.
- Store formula version as `route_analytics_v1`.
- Store campaign/assignment/driver/vehicle foreign keys copied from the trip for efficient later reporting.
- Do not compute impressions or payouts in this table.
- `metadata` must be an object when supplied or generated.

Suggested constraints/indexes:

- Unique constraint or unique index on `trip_session_id`.
- Index on `campaign_id`.
- Index on `assignment_id`.
- Index on `driver_profile_id`.
- Index on `vehicle_id`.
- Index on `(campaign_id, computed_at)`.
- Index on `(driver_profile_id, computed_at)`.
- Check constraints for nonnegative counts, durations, distances, and zone seconds/distances.
- Check constraint for `quality_score` between 0 and 1 if cleanly supported.

2. `fraud_flags`

Required columns:

- `id` UUID primary key
- `trip_session_id` UUID foreign key to `trip_sessions.id`, not null
- `trip_analytics_id` UUID foreign key to `trip_analytics.id`, nullable
- `assignment_id` UUID foreign key to `campaign_assignments.id`, not null
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `vehicle_id` UUID foreign key to `vehicles.id`, not null
- `flag_type` constrained to:
  - `insufficient_pings`
  - `impossible_speed`
  - `poor_accuracy`
  - `stationary_trip`
  - `excessive_ping_gap`
  - `future_timestamp`
  - `route_looping`
  - `exclusion_zone_presence`
- `severity` constrained to:
  - `low`
  - `medium`
  - `high`
- `status` constrained to:
  - `open`
  - `acknowledged`
  - `dismissed`
- `description` text not null
- `evidence` JSON/JSONB not null, default empty object
- `detected_at` timezone-aware timestamp not null
- `created_at` timezone-aware timestamp not null
- `updated_at` timezone-aware timestamp not null

Rules:

- Fraud flags are deterministic rule outputs, not ML.
- On recompute, replace prior open flags for the trip generated by v1 rules, or otherwise make recompute idempotent so duplicate flags are not created.
- Store evidence as structured JSON, such as max speed, poor accuracy ratio, ping gap seconds, stationary ratio, or exclusion-zone metrics.
- Do not implement manual review workflow beyond status storage and listing.
- Do not add automated driver penalties, payout blocks, account suspensions, or notifications in this slice.

Suggested constraints/indexes:

- Index on `trip_session_id`.
- Index on `trip_analytics_id`.
- Index on `campaign_id`.
- Index on `driver_profile_id`.
- Index on `flag_type`.
- Index on `severity`.
- Index on `status`.
- Index on `(campaign_id, status)`.
- Optional idempotency unique index on `(trip_session_id, flag_type)` where status = `open`, if it fits existing migration style.

Do not create traffic density, impression, payout, earnings, reporting, heatmap, ledger, or seed tables.

CONFIGURATION REQUIREMENTS

Extend existing settings only as needed.

Add settings such as:

- `ROUTE_ANALYTICS_FORMULA_VERSION`, default `route_analytics_v1`
- `ROUTE_ANALYTICS_MIN_VALID_PINGS`, default `2`
- `ROUTE_ANALYTICS_MOVING_SPEED_MPS`, default `1.0`
- `ROUTE_ANALYTICS_STATIONARY_SPEED_MPS`, default `0.5`
- `ROUTE_ANALYTICS_IMPOSSIBLE_SPEED_MPS`, default `55`
- `ROUTE_ANALYTICS_MAX_PING_GAP_SECONDS`, default `900`
- `ROUTE_ANALYTICS_POOR_ACCURACY_THRESHOLD_M`, default existing `MAX_LOCATION_ACCURACY_M` or a lower analytics value such as `100`
- `ROUTE_ANALYTICS_POOR_ACCURACY_RATIO_THRESHOLD`, default `0.5`
- `ROUTE_ANALYTICS_STATIONARY_RATIO_THRESHOLD`, default `0.8`
- `ROUTE_ANALYTICS_LOOPING_RADIUS_M`, default `50`
- `ROUTE_ANALYTICS_LOOPING_MIN_DISTANCE_M`, default `1000`

Update `.env.example` and Docker Compose only if needed.

Validate settings for positive numeric values and ratios between 0 and 1 where applicable.

ANALYTICS CALCULATION REQUIREMENTS

Analytics must be deterministic and transparent.

Use stored `location_pings` ordered by `recorded_at`, then `sequence_number`, then `created_at`/`id` as a stable tie-breaker.

High-level calculation rules:

1. Only ended trips can be analyzed.
2. Load pings for the trip ordered deterministically.
3. Treat pings as valid for analytics if they have valid stored lat/lon and are inside acceptable configured bounds. Slice 6 should already prevent invalid rows, but do not assume corrupted data is impossible.
4. If valid ping count is below `ROUTE_ANALYTICS_MIN_VALID_PINGS`:
   - create/update analytics row with `status = insufficient_data`
   - set distances and moving/stationary seconds to 0
   - create an `insufficient_pings` fraud flag
5. Compute `duration_seconds` from trip `started_at` to `ended_at` when both exist.
6. Compute `active_tracking_seconds` from first to last valid ping.
7. For each consecutive valid ping pair:
   - calculate segment time delta in seconds.
   - ignore negative or zero time deltas for distance/time accumulation, but count or note them in metadata if useful.
   - calculate segment distance using PostGIS geography-safe distance, preferably `ST_Distance(point1::geography, point2::geography)`, or a database-backed equivalent.
   - calculate observed speed as `distance_m / delta_seconds`.
   - accumulate distance.
   - classify segment as moving if speed is at or above `ROUTE_ANALYTICS_MOVING_SPEED_MPS`.
   - classify segment as stationary if speed is below `ROUTE_ANALYTICS_STATIONARY_SPEED_MPS`.
   - for speeds between stationary and moving thresholds, choose a documented deterministic classification.
8. Compute average and maximum observed speed.
9. Compute average accuracy and poor accuracy count.
10. Compute zone overlap metrics:
   - Use campaign zones attached to the trip campaign.
   - For each segment, determine whether the segment intersects target, bonus, or exclusion zones.
   - Approximate zone distance by assigning the whole segment distance to a zone type when the segment line intersects that zone type.
   - Approximate zone seconds by assigning the whole segment delta to a zone type when the segment line intersects that zone type.
   - This approximation is acceptable for v1; do not implement precise clipped segment lengths unless straightforward.
   - Use PostGIS line/zone intersection for authoritative checks.
11. Compute quality score as a deterministic 0..1 value.
12. Suggested quality score v1:
   - Start at 1.0.
   - Subtract up to 0.30 based on poor accuracy ratio.
   - Subtract up to 0.25 based on excessive ping gaps.
   - Subtract up to 0.25 if impossible speeds are observed.
   - Subtract up to 0.20 if stationary ratio exceeds threshold.
   - Clamp to [0, 1].
13. Store enough metadata to explain the computation:
   - formula version
   - poor accuracy ratio
   - stationary ratio
   - excessive gap count
   - impossible speed count
   - ignored segment count
   - zone approximation method

Do not implement map matching, road-category weighting, traffic density, impressions, or payout logic in Slice 7.

FRAUD/ANOMALY FLAG RULES

Generate deterministic flags during analytics recompute.

Required v1 rules:

1. `insufficient_pings`
   - Trigger when valid ping count is below `ROUTE_ANALYTICS_MIN_VALID_PINGS`.
   - Severity: `medium`.

2. `impossible_speed`
   - Trigger when any segment speed exceeds `ROUTE_ANALYTICS_IMPOSSIBLE_SPEED_MPS`.
   - Severity: `high`.
   - Evidence should include maximum observed speed and count of offending segments.

3. `poor_accuracy`
   - Trigger when poor accuracy ratio exceeds `ROUTE_ANALYTICS_POOR_ACCURACY_RATIO_THRESHOLD`.
   - Severity: `medium`.
   - Evidence should include poor accuracy ratio and poor accuracy ping count.

4. `stationary_trip`
   - Trigger when stationary ratio exceeds `ROUTE_ANALYTICS_STATIONARY_RATIO_THRESHOLD`.
   - Severity: `low` or `medium`; choose and document one.
   - Evidence should include stationary seconds and ratio.

5. `excessive_ping_gap`
   - Trigger when any consecutive ping gap exceeds `ROUTE_ANALYTICS_MAX_PING_GAP_SECONDS`.
   - Severity: `medium`.
   - Evidence should include max gap and count.

6. `future_timestamp`
   - Trigger if stored pings are found with `recorded_at` materially after computation time plus configured Slice 6 future skew.
   - Severity: `medium`.
   - This should be rare because Slice 6 validates pings, but the analytics layer should still detect corrupted/imported data.

7. `route_looping`
   - Basic deterministic v1 rule:
     - Trigger when total distance exceeds `ROUTE_ANALYTICS_LOOPING_MIN_DISTANCE_M` and first/last ping are within `ROUTE_ANALYTICS_LOOPING_RADIUS_M`, with limited displacement relative to total distance.
   - Severity: `low`.
   - Evidence should include start/end distance and total distance.

8. `exclusion_zone_presence`
   - Trigger when exclusion zone distance or seconds are greater than zero.
   - Severity: `medium`.
   - Evidence should include exclusion distance and seconds.

Do not implement ML fraud scoring, driver suspension, payout blocking, automated enforcement, or alerts.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

1. `POST /api/v1/admin/trips/{trip_id}/recompute-analytics`

Admin-only.

Input body optional. If body is implemented, keep it minimal:

```json
{
  "metadata": {}
}

Output: trip analytics response, including generated fraud flags if straightforward.

Rules:

Admin-only.

Trip must exist.

Trip must be ended.

Recompute must be idempotent:

update existing trip_analytics row for the trip

avoid duplicate open fraud flags for the same trip/rule

Use server-side computation time.

Do not compute impressions or payouts.

Do not mutate the trip or assignment lifecycle.

GET /api/v1/admin/trips/{trip_id}/analytics

Admin-only.

Output: trip analytics and fraud flags if analytics exists.

Rules:

Admin-only.

Trip must exist.

If analytics has not been computed, return a clear 404/domain error using the standard error envelope.

Do not expose password hashes.

GET /api/v1/admin/fraud-flags

Admin-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

optional severity

optional flag_type

optional campaign_id

optional driver_profile_id

optional trip_session_id

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

Admin can list flags across trips/campaigns/drivers.

Include compact trip/campaign/driver/vehicle identifiers if straightforward.

Do not implement manual status update endpoints yet unless already trivial; listing is enough for Slice 7.

GET /api/v1/driver/trips/{trip_id}/analytics-summary

Driver-only.

Output: simple analytics summary for the current driver’s own trip.

Rules:

Driver-only.

Trip must belong to current driver profile.

Cross-driver reads must not leak data. Prefer non-leaking 404.

If analytics has not been computed, return a clear 404/domain error or { "analytics": null } if that is the existing project convention. Prefer a clear standard error if prior slice read endpoints use errors.

Return summary metrics useful to the driver:

trip id

status

distance_m

duration_seconds

moving_seconds

stationary_seconds

quality_score

fraud flag count by severity or a simple has_flags

Do not return admin-only fraud evidence details to drivers unless intentionally simple and non-sensitive.

RESPONSE SHAPE GUIDANCE

Trip analytics admin response should include at minimum:

JSON
{
  "id": "uuid",
  "trip_session_id": "uuid",
  "assignment_id": "uuid",
  "campaign_id": "uuid",
  "driver_profile_id": "uuid",
  "vehicle_id": "uuid",
  "formula_version": "route_analytics_v1",
  "status": "computed",
  "ping_count": 120,
  "valid_ping_count": 120,
  "invalid_ping_count": 0,
  "started_at": "2026-05-31T12:00:00Z",
  "ended_at": "2026-05-31T12:30:00Z",
  "first_ping_at": "2026-05-31T12:00:05Z",
  "last_ping_at": "2026-05-31T12:29:55Z",
  "duration_seconds": 1800,
  "active_tracking_seconds": 1790,
  "moving_seconds": 1500,
  "stationary_seconds": 290,
  "distance_m": "8500.25",
  "avg_speed_mps": "5.67",
  "max_observed_speed_mps": "18.20",
  "avg_accuracy_m": "14.30",
  "poor_accuracy_ping_count": 2,
  "target_zone_distance_m": "5300.00",
  "bonus_zone_distance_m": "1000.00",
  "exclusion_zone_distance_m": "0.00",
  "target_zone_seconds": 980,
  "bonus_zone_seconds": 200,
  "exclusion_zone_seconds": 0,
  "quality_score": "0.95",
  "computed_at": "2026-05-31T12:35:00Z",
  "metadata": {},
  "fraud_flags": []
}

Fraud flag response should include at minimum:

JSON
{
  "id": "uuid",
  "trip_session_id": "uuid",
  "trip_analytics_id": "uuid",
  "campaign_id": "uuid",
  "driver_profile_id": "uuid",
  "vehicle_id": "uuid",
  "flag_type": "impossible_speed",
  "severity": "high",
  "status": "open",
  "description": "Observed speed exceeded configured threshold.",
  "evidence": {
    "max_observed_speed_mps": 85.2,
    "offending_segment_count": 1
  },
  "detected_at": "2026-05-31T12:35:00Z",
  "created_at": "2026-05-31T12:35:00Z",
  "updated_at": "2026-05-31T12:35:00Z"
}

Driver analytics summary response should include at minimum:

JSON
{
  "trip_id": "uuid",
  "analytics_status": "computed",
  "distance_m": "8500.25",
  "duration_seconds": 1800,
  "moving_seconds": 1500,
  "stationary_seconds": 290,
  "quality_score": "0.95",
  "has_flags": false,
  "flag_counts": {
    "low": 0,
    "medium": 0,
    "high": 0
  }
}

For Decimal values, use the existing project convention. If no convention exists, return Decimal values as strings to avoid JSON float precision ambiguity.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 6 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/trip_analytics.py or similar

app/models/trip_analytics.py

app/models/fraud_flag.py or combined analytics model file

app/models/__init__.py

app/schemas/trip_analytics.py

app/schemas/fraud_flags.py or combined analytics schemas

app/services/trip_analytics.py

app/services/fraud_flags.py or combined analytics service if simpler

app/core/config.py

app/api/v1/dependencies.py only if needed to reuse admin/driver helpers

app/db/base.py only if model imports require update

alembic/versions/0008_route_analytics_and_fraud_flags.py

.env.example

README.md

tests/test_trip_analytics.py

tests/test_fraud_flags.py

tests/test_migration_slice7.py

Possibly fixture updates in tests/conftest.py

docs/build-loop/reports/slice-07-route-analytics-fraud.md

Keep code simple. Avoid unnecessary abstractions.

POSTGIS IMPLEMENTATION GUIDANCE

Use PostGIS for authoritative spatial calculations.

Recommended approaches:

Segment distance:

Use ST_Distance(p1.geom::geography, p2.geom::geography) or equivalent.

Do not calculate distance using naive degree math.

Segment zone intersection:

Build segment lines using ST_MakeLine(point1.geom, point2.geom) with SRID 4326.

Use ST_Intersects(segment_line, campaign_zones.geom) for target/bonus/exclusion checks.

For v1, whole-segment attribution on intersection is acceptable and must be documented in metadata.

Looping detection:

Use PostGIS geography distance between first and last valid point.

Do not generate route polylines or store route geometries in Slice 7 unless absolutely necessary. The approved Slice 7 persistence is trip analytics plus fraud flags.

TEST REQUIREMENTS

Add/extend tests for:

Analytics computation:

Admin can recompute analytics for an ended trip with valid pings.

Recompute creates a trip_analytics row.

Recompute updates existing analytics row instead of creating duplicates.

Analytics cannot be computed for an active trip.

Trip with too few valid pings produces insufficient_data.

Insufficient data produces an insufficient_pings fraud flag.

Distance is computed using PostGIS/geography behavior, not naive degree math.

Duration and active tracking seconds are computed correctly.

Moving and stationary seconds are computed deterministically.

Average speed and max observed speed are computed.

Average accuracy and poor accuracy ping count are computed.

Quality score is clamped between 0 and 1.

Analytics metadata records formula version and approximation notes.

Analytics stores campaign, assignment, driver profile, and vehicle ids from the trip.

Campaign zone overlap:

Target zone segment intersection contributes to target zone distance/seconds.

Bonus zone segment intersection contributes to bonus zone distance/seconds.

Exclusion zone segment intersection contributes to exclusion zone distance/seconds.

A trip outside campaign zones has zero zone distance/seconds.

Exclusion zone presence creates an exclusion_zone_presence fraud flag.

Fraud/anomaly flags:

Impossible speed creates a high-severity impossible_speed flag.

Poor accuracy ratio creates a poor_accuracy flag.

Excessive ping gap creates an excessive_ping_gap flag.

Stationary trip creates a stationary_trip flag.

Future timestamp creates a future_timestamp flag when corrupted/imported data is present.

Route looping creates a route_looping flag under the configured v1 rule.

Recompute does not duplicate open flags for the same trip/rule.

Fraud flag evidence contains useful structured values.

API/RBAC/access control:

Admin can read trip analytics after recompute.

Admin gets clear standard error when analytics does not exist.

Admin can list fraud flags with pagination response shape.

Admin can filter fraud flags by status.

Admin can filter fraud flags by severity.

Admin can filter fraud flags by flag type.

Admin can filter fraud flags by campaign id.

Driver can read own trip analytics summary.

Driver cannot read another driver’s analytics summary; prefer non-leaking 404.

Driver receives a clear response when analytics is missing.

Admin is rejected from driver analytics-summary endpoint.

Advertiser is rejected from admin analytics/fraud endpoints.

Advertiser is rejected from driver analytics-summary endpoint.

Unauthenticated users are rejected from all Slice 7 endpoints.

API responses do not expose password hashes.

Migration and scope:

Alembic migration creates exactly trip_analytics and fraud_flags as new Slice 7 tables.

Migration creates unique constraint/index on trip_analytics.trip_session_id.

Migration creates expected indexes on campaign, driver, vehicle, status, severity, and flag type.

Migration does not create impression, traffic density, payout, earnings, reporting, heatmap, ledger, or seed tables.

Existing Slice 0-Slice 6 tests continue to pass.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

This slice depends on PostGIS distance and intersection. Do not fake all geospatial behavior with JSON-only tests.

It is acceptable to run analytics/zone-overlap tests against a real PostgreSQL/PostGIS test database if SQLite cannot support geometry behavior.

If the existing default test suite uses SQLite for speed, update the test strategy carefully so python -m pytest still passes and PostGIS-specific tests are either:

run against a configured Postgres/PostGIS test database, or

explicitly skipped only when PostGIS is unavailable, while Docker-based pytest must run them.

Migration verification against Postgres/PostGIS is required.

Keep tests deterministic.

Do not require external network access.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in prior slices:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

Postgres/PostGIS migration and analytics verification is required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Admin tools can use:

http
POST /api/v1/admin/trips/{trip_id}/recompute-analytics
GET  /api/v1/admin/trips/{trip_id}/analytics
GET  /api/v1/admin/fraud-flags

Driver app can use:

http
GET /api/v1/driver/trips/{trip_id}/analytics-summary

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

Route analytics exists after this slice, but impression estimation, payout calculation, advertiser reporting, and heatmap aggregation do not. Frontend must not expect estimated impressions, driver earnings, advertiser dashboard summaries, or heatmap cells yet.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 6 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Trip not found

Trip belongs to another driver

Trip is not ended

Analytics not found

Insufficient pings

Invalid metadata

Invalid pagination/filter values

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 7 is acceptable only if:

Alembic migration creates exactly the approved trip_analytics and fraud_flags tables, constraints, and indexes.

No Slice 8+ impression/payout/report/heatmap/ledger/seed tables are added.

Admin can recompute analytics for ended trips.

Analytics recompute is idempotent and does not duplicate analytics rows or open fraud flags.

Analytics calculation uses stored location pings and PostGIS/geography-safe distance behavior.

Analytics includes distance, duration, active tracking seconds, moving seconds, stationary seconds, speed metrics, accuracy metrics, campaign-zone distance/seconds, and quality score.

Analytics handles insufficient data deterministically.

Campaign zone overlap uses existing campaign zones and PostGIS intersection checks.

Basic fraud/anomaly flags are generated for insufficient pings, impossible speed, poor accuracy, stationary trip, excessive ping gaps, future timestamps, route looping, and exclusion zone presence.

Admin can read analytics and list fraud flags.

Driver can read only their own trip analytics summary.

Admin/driver/advertiser/unauthenticated access boundaries are enforced.

API responses do not expose password hashes or unrelated sensitive data.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 6 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support analytics/fraud tables without reworking previous slices.

The test infrastructure cannot support meaningful PostGIS-backed distance/intersection verification.

Existing trip or location ping models make route analytics ambiguous in a way that requires a product decision.

Existing campaign zone geometry behavior cannot support zone intersection without reworking Slice 4.

You are tempted to add impression estimation, payouts, earnings ledger, reports, heatmaps, map tiles, external map providers, background jobs, or seed/demo data.

Otherwise, stop after Slice 7. Do not continue to Slice 8.

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
Route analytics calculation approach:
Fraud/anomaly flag approach:
PostGIS distance/intersection approach:
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
Route analytics calculation implemented:
Fraud/anomaly flags implemented:
PostGIS distance/intersection implemented:
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
Route analytics calculation implemented:
Fraud/anomaly flags implemented:
PostGIS distance/intersection implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED