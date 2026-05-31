PASS

Safe to commit: Yes. Commit Slice 5 before starting Slice 6.

Basis: Slice 5 adds the approved assignment and activation-event tables, required admin/driver assignment endpoints, deterministic lifecycle transitions, eligibility checks, audit/activation events, uniqueness enforcement, passing host/Docker/Alembic/ruff checks, and no Slice 6+ GPS/trip/analytics scope. 

Pasted text

 

Pasted text

Recommended commit message:

feat: add campaign assignments and activation lifecycle

Full Slice 6 implementation prompt:

You are implementing Slice 6 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, Slice 4 campaign zones/geofences, and Slice 5 campaign assignment/activation have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 5 has been committed or that the working tree contains only the accepted Slice 5 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and later analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 6 goal:
Implement GPS/location ping ingestion and trip/session tracking for drivers with active campaign assignments. This slice should let the future driver mobile app start a tracking session, send batched GPS pings idempotently, view the current trip/session, read a trip summary, and end the trip/session. Later slices will compute route analytics, fraud/anomaly flags, impressions, payouts, reports, and heatmaps from this stored movement data.

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
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 through Slice 5 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing campaign assignment, campaign, driver profile, vehicle, and activation lifecycle service patterns from Slice 5.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the existing standard error envelope and reuse it.
8. Confirm the current Alembic head is `0006_campaign_assignments`.
9. Confirm no Slice 6 trip/session/location ping tables already exist.
10. Determine existing PostGIS geometry implementation patterns from Slice 4 and reuse them where appropriate.
11. Determine current test strategy for Postgres/PostGIS-backed tests and preserve it.
12. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 6:

1. Trip/session model, schema, service, and API support.
2. Location ping batch model, schema, service, and idempotency support.
3. Location ping model, schema, service, and PostGIS point storage.
4. Driver endpoint to start a trip for an active campaign assignment.
5. Driver endpoint to get the current active trip.
6. Driver endpoint to ingest a batch of GPS/location pings for an active trip.
7. Driver endpoint to end a trip.
8. Driver endpoint to read one of the current driver’s own trips.
9. Alembic migration for exactly the Slice 6 trip/session and location ping tables, constraints, and indexes.
10. Tests for trip lifecycle, driver ownership boundaries, assignment eligibility, ping validation, idempotency, PostGIS point storage, migration behavior, and out-of-scope guardrails.
11. README/OpenAPI documentation updates only where needed for Slice 6 usage.

DO NOT IMPLEMENT

- Route analytics
- Distance calculations
- Moving time calculations
- Dwell time calculations
- Zone-overlap analytics
- Fraud/anomaly flags
- Impression estimation
- Payout calculation
- Earnings ledger
- Advertiser dashboard/reporting APIs
- Heatmap APIs
- Map tiles
- Mapbox integration
- Geocoding/reverse-geocoding
- External map provider integration
- Automatic route matching
- Trip polyline generation
- Background jobs
- Celery workers
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

Create a new Alembic migration after the Slice 5 migration.

Expected migration name:
`0007_trip_tracking`

