PRO REVIEW PACKET

Slice:
Slice 7 - Route analytics v1 and fraud flags

Review request:
Please review this Slice 7 implementation for ship readiness. Respond with `PASS`, `FIX REQUIRED`, or `BLOCKED`. If this passes, please say it is safe to commit and provide a recommended commit message plus the full Slice 8 implementation prompt.

Repo state summary:
- Branch: `slice-07-route-analytics`
- Base accepted state: Slice 6 recorded at `bc904ae docs: record slice 6 commit`
- Slice 6 feature commit: `0e6d102 feat: add trip tracking and GPS ping ingestion`
- Current status: uncommitted Slice 7 PASS_CANDIDATE
- Current Alembic head after Slice 7: `0008_route_analytics_and_fraud_flags`
- API prefix remains `/api/v1`
- Fixed stack preserved: FastAPI, Pydantic v2, SQLAlchemy async, asyncpg, Alembic, PostgreSQL/PostGIS, Redis, JWT, pytest, ruff, Docker Compose.

Commit status:
- No Slice 7 commit has been created yet.
- Working tree contains only the Slice 7 implementation/report/ledger changes listed below.
- Intended commit only after Pro PASS and local reconciliation.

Approved Slice 7 prompt summary:
- Implement only deterministic route analytics v1 and basic fraud/anomaly flags from completed trip/location ping data.
- Add migration `0008_route_analytics_and_fraud_flags` after `0007_trip_tracking`.
- Create exactly two new business tables: `trip_analytics` and `fraud_flags`.
- Compute trip-level distance, duration, moving time, stationary time, ping quality, speed quality, campaign-zone distance/seconds, and quality score.
- Use PostGIS geography-safe distance and PostGIS segment/zone intersection checks.
- Add admin endpoints:
  - `POST /api/v1/admin/trips/{trip_id}/recompute-analytics`
  - `GET /api/v1/admin/trips/{trip_id}/analytics`
  - `GET /api/v1/admin/fraud-flags`
- Add driver endpoint:
  - `GET /api/v1/driver/trips/{trip_id}/analytics-summary`
- Generate deterministic v1 flags for insufficient pings, impossible speed, poor accuracy, stationary trip, excessive ping gap, future timestamp, route looping, and exclusion-zone presence.
- Do not implement impressions, payouts, earnings, advertiser reports, heatmaps, traffic density, map providers, background jobs, seed/demo data, frontend/mobile, or any later-slice scope.

Files changed:
- `.env.example`
- `README.md`
- `alembic/versions/0008_route_analytics_and_fraud_flags.py`
- `app/api/v1/router.py`
- `app/api/v1/trip_analytics.py`
- `app/core/config.py`
- `app/db/base.py`
- `app/models/trip_analytics.py`
- `app/schemas/trip_analytics.py`
- `app/services/trip_analytics.py`
- `docs/build-loop/reports/slice-07-route-analytics.md`
- `docs/build-loop/slice-log.md`
- `tests/test_config.py`
- `tests/test_migration_slice7.py`
- `tests/test_trip_analytics.py`

Diff summary:
- Adds route analytics and fraud flag ORM models with check constraints, metadata/evidence JSON, timestamps, copied trip foreign keys, unique analytics row per trip, and partial unique open flag index.
- Adds Slice 7 Alembic migration `0008_route_analytics_and_fraud_flags` after `0007_trip_tracking`.
- Adds a trip analytics router mounted under the existing `/api/v1` router.
- Adds admin recompute/read/list endpoints and driver own-trip summary endpoint.
- Adds service logic for ended-trip enforcement, ordered ping loading, PostGIS segment measurement, zone attribution, quality scoring, deterministic flag generation, idempotent recompute, admin reads, flag listing, and non-leaking driver ownership.
- Adds route analytics response schemas with Decimal-as-string serialization.
- Adds route analytics settings, env docs, README notes, migration guardrails, PostGIS-backed analytics tests, RBAC tests, and config validation tests.

Database migrations:
- New migration: `alembic/versions/0008_route_analytics_and_fraud_flags.py`
- Down revision: `0007_trip_tracking`
- Creates exactly two new Slice 7 business tables:
  - `trip_analytics`
  - `fraud_flags`
- `trip_analytics`:
  - UUID PK with `gen_random_uuid()`
  - FKs to `trip_sessions`, `campaign_assignments`, `campaigns`, `driver_profiles`, and `vehicles`
  - `formula_version` default `route_analytics_v1`
  - status constrained to `computed`, `insufficient_data`, `blocked`
  - ping counts, lifecycle timestamps, duration/time metrics, distance/speed/accuracy metrics, zone metrics, quality score, computed timestamp, metadata JSONB, created/updated timestamps
  - nonnegative check constraints for counts, durations, distances, and zone metrics
  - `quality_score` check constrained to 0..1
  - unique `trip_session_id`
  - indexes on campaign, assignment, driver profile, vehicle, `(campaign_id, computed_at)`, and `(driver_profile_id, computed_at)`
