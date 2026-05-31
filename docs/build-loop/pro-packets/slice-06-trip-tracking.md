PRO REVIEW PACKET

Slice:
Slice 6 - GPS ingestion and trip/session tracking

Review request:
Please review this Slice 6 implementation for ship readiness. Respond with `PASS`, `FIX REQUIRED`, or `BLOCKED`. If this passes, please say it is safe to commit and provide a recommended commit message plus the full Slice 7 implementation prompt.

Repo state summary:
- Branch: `slice-06-trip-tracking`
- Base accepted state: Slice 5 recorded at `ac8f5b8 docs: record slice 5 commit`
- Slice 5 feature commit: `95359a4 feat: add campaign assignments and activation lifecycle`
- Current status: uncommitted Slice 6 PASS_CANDIDATE
- Current Alembic head after Slice 6: `0007_trip_tracking`
- API prefix remains `/api/v1`
- Fixed stack preserved: FastAPI, Pydantic v2, SQLAlchemy async, asyncpg, Alembic, PostgreSQL/PostGIS, Redis, JWT, pytest, ruff, Docker Compose.

Commit status:
- No Slice 6 commit has been created yet.
- Working tree contains only the Slice 6 implementation/report/ledger changes listed below.
- Intended commit only after Pro PASS and local reconciliation.

Approved Slice 6 prompt summary:
- Implement only driver trip/session tracking and GPS/location ping ingestion for active campaign assignments.
- Add migration `0007_trip_tracking` after `0006_campaign_assignments`.
- Create exactly three new business tables: `trip_sessions`, `location_ping_batches`, `location_pings`.
- Store pings as PostGIS `geometry(Point,4326)` with longitude as X and latitude as Y.
- Add driver-only endpoints:
  - `POST /api/v1/driver/trips/start`
  - `GET /api/v1/driver/trips/current`
  - `POST /api/v1/driver/trips/{trip_id}/pings`
  - `POST /api/v1/driver/trips/{trip_id}/end`
  - `GET /api/v1/driver/trips/{trip_id}`
- Enforce non-leaking ownership, active assignment/campaign/driver/vehicle eligibility, one active trip per driver/vehicle, durable idempotency, all-or-nothing ping validation, timestamp and coordinate bounds, config maxima, and assignment-preserving trip end.
- Do not implement route analytics, distance, moving time, dwell, zone overlap analytics, fraud flags, impressions, payouts, reports, heatmaps, map tiles/providers, background jobs, seed trips, frontend/mobile, or any later-slice scope.

Files changed:
- `.env.example`
- `README.md`
- `alembic/versions/0007_trip_tracking.py`
- `app/api/v1/router.py`
- `app/api/v1/trips.py`
- `app/core/config.py`
- `app/db/base.py`
- `app/models/trip.py`
- `app/schemas/trips.py`
- `app/services/trips.py`
- `docker-compose.yml`
- `docs/build-loop/reports/slice-06-trip-tracking.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_config.py`
- `tests/test_migration_slice6.py`
- `tests/test_trips.py`

Diff summary:
- Adds trip/session, location ping batch, and location ping models with check constraints, metadata columns, timestamps, idempotency uniqueness, partial active-trip indexes, and PostGIS point type.
- Adds Slice 6 Alembic migration `0007_trip_tracking` after `0006_campaign_assignments`.
- Adds driver trip router and mounts it under the existing `/api/v1` router.
- Adds trip schemas with forbidden extras, metadata object fields, trimmed end reason/idempotency key, timezone-aware recorded timestamps, and coordinate/numeric bounds.
- Adds trip service logic for start/current/read/end, assignment/campaign/driver/vehicle eligibility, non-leaking ownership, idempotency hashing, all-or-nothing ping validation, and PostGIS point construction.
- Adds location tracking settings to app config, `.env.example`, and Docker Compose.
- Extends tests/fixtures for trip lifecycle, RBAC, ownership, eligibility, idempotency, validation, PostGIS point storage, migration guardrails, and config validation.
- Updates README and build-loop ledger/report.

Database migrations:
- New migration: `alembic/versions/0007_trip_tracking.py`
- Down revision: `0006_campaign_assignments`
- Creates exactly three new Slice 6 business tables:
  - `trip_sessions`
  - `location_ping_batches`
  - `location_pings`