Expected down revision:
`0006_campaign_assignments`

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()`.

Use timezone-aware timestamps.

Use PostGIS geometry storage with SRID 4326 for location points.

Use either PostgreSQL enums or string columns with database check constraints. Match the existing repo style unless there is a strong local reason not to.

Create exactly these new business tables:

1. `trip_sessions`

Required columns:

- `id` UUID primary key
- `assignment_id` UUID foreign key to `campaign_assignments.id`, not null
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `vehicle_id` UUID foreign key to `vehicles.id`, not null
- `started_by_user_id` UUID foreign key to `users.id`, not null
- `status` constrained to:
  - `active`
  - `ended`
- `started_at` timezone-aware timestamp, not null
- `ended_at` timezone-aware timestamp nullable
- `end_reason` text nullable
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Rules:

- Trip belongs to exactly one active campaign assignment.
- Trip stores campaign, driver profile, and vehicle snapshots through foreign keys for query efficiency.
- Trip can be started only by the driver who owns the assignment’s driver profile.
- Trip can be started only when assignment status is `active`.
- Campaign must still be `active` and within its date window at trip start.
- Driver profile must still be `active`.
- Vehicle must still be `active`.
- Vehicle must belong to the assignment’s driver profile.
- A driver profile may have at most one active trip.
- A vehicle may have at most one active trip.
- Use service-level checks and PostgreSQL partial unique indexes where feasible.
- Driver cannot client-set lifecycle timestamps.
- `metadata` must be an object when supplied.
- `end_reason`, if supplied, should be trimmed.

Suggested constraints/indexes:

- Check constraint for `status`.
- Index on `assignment_id`.
- Index on `campaign_id`.
- Index on `driver_profile_id`.
- Index on `vehicle_id`.
- Index on `(driver_profile_id, status)`.
- Index on `(vehicle_id, status)`.
- Index on `(campaign_id, started_at)`.
- PostgreSQL partial unique index on `driver_profile_id` where `status = 'active'`.
- PostgreSQL partial unique index on `vehicle_id` where `status = 'active'`.

2. `location_ping_batches`

Required columns:

- `id` UUID primary key
- `trip_session_id` UUID foreign key to `trip_sessions.id`, not null
- `idempotency_key` text, not null
- `payload_hash` text, not null
- `pings_accepted` integer, not null
- `received_at` timezone-aware timestamp, not null
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null

Required constraints:

- Unique constraint on `(trip_session_id, idempotency_key)`.
- `pings_accepted` must be >= 0.

Rules:

- Each ping ingestion request must include an `idempotency_key`.
- Reusing the same `idempotency_key` with the same payload for the same trip returns the original batch response and must not double-insert pings.
- Reusing the same `idempotency_key` with a different payload for the same trip must return a deterministic conflict error using the standard error envelope.
- `payload_hash` should be derived from a canonical JSON representation of the accepted request payload.
- `metadata` must be an object when supplied.

Suggested indexes:

- Index on `trip_session_id`.
- Index on `(trip_session_id, received_at)`.

3. `location_pings`

Required columns:

- `id` UUID primary key
- `trip_session_id` UUID foreign key to `trip_sessions.id`, not null
- `batch_id` UUID foreign key to `location_ping_batches.id`, not null
- `recorded_at` timezone-aware timestamp, not null
- `received_at` timezone-aware timestamp, not null
- `sequence_number` integer nullable
- `latitude` double precision, not null
- `longitude` double precision, not null
- `accuracy_m` double precision nullable
- `speed_mps` double precision nullable
- `heading_degrees` double precision nullable
- `altitude_m` double precision nullable
- `geom` PostGIS geometry, not null
  - Preferred type: `geometry(Point, 4326)`
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null

Rules:

- Store GPS location as both numeric latitude/longitude and real PostGIS `Point` geometry with SRID 4326.
- Use Geo coordinate order correctly when creating the point:
  - longitude = X
  - latitude = Y
- Store `recorded_at` from the mobile client.
- Store `received_at` from the server.
- `sequence_number`, if supplied, must be >= 0.
- `latitude` must be between -90 and 90.
- `longitude` must be between -180 and 180.
- `accuracy_m`, if supplied, must be >= 0 and <= configured max.
- `speed_mps`, if supplied, must be >= 0 and <= configured max.
- `heading_degrees`, if supplied, must be >= 0 and < 360.
- `altitude_m`, if supplied, must be within a broad reasonable range, for example -500 through 10000.
- `metadata` must be an object when supplied.
- Do not compute distance, speed from consecutive pings, fraud flags, zone overlap, impressions, or payouts in this slice.

Suggested constraints/indexes:

- Check constraints for coordinate bounds and nonnegative numeric fields where clean.
- Index on `trip_session_id`.
- Index on `(trip_session_id, recorded_at)`.
- Index on `batch_id`.
- GiST index on `geom`.

Do not create route analytics, fraud, impression, payout, report, heatmap, ledger, or seed tables.

CONFIGURATION REQUIREMENTS

Extend existing settings only as needed.

Add settings such as:

- `MAX_LOCATION_PINGS_PER_BATCH`, default `500`
- `LOCATION_PING_FUTURE_SKEW_SECONDS`, default `300`
- `LOCATION_PING_START_SKEW_SECONDS`, default `900`
- `MAX_LOCATION_ACCURACY_M`, default `10000`
- `MAX_LOCATION_SPEED_MPS`, default `120`

Update `.env.example` and Docker Compose only if needed.

SECURITY AND VALIDATION REQUIREMENTS

1. All Slice 6 endpoints are driver-only.
2. Admin users must be rejected from driver trip endpoints.
3. Advertiser users must be rejected from driver trip endpoints.
4. Unauthenticated users must be rejected from all trip endpoints.
5. Driver users must only start/read/end trips tied to their own driver profile.
6. Driver users must only ingest pings for their own active trips.
7. Cross-driver trip access must not leak data. Prefer non-leaking 404 where practical.
8. Reuse existing auth/current-user dependencies and role-check patterns.
9. Reuse the existing standard error envelope from previous slices.
10. Do not introduce new auth schemes.
11. Do not expose password hashes in any embedded user summaries.
12. Do not expose unrelated advertiser billing/user-sensitive data.
13. Do not expose advertiser reporting APIs in this slice.
14. Use UTC-aware timestamps.
15. Use deterministic validation errors.
16. Validate all pings in a batch before inserting any pings; batch ingestion should be all-or-nothing.

TRIP LIFECYCLE RULES

Trip start:

- Current user must have role `driver`.
- Current user must have an existing driver profile.
- Input assignment must exist.
- Assignment must belong to current driver profile.
- Assignment status must be `active`.
- Campaign must be `active`.
- If campaign `start_at` is set, current UTC time must be on or after it.
- If campaign `end_at` is set, current UTC time must be on or before it.
- Driver profile status must be `active`.
- Vehicle status must be `active`.
- Vehicle must still belong to the assignment’s driver profile.
- No active trip may already exist for the current driver profile.
- No active trip may already exist for the assignment vehicle.
- Create trip with status `active`.
- Set `started_at` using server UTC time.

Trip current:

- Current user must have role `driver`.
- If driver has no active trip, return:

```json
{
  "trip": null
}