- `fraud_flags`:
  - UUID PK with `gen_random_uuid()`
  - FKs to `trip_sessions`, `trip_analytics`, `campaign_assignments`, `campaigns`, `driver_profiles`, and `vehicles`
  - `flag_type` constrained to the eight required v1 rule names
  - `severity` constrained to low/medium/high
  - `status` constrained to open/acknowledged/dismissed
  - description, evidence JSONB, detected/created/updated timestamps
  - indexes on trip, analytics, campaign, driver, vehicle, flag type, severity, status, and `(campaign_id, status)`
  - partial unique index `uq_fraud_flags_trip_open_flag_type` on `(trip_session_id, flag_type)` where `status = 'open'`
- Because the approved revision id `0008_route_analytics_and_fraud_flags` is longer than Alembic's default `alembic_version.version_num VARCHAR(32)`, the migration widens `alembic_version.version_num` to 64 before recording the revision. A DB-backed test creates a temporary Postgres/PostGIS database, runs `alembic upgrade head`, and verifies the stored revision, widened column length, expected tables, constraints, indexes, and partial unique predicate.
- Does not add traffic density, impression, payout, earnings, advertiser reporting, campaign daily metrics, heatmap, ledger, seed, map, or later-slice tables/columns.

Key code evidence:
- `app/services/trip_analytics.py` loads pings ordered by `recorded_at`, `sequence_number`, `created_at`, and `id`.
- `app/services/trip_analytics.py` rejects non-PostgreSQL analytics execution with `POSTGIS_REQUIRED`, because the Slice 7 calculation depends on PostGIS.
- Segment distance uses `ST_Distance(start_ping.geom::geography, end_ping.geom::geography)`.
- Zone overlap uses `EXISTS` per zone type with `ST_Intersects(ST_MakeLine(start_ping.geom, end_ping.geom), geom)`, preventing same-type zone overcounting.
- Loop detection uses PostGIS geography-safe start/end distance.
- Recompute updates an existing `TripAnalytics` row when present, instead of inserting duplicates.
- Recompute deletes prior open `FraudFlag` rows for the trip before creating deterministic v1 flags.
- Driver summary resolves the current driver profile and queries `TripSession` by both trip id and driver profile id before loading analytics.
- Decimal values in API responses serialize as strings.

Security/validation implemented:
- Admin endpoints use existing `AdminUserDependency`.
- Driver summary uses existing `DriverUserDependency`.
- Missing analytics returns standard `ANALYTICS_NOT_FOUND` error.
- Active/non-ended trip recompute returns standard `TRIP_NOT_ENDED` error.
- Missing/cross-driver trip summary returns non-leaking `TRIP_NOT_FOUND` 404.
- Advertisers are rejected from admin analytics read, admin recompute, admin fraud flag list, and driver summary.
- Admins are rejected from driver summary.
- Unauthenticated users are rejected from all four Slice 7 endpoints.
- API responses do not expose password hashes.

Route analytics calculation implemented:
- Uses stored pings only; no external map matching or provider calls.
- Defensively filters corrupted invalid coordinates.
- Computes:
  - ping count, valid/invalid ping count
  - first/last ping time
  - trip duration seconds
  - active tracking seconds
  - moving seconds
  - stationary seconds
  - total distance
  - average speed
  - max observed speed
  - average accuracy
  - poor accuracy count and ratio
  - target/bonus/exclusion zone distance and seconds
  - quality score clamped 0..1
- Insufficient valid pings produce deterministic `insufficient_data`, zero/low metrics, quality score `0.0000`, and an `insufficient_pings` flag.
- Metadata records formula version, ratios, counts, ignored segments, future ping count, whole-segment zone attribution, deterministic between-threshold speed classification, and request metadata.

Fraud/anomaly flags implemented:
- `insufficient_pings`, severity medium
- `impossible_speed`, severity high
- `poor_accuracy`, severity medium
- `stationary_trip`, severity medium
- `excessive_ping_gap`, severity medium
- `future_timestamp`, severity medium
- `route_looping`, severity low
- `exclusion_zone_presence`, severity medium
- Evidence includes configured thresholds and observed values such as max speed, offending segment count, poor accuracy ratio, stationary ratio, gap count, future ping count, start/end distance, total distance, and exclusion zone metrics.
- No ML scoring, driver suspension, payout blocking, manual review update endpoint, notifications, or automated enforcement was added.

PostGIS distance/intersection implemented:
- Segment distance: `ST_Distance(point1::geography, point2::geography)`.
- Segment line: `ST_MakeLine(start_ping.geom, end_ping.geom)`.
- Zone intersection: `ST_Intersects(segment_line, campaign_zones.geom)`.
- Whole-segment attribution is used for v1 and recorded in metadata.
- Same-type overlapping zones do not overcount because each zone type is attributed via `EXISTS`.