- `trip_sessions`:
  - UUID PK with `gen_random_uuid()`
  - FKs to `campaign_assignments`, `campaigns`, `driver_profiles`, `vehicles`, and `users`
  - status constrained to `active` or `ended`
  - timezone-aware lifecycle timestamps
  - metadata JSONB default `{}`
  - indexes for assignment/campaign/driver/vehicle/status/start lookups
  - partial unique indexes for active driver profile and active vehicle
- `location_ping_batches`:
  - UUID PK with `gen_random_uuid()`
  - FK to `trip_sessions`
  - `idempotency_key`, `payload_hash`, `pings_accepted`, `received_at`, metadata, created timestamp
  - unique `(trip_session_id, idempotency_key)`
  - check `pings_accepted >= 0`
  - indexes on trip and trip/received_at
- `location_pings`:
  - UUID PK with `gen_random_uuid()`
  - FKs to `trip_sessions` and `location_ping_batches`
  - recorded/received timestamps
  - sequence, latitude, longitude, accuracy, speed, heading, altitude fields
  - `geom geometry(Point,4326)` and GiST index
  - check constraints for sequence, coordinate, heading, altitude, nonnegative accuracy/speed
- Does not add route analytics, fraud, impression, payout, report, heatmap, seed, ledger, or future-scope tables.

Key code evidence:
- `app/api/v1/trips.py` defines `/current` before `/{trip_id}` and all endpoints use `DriverUserDependency`.
- `app/services/trips.py` starts trips only after resolving current driver profile and querying assignment by both assignment id and driver profile id.
- `app/services/trips.py` validates active assignment, active campaign/date window, active driver profile, active vehicle, vehicle ownership, and no active trip for driver/vehicle before inserting.
- `app/services/trips.py` reads/ends/ingests pings only after querying trip by both trip id and current driver profile id.
- `app/services/trips.py` hashes a canonical accepted payload and uses the database-backed `(trip_session_id, idempotency_key)` row as the durable idempotency record.
- `app/services/trips.py` checks batch size and validates every ping before inserting `location_ping_batches` or `location_pings`.
- `app/services/trips.py` stores PostGIS points using `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` for PostgreSQL and a simple WKT fallback for SQLite tests.
- `app/schemas/trips.py` forbids extra fields and limits response fields to trip summaries and batch acknowledgement data.

Security/validation implemented:
- Driver-only trip endpoints reject admin, advertiser, and unauthenticated calls.
- Cross-driver assignment start returns non-leaking `CAMPAIGN_ASSIGNMENT_NOT_FOUND` 404.
- Cross-driver trip read/end/ping operations return non-leaking `TRIP_NOT_FOUND` 404.
- Trip start enforces active assignment, active campaign status/date window, active driver profile, active vehicle, vehicle belongs to driver, and active trip uniqueness.
- Current trip returns `{ "trip": null }` when no active trip exists.
- Ping ingestion requires active owned trip and active assignment.
- End trip sets server-side lifecycle fields, trims optional reason, and does not deactivate the assignment.
- Request schemas forbid extra fields and require metadata objects by typed `dict[str, Any]` fields.

Location ping behavior:
- `idempotency_key` is required and trimmed.
- Batch must contain 1..`MAX_LOCATION_PINGS_PER_BATCH` pings.
- Duplicate idempotency key plus same canonical payload returns the original batch with `duplicate=true` and inserts no rows.
- Duplicate idempotency key plus different canonical payload returns `IDEMPOTENCY_KEY_CONFLICT`.
- Future timestamps beyond `LOCATION_PING_FUTURE_SKEW_SECONDS` are rejected.
- Timestamps before `trip.started_at - LOCATION_PING_START_SKEW_SECONDS` are rejected.
- Latitude, longitude, accuracy, speed, heading, altitude, and sequence bounds are enforced.
- Point storage uses longitude as X and latitude as Y.

Configuration:
- Added defaults:
  - `MAX_LOCATION_PINGS_PER_BATCH=500`
  - `LOCATION_PING_FUTURE_SKEW_SECONDS=300`
  - `LOCATION_PING_START_SKEW_SECONDS=900`
  - `MAX_LOCATION_ACCURACY_M=10000`
  - `MAX_LOCATION_SPEED_MPS=120`
- Added positive-value validation for all Slice 6 tracking settings.
- Added env/Compose values for local and Docker runs.