Trip ping ingestion:

Current user must have role driver.

Trip must exist and belong to current driver profile.

Trip status must be active.

Assignment should still be active to accept new pings.

Batch must include idempotency_key.

Batch must include at least one ping.

Batch size must not exceed MAX_LOCATION_PINGS_PER_BATCH.

All pings are validated before any insert.

Duplicate idempotency key with identical payload returns duplicate response and inserts no new rows.

Duplicate idempotency key with different payload returns conflict error.

Do not automatically end or deactivate trips during ping ingestion.

Trip end:

Current user must have role driver.

Trip must exist and belong to current driver profile.

Trip status must be active.

Set status to ended.

Set ended_at using server UTC time.

Store optional trimmed end_reason.

Do not deactivate the campaign assignment automatically.

Do not compute analytics, payouts, impressions, or fraud flags.

API ENDPOINTS

Implement these endpoints under /api/v1.

POST /api/v1/driver/trips/start

Driver-only.

Input:

JSON
{
  "assignment_id": "assignment-uuid",
  "metadata": {}
}

Output: created active trip summary.

Rules:

Assignment must belong to current driver and be active.

Campaign, driver profile, and vehicle must be eligible.

Driver/vehicle active-trip uniqueness must be enforced.

Server sets started_at.

GET /api/v1/driver/trips/current