Tests/checks run:
- `python -m ruff check .`
- `python -m pytest tests/test_config.py tests/test_migration_slice7.py -q`
- `python -m alembic upgrade head` with Postgres/PostGIS `DATABASE_URL`
- `python -m alembic current` with Postgres/PostGIS `DATABASE_URL`
- `python -m pytest tests/test_trip_analytics.py tests/test_migration_slice7.py -q` with Postgres/PostGIS `DATABASE_URL`
- `python -m pytest`
- `python -m pytest` with Postgres/PostGIS `DATABASE_URL`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Exact command outputs or concise results:
- Host ruff:
  - `All checks passed!`
- Host targeted migration/config tests:
  - `python -m pytest tests/test_config.py tests/test_migration_slice7.py -q`
  - `35 passed, 1 skipped, 1 warning in 0.58s`
  - The skip is the DB-backed migration test when no PostGIS URL is configured.
- Host Alembic upgrade/current with `DATABASE_URL=postgresql+asyncpg://mobility:mobility@localhost:5433/mobility`:
  - upgrade passed
  - current: `0008_route_analytics_and_fraud_flags (head)`
- Host targeted PostGIS analytics/migration tests with same `DATABASE_URL`:
  - `11 passed, 1 warning in 47.29s`
- Host full tests without `DATABASE_URL`:
  - `128 passed, 19 skipped, 1 warning in 120.43s`
  - Skips are PostGIS-gated tests when no PostGIS URL is configured.
- Host full tests with same PostGIS `DATABASE_URL`:
  - `147 passed, 1 warning in 217.80s`
- Docker build:
  - image `mobility-api:latest` built successfully
- Docker Python:
  - `Python 3.12.13`
- Docker full tests:
  - `147 passed, 1 warning in 286.67s`
- Docker ruff:
  - `All checks passed!`

Audit/fix reconciliation:
- Clean planning auditor confirmed Slice 7 prompt and local repo evidence were safe to execute.
- Clean service/API auditor found no blocker-class issues in PostGIS distance, zone overlap, idempotent recompute, ORM constraints/indexes, driver ownership, route wiring, or out-of-scope application behavior.
- Clean migration/test/docs auditor found one Pro-review blocker: tests did not exercise the actual DB-backed Alembic upgrade path for the long revision id/version table widening.
- The same auditor found RBAC and out-of-scope guard coverage gaps.
- Clean fix worker added the DB-backed Alembic migration test, expanded RBAC/unauthenticated endpoint tests, and strengthened Slice 8+ table/field guardrails.
- Orchestrator reran full host/PostGIS/Docker verification after the fix pass.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.
- PostGIS-specific tests intentionally skip on host when no `DATABASE_URL` or `TEST_DATABASE_URL` is configured. They pass with a real PostGIS URL and in Docker.
- The migration widens `alembic_version.version_num` to support the approved long revision id. It does not narrow this internal Alembic bookkeeping column on downgrade; no business table or application behavior depends on that width.

Out-of-scope confirmation:
- No impression estimation.
- No traffic density profile tables.
- No payout calculation.
- No earnings ledger.
- No advertiser dashboard/reporting APIs.
- No heatmap APIs.
- No campaign daily metrics.
- No driver earnings APIs.
- No billing, invoicing, settlements, payment APIs, or payout blocking.
- No advanced ML fraud detection.
- No external map matching, map providers, map tiles, geocoding, or reverse geocoding.
- No background jobs or automated analytics scheduling.
- No seed/demo trip data.
- No creative binary upload/storage pipeline.
- No public self-registration, OAuth, social login, or refresh-token flow.
- No frontend/mobile implementation.
- No GitHub remote/PR setup.
- No production cloud deployment, retargeting, audience pooling, AI/computer vision, or real payment settlement.

Acceptance criteria checklist:
- Alembic migration creates exactly `trip_analytics` and `fraud_flags`: yes.
- Migration creates unique constraint/index on `trip_analytics.trip_session_id`: yes.
- Migration creates expected indexes on campaign, driver, vehicle, status, severity, and flag type: yes.
- Migration does not create impression, traffic density, payout, earnings, reporting, heatmap, ledger, or seed tables: yes.
- Admin can recompute analytics for ended trips: yes.
- Analytics recompute is idempotent and does not duplicate analytics rows or open fraud flags: yes.
- Analytics calculation uses stored location pings and PostGIS/geography-safe distance behavior: yes.
- Analytics includes required metrics: yes.
- Analytics handles insufficient data deterministically: yes.
- Campaign zone overlap uses existing campaign zones and PostGIS intersection checks: yes.
- Required fraud/anomaly flags are generated: yes.
- Admin can read analytics and list/filter fraud flags: yes.
- Driver can read only their own analytics summary: yes.
- Admin/driver/advertiser/unauthenticated boundaries are enforced: yes.
- API responses do not expose password hashes or unrelated sensitive data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Codex questions:
- Please confirm the `alembic_version.version_num` widening to support the expected long revision id is acceptable.
- If passing, please provide the recommended commit message and the full Slice 8 implementation prompt.

Orchestrator recommendation:
PASS_CANDIDATE