Tests/checks run:
- `python -m ruff check .`
- `python -m pytest tests/test_migration_slice6.py tests/test_trips.py -q`
- `python -m pytest tests/test_config.py tests/test_trips.py -q`
- `python -m pytest`
- `python -m alembic upgrade head` with Postgres/PostGIS `DATABASE_URL`
- `python -m alembic current` with Postgres/PostGIS `DATABASE_URL`
- `python -m pytest` with Postgres/PostGIS `DATABASE_URL`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Exact command outputs or concise results:
- Host ruff:
  - `All checks passed!`
- Host targeted Slice 6 tests:
  - `python -m pytest tests/test_migration_slice6.py tests/test_trips.py -q`
  - `17 passed, 1 skipped, 1 warning in 33.33s`
- Host targeted tests after evidence fix:
  - `python -m pytest tests/test_config.py tests/test_trips.py -q`
  - `30 passed, 1 skipped, 1 warning in 40.17s`
- Host full tests without `DATABASE_URL`:
  - `107 passed, 9 skipped, 1 warning in 193.30s`
  - Skips are PostGIS-gated tests when no PostGIS URL is configured.
- Host Alembic upgrade/current with `DATABASE_URL=postgresql+asyncpg://mobility:mobility@localhost:5433/mobility`:
  - upgrade passed
  - current: `0007_trip_tracking (head)`
- Host full tests with same PostGIS `DATABASE_URL`:
  - `116 passed, 1 warning in 277.22s`
- Docker build:
  - image `mobility-api:latest` built successfully
- Docker Python:
  - `Python 3.12.13`
- Docker full tests:
  - `116 passed, 1 warning in 313.59s`
- Docker ruff:
  - `All checks passed!`

Audit/fix reconciliation:
- Clean service/API auditor found no blocker-class issues after implementation.
- Clean migration/test/config auditor flagged evidence gaps around PostGIS verification, ownership/RBAC test coverage, and config tests.
- Orchestrator verified Alembic `upgrade head` and full tests against PostGIS, addressing migration/geometry evidence.
- Clean fix worker added:
  - cross-driver trip-start ownership test with non-leaking 404
  - broader RBAC rejection coverage across Slice 6 endpoints
  - Slice 6 config default and positive-validation tests
  - README note explaining SQLite host tests vs PostGIS-backed verification command
- All full host/PostGIS/Docker checks were rerun after the fix.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.
- PostGIS-specific tests intentionally skip on host when no `DATABASE_URL` or `TEST_DATABASE_URL` is configured. They pass with a real PostGIS URL and in Docker.

Out-of-scope confirmation:
- No route analytics.
- No distance, moving time, dwell time, route polyline, or zone-overlap analytics.
- No fraud/anomaly flags.
- No impression estimation.
- No payout calculation or earnings ledger.
- No advertiser dashboard/reporting APIs.
- No heatmap APIs.
- No map tiles, map providers, route matching, geocoding, or reverse geocoding.
- No background jobs.
- No seed/demo trip data.
- No creative binary upload/storage pipeline.
- No frontend/mobile implementation.
- No deployment, retargeting, audience pooling, AI/computer vision, or payment settlement scope.

Acceptance criteria checklist:
- Alembic migration creates exactly `trip_sessions`, `location_ping_batches`, and `location_pings`: yes.
- Migration down revision is `0006_campaign_assignments`: yes.
- Location pings store real PostGIS `geometry(Point,4326)`: yes.
- GiST index exists on ping geometry: yes.
- Unique idempotency constraint exists on `(trip_session_id, idempotency_key)`: yes.
- Active trip uniqueness is enforced by service checks and PostgreSQL partial unique indexes: yes.
- Driver can start a trip for an active eligible assignment: yes.
- Driver can get current active trip and receives `trip: null` when none exists: yes.
- Driver can ingest batched pings idempotently: yes.
- Duplicate same-payload idempotency returns existing batch without double inserts: yes.
- Duplicate different-payload idempotency returns deterministic conflict: yes.
- Ping validation is all-or-nothing: yes.
- Driver can end and read own trip: yes.
- End trip does not deactivate assignment: yes.
- Ownership checks are non-leaking: yes.
- Admin/advertiser/unauthenticated boundaries are enforced: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Codex questions:
- None.

Orchestrator recommendation:
PASS_CANDIDATE