Driver-only.

Important routing note:
Define this static route before GET /api/v1/driver/trips/{trip_id} to avoid path conflicts.

Output when active trip exists:

JSON
{
  "trip": {
    "id": "uuid",
    "assignment_id": "uuid",
    "campaign_id": "uuid",
    "driver_profile_id": "uuid",
    "vehicle_id": "uuid",
    "status": "active",
    "started_at": "2026-05-31T00:00:00Z",
    "ended_at": null,
    "ping_count": 0,
    "first_ping_at": null,
    "last_ping_at": null,
    "metadata": {},
    "created_at": "2026-05-31T00:00:00Z",
    "updated_at": "2026-05-31T00:00:00Z"
  }
}

Output when no active trip exists:

JSON
{
  "trip": null
}

POST /api/v1/driver/trips/{trip_id}/pings

Driver-only.

Input:

JSON
{
  "idempotency_key": "mobile-batch-uuid-or-stable-key",
  "pings": [
    {
      "recorded_at": "2026-05-31T12:00:00Z",
      "lat": 6.4500,
      "lon": 3.3900,
      "accuracy_m": 12.5,
      "speed_mps": 8.3,
      "heading_degrees": 180.0,
      "altitude_m": 42.0,
      "sequence_number": 1,
      "metadata": {}
    }
  ],
  "metadata": {}
}

Output on first successful insert:

JSON
{
  "batch_id": "uuid",
  "trip_id": "uuid",
  "accepted_count": 1,
  "duplicate": false
}

Output on duplicate identical request:

JSON
{
  "batch_id": "uuid",
  "trip_id": "uuid",
  "accepted_count": 1,
  "duplicate": true
}

Rules:

Do not accept pings for ended trips.

Do not accept pings for another driver’s trip.

Do not accept pings if assignment is no longer active.

Reject invalid coordinates.

Reject timestamps more than LOCATION_PING_FUTURE_SKEW_SECONDS in the future.

Reject pings recorded before trip.started_at - LOCATION_PING_START_SKEW_SECONDS.

If duplicate idempotency key has different payload, return conflict.

Store points as PostGIS Point with SRID 4326.

Do not compute route analytics.

POST /api/v1/driver/trips/{trip_id}/end

Driver-only.

Input:

JSON
{
  "end_reason": "driver_ended",
  "metadata": {}
}

Output: ended trip summary.

Rules:

Trip must belong to current driver.

Trip must be active.

Server sets ended_at.

No assignment deactivation happens here.

No analytics/impressions/payouts are calculated here.

GET /api/v1/driver/trips/{trip_id}

Driver-only.

Rules:

Return the trip only if it belongs to the current driver profile.

Cross-driver reads must not leak data. Prefer 404.

Include trip summary and ping count, not full raw ping list.

Do not expose advertiser billing data or password hashes.

Trip response should include at minimum:

JSON
{
  "id": "uuid",
  "assignment_id": "uuid",
  "campaign_id": "uuid",
  "driver_profile_id": "uuid",
  "vehicle_id": "uuid",
  "status": "active",
  "started_at": "2026-05-31T00:00:00Z",
  "ended_at": null,
  "end_reason": null,
  "ping_count": 12,
  "first_ping_at": "2026-05-31T00:01:00Z",
  "last_ping_at": "2026-05-31T00:20:00Z",
  "metadata": {},
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:20:00Z"
}

No advertiser or admin trip endpoints are required in Slice 6.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 5 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/trips.py or similar

app/models/trip.py

app/models/location.py or similar

app/models/__init__.py

app/schemas/trips.py

app/schemas/location_pings.py or combined trip schemas

app/services/trips.py

app/services/location_pings.py or combined service if simpler

app/core/config.py

app/api/v1/dependencies.py only if needed to reuse/add driver helpers

app/db/base.py only if model imports require update

alembic/versions/0007_trip_tracking.py

.env.example

README.md

tests/test_trips.py

tests/test_location_pings.py

tests/test_migration_slice6.py

Possibly fixture updates in tests/conftest.py

docs/build-loop/reports/slice-06-trip-tracking.md

Keep code simple. Avoid unnecessary abstractions.

POSTGIS IMPLEMENTATION GUIDANCE

Use PostGIS for authoritative point storage.

Recommended insert behavior:

Validate high-level JSON in Pydantic:

lat, lon, recorded_at, optional fields.

forbid extra fields.

Validate all pings in service before insert:

coordinate bounds

timestamp skew

numeric bounds

batch size

For each ping, create geometry using:

ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)

Ensure persisted geometry uses SRID 4326.

Add GiST index on location_pings.geom.

Do not store pings as JSON-only. PostGIS point storage is required.

IDEMPOTENCY IMPLEMENTATION GUIDANCE

Use the location_ping_batches table.

Recommended behavior:

Build a canonical normalized payload from the requested pings and request metadata.

Compute payload_hash.

Check for existing (trip_session_id, idempotency_key).

If existing batch exists and payload_hash matches:

return existing batch response with duplicate = true

do not insert pings

If existing batch exists and payload_hash differs:

return standard conflict/domain error

If no existing batch:

validate all pings

create batch

create ping rows

return duplicate = false

Do not use Redis-only idempotency for this slice. Durable DB idempotency is required.

TEST REQUIREMENTS

Add/extend tests for:

Trip lifecycle:

Driver can start a trip for own active assignment.

Starting a trip stores campaign, driver profile, vehicle, assignment, and started_by user references.

Driver cannot start a trip for another driver’s assignment.

Driver cannot start a trip without a driver profile.

Driver cannot start a trip if assignment is not active.

Driver cannot start a trip if campaign is not active.

Driver cannot start a trip before campaign start date.

Driver cannot start a trip after campaign end date.

Driver cannot start a trip if driver profile is not active.

Driver cannot start a trip if vehicle is not active.

Driver cannot start a second active trip for the same driver profile.

Driver cannot start a second active trip for the same vehicle.

GET /api/v1/driver/trips/current returns active trip when one exists.

GET /api/v1/driver/trips/current returns {"trip": null} when none exists.

Driver can read own trip summary.

Driver cannot read another driver’s trip; prefer non-leaking 404.

Driver can end own active trip.

Ending a trip sets status = ended and ended_at.

Driver cannot end another driver’s trip.

Driver cannot end an already ended trip.

Ending a trip does not deactivate the assignment.

Ping ingestion:

Driver can ingest a valid ping batch for own active trip.

Location pings are persisted with latitude/longitude and PostGIS Point SRID 4326.

Batch response includes batch_id, trip_id, accepted_count, and duplicate.

Duplicate idempotency key with identical payload returns duplicate = true and does not double-insert pings.

Duplicate idempotency key with different payload returns a conflict/domain error.

Batch size limit is enforced.

Empty ping batch is rejected.

Invalid latitude is rejected.

Invalid longitude is rejected.

Future timestamp beyond configured skew is rejected.

Timestamp before allowed trip-start skew is rejected.

Negative accuracy is rejected.

Excessive accuracy is rejected.

Negative speed is rejected.

Excessive speed is rejected.

Invalid heading is rejected.

Invalid altitude is rejected.

Negative sequence number is rejected.

Metadata must be an object.

Pings for ended trip are rejected.

Pings for another driver’s trip are rejected.

Pings are rejected if assignment is no longer active.

Invalid batch is all-or-nothing and inserts no partial pings.

Access control:

Admin user is rejected from driver trip endpoints.

Advertiser user is rejected from driver trip endpoints.

Unauthenticated user is rejected from driver trip endpoints.

API responses do not expose password hashes.

Migration and scope:

Alembic migration creates exactly trip_sessions, location_ping_batches, and location_pings as new Slice 6 tables.

Migration creates location_pings.geom as PostGIS geometry(Point,4326).

Migration creates a GiST index on location_pings.geom.

Migration creates unique idempotency constraint on (trip_session_id, idempotency_key).

Migration creates partial active-trip uniqueness indexes where feasible.

Migration does not create route analytics, fraud, impression, payout, report, heatmap, ledger, or seed tables.

Existing Slice 0-Slice 5 tests continue to pass.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

This slice depends on PostGIS point storage. Do not fake all geospatial behavior with JSON-only tests.

It is acceptable to run ping/geometry tests against a real PostgreSQL/PostGIS test database if SQLite cannot support geometry behavior.

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

Postgres/PostGIS migration verification is required:

$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current
$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m pytest

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Driver mobile app can use:

http
POST /api/v1/driver/trips/start
GET  /api/v1/driver/trips/current
POST /api/v1/driver/trips/{trip_id}/pings
POST /api/v1/driver/trips/{trip_id}/end
GET  /api/v1/driver/trips/{trip_id}

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

Mobile app should send pings in batches with:

idempotency_key

recorded_at

lat

lon

optional accuracy_m

optional speed_mps

optional heading_degrees

optional altitude_m

optional sequence_number

optional object metadata

GPS tracking exists after this slice, but analytics/reporting do not. Frontend must not expect distance, route line, dwell time, zone overlap, impressions, payouts, fraud status, or heatmap values yet.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 5 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Driver profile missing

Assignment not found

Assignment belongs to another driver

Assignment not active

Campaign not active

Campaign outside date window

Driver profile not active

Vehicle not active

Active trip already exists

Trip not found

Trip belongs to another driver

Trip already ended

Empty ping batch

Batch too large

Idempotency key conflict

Invalid latitude/longitude

Invalid recorded_at

Invalid accuracy/speed/heading/altitude

Invalid metadata

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 6 is acceptable only if:

Alembic migration creates exactly the approved trip_sessions, location_ping_batches, and location_pings tables, constraints, and indexes.

location_pings.geom is stored as real PostGIS geometry(Point,4326).

A GiST index exists on location_pings.geom.

No Slice 7+ route analytics/fraud/impression/payout/report/heatmap tables are added.

Driver can start a trip for an eligible active assignment.

Driver can retrieve current active trip or a null current-trip response.

Driver can ingest validated batched pings for their own active trip.

Ping ingestion is durable and idempotent by (trip_session_id, idempotency_key).

Duplicate idempotent requests do not double-insert pings.

Same idempotency key with different payload is rejected.

Driver can end their own active trip.

Trip and ping access is restricted to the owning driver.

Admin/advertiser/unauthenticated access boundaries are enforced.

Coordinate, timestamp, numeric field, batch size, and metadata validation are enforced.

Pings are rejected for ended trips.

Pings are rejected if assignment is no longer active.

API responses do not expose password hashes or unrelated sensitive data.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 5 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support PostGIS point columns without reworking previous slices.

The test infrastructure cannot support any meaningful PostGIS-backed validation path.

Existing assignment lifecycle behavior makes trip-start eligibility ambiguous in a way that requires a product decision.

Existing router path structure makes /driver/trips/current conflict unavoidable without changing the endpoint contract.

You are tempted to add route analytics, fraud flags, impressions, payouts, earnings, reports, heatmaps, map tiles, or seed/demo data.

Otherwise, stop after Slice 6. Do not continue to Slice 7.

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
Trip lifecycle approach:
Location ping ingestion/idempotency approach:
PostGIS point storage approach:
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
Trip lifecycle implemented:
Location ping ingestion/idempotency implemented:
PostGIS point storage implemented:
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
Trip lifecycle implemented:
Location ping ingestion/idempotency implemented:
PostGIS point storage implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED