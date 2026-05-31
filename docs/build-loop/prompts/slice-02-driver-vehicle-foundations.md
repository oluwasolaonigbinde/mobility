You are implementing Slice 2 of the Mobility AdTech & Audience Attribution backend.

Slice 0 foundation and Slice 1 auth/users/advertiser organizations have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 1 has been committed or that the working tree contains only the accepted Slice 1 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and later analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 2 goal:
Establish the supply-side backend foundation: driver profiles and vehicle profiles. This gives the platform a controlled inventory of drivers and vehicles that later slices can assign to campaigns and track through GPS sessions.

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
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0 and Slice 1 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Confirm the existing API prefix is `/api/v1`.
6. Confirm the existing standard error envelope and reuse it.
7. Confirm the existing roles are exactly compatible with: `admin`, `advertiser`, `driver`.
8. Confirm no Slice 2 driver/vehicle tables already exist.
9. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 2:

1. Driver profile model, schema, service, and API support.
2. Vehicle model, schema, service, and API support.
3. Admin endpoints for creating/listing/updating driver profiles.
4. Driver endpoints for reading/updating the current driver’s own profile.
5. Admin endpoints for creating/listing/updating vehicles.
6. Driver endpoint for listing the current driver’s own vehicles.
7. Driver endpoint for retrieving one of the current driver’s own vehicles.
8. Alembic migration for Slice 2 tables, constraints, and indexes.
9. Tests for driver profile access control, vehicle ownership boundaries, validation, and migration behavior.
10. README/OpenAPI documentation updates only where needed for Slice 2 usage.
11. Audit events for admin-created/updated driver profiles and vehicles, using the existing audit event mechanism from Slice 1.

DO NOT IMPLEMENT

- Campaigns
- Campaign creatives
- Campaign target zones/geofences
- Campaign assignments
- Campaign activation
- GPS pings
- Trip sessions
- Route analytics
- Fraud flags
- Impression estimation
- Payout calculation
- Earnings ledger
- Advertiser dashboard/reporting APIs
- Heatmap APIs
- Seed/demo trip data
- Celery/background jobs
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

Create a new Alembic migration after the Slice 1 migration.

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()` now that `pgcrypto` is enabled.

Use timezone-aware timestamps.

Use either PostgreSQL enums or string columns with database check constraints. Match the Slice 1 style unless there is a strong local reason not to.

Required tables:

1. `driver_profiles`

Required columns:

- `id` UUID primary key
- `user_id` UUID foreign key to `users.id`, not null, unique
- `onboarding_status` constrained to:
  - `pending`
  - `active`
  - `suspended`
  - `rejected`
- `license_number` nullable text
- `service_city` nullable text
- `country_code` nullable text
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Rules:

- A driver profile may only be created for a user whose role is `driver`.
- One driver profile per driver user.
- `country_code`, if supplied, should be normalized uppercase.
- `service_city`, if supplied, should be trimmed.
- `license_number`, if supplied, should be trimmed.
- Do not expose unrelated user-sensitive data in driver profile responses.

Suggested indexes:

- `driver_profiles(user_id)`
- `driver_profiles(onboarding_status)`
- Optional composite index on `(country_code, service_city)` if straightforward.

2. `vehicles`

Required columns:

- `id` UUID primary key
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `plate_number` text, not null
- `plate_number_normalized` text, not null
- `plate_country_code` text, not null
- `vehicle_type` constrained to:
  - `car`
  - `van`
  - `minibus`
  - `bus`
  - `motorcycle`
  - `tricycle`
  - `other`
- `make` nullable text
- `model` nullable text
- `year` nullable integer
- `color` nullable text
- `status` constrained to:
  - `pending`
  - `active`
  - `inactive`
  - `suspended`
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Required constraints:

- Unique constraint on `(plate_country_code, plate_number_normalized)`.
- `year`, if supplied, must be reasonable. Use a simple validation such as 1980 through current year + 1 at the API/service layer. A DB check is optional if it can be implemented cleanly.

Rules:

- Vehicles must belong to an existing driver profile.
- `plate_country_code` must be normalized uppercase.
- `plate_number_normalized` should be derived from `plate_number` by uppercasing and removing whitespace/hyphens or by a similarly deterministic normalization. Document the chosen behavior.
- API responses may include the display `plate_number`, but should not rely on raw display value for uniqueness.
- Active vehicles require:
  - driver profile
  - plate number
  - plate country code
  - vehicle type
- A driver can only view vehicles attached to their own driver profile.
- Admin can view and update all vehicles.

Suggested indexes:

- `vehicles(driver_profile_id)`
- `vehicles(status)`
- `vehicles(plate_country_code, plate_number_normalized)`

AUDIT EVENT REQUIREMENTS

Use the existing `audit_events` table/service from Slice 1.

Write audit events for admin actions:

- `admin.driver_profile.created`
- `admin.driver_profile.updated`
- `admin.vehicle.created`
- `admin.vehicle.updated`

Do not add audit events for routine driver self-profile updates unless it is already trivial and consistent with the existing service. Keep the slice focused.

SECURITY AND VALIDATION REQUIREMENTS

1. Admin-only endpoints must require role `admin`.
2. Driver-only endpoints must require role `driver`.
3. Advertiser users must not access driver-only or admin-only supply endpoints.
4. Driver users must only access their own profile and own vehicles.
5. Admin vehicle creation must reject non-driver users or missing driver profiles.
6. Duplicate normalized vehicle plate within the same plate country must be rejected.
7. Invalid vehicle type/status/onboarding status must be rejected.
8. Invalid year must be rejected.
9. No endpoint may expose password hashes.
10. Use the existing standard error envelope from Slice 0/Slice 1.
11. Reuse existing auth/current-user dependencies and role-check patterns.
12. Do not introduce new auth schemes.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

1. `GET /api/v1/driver/profile`

Driver-only.

Returns the current driver’s profile.

Response shape:

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "email": "driver@example.com",
  "full_name": "Driver Name",
  "phone": null,
  "onboarding_status": "active",
  "license_number": "DRV-123",
  "service_city": "Lagos",
  "country_code": "NG",
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:00:00Z"
}

Rules:

If the authenticated driver has no profile, return a clear 404/domain error using the standard error envelope.

Admin/advertiser users are rejected.

PATCH /api/v1/driver/profile

Driver-only.

Allowed driver self-update fields:

JSON
{
  "license_number": "DRV-123",
  "service_city": "Lagos",
  "country_code": "NG"
}

Rules:

Driver can update only their own existing profile.

Driver cannot change user_id or onboarding_status.

If the authenticated driver has no profile, return a clear 404/domain error.

Admin/advertiser users are rejected.

GET /api/v1/driver/vehicles

Driver-only.

Returns the current driver’s vehicles.

Response shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

Rules:

Only vehicles attached to the current driver profile are returned.

If no driver profile exists, return a clear 404/domain error.

GET /api/v1/driver/vehicles/{vehicle_id}

Driver-only.

Rules:

Return the vehicle only if it belongs to the current driver profile.

If the vehicle belongs to another driver, return 404 or forbidden using the standard error envelope. Prefer not to leak cross-driver existence.

POST /api/v1/admin/drivers/{user_id}/profile

Admin-only.

Creates a driver profile for an existing user.

Input:

JSON
{
  "onboarding_status": "pending",
  "license_number": "DRV-123",
  "service_city": "Lagos",
  "country_code": "NG",
  "metadata": {}
}

Output: created driver profile with user summary fields.

Rules:

user_id must exist.

User must have role driver.

Reject duplicate profile for the same user.

Write audit event admin.driver_profile.created.

GET /api/v1/admin/drivers

Admin-only.

Lists driver profiles with minimal user summary.

Query parameters:

limit, default 50, max 100

offset, default 0

optional onboarding_status

optional country_code

optional service_city

Response shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

GET /api/v1/admin/drivers/{driver_profile_id}

Admin-only.

Returns one driver profile with user summary.

PATCH /api/v1/admin/drivers/{driver_profile_id}

Admin-only.

Allowed admin update fields:

JSON
{
  "onboarding_status": "active",
  "license_number": "DRV-123",
  "service_city": "Lagos",
  "country_code": "NG",
  "metadata": {}
}

Rules:

Admin can change onboarding status.

Admin cannot change user_id.

Write audit event admin.driver_profile.updated.

POST /api/v1/admin/drivers/{user_id}/vehicles

Admin-only.

Creates a vehicle for the driver profile associated with the given driver user.

Input:

JSON
{
  "plate_number": "ABC-123",
  "plate_country_code": "NG",
  "vehicle_type": "car",
  "make": "Toyota",
  "model": "Corolla",
  "year": 2018,
  "color": "White",
  "status": "pending",
  "metadata": {}
}

Output: created vehicle.

Rules:

user_id must exist and have role driver.

Driver profile must exist for that user.

Duplicate normalized plate within same country is rejected.

Write audit event admin.vehicle.created.

GET /api/v1/admin/vehicles

Admin-only.

Lists vehicles with minimal driver/user summary.

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

optional vehicle_type

optional plate_country_code

optional driver_profile_id

Response shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

GET /api/v1/admin/vehicles/{vehicle_id}

Admin-only.

Returns one vehicle with minimal driver/user summary.

PATCH /api/v1/admin/vehicles/{vehicle_id}

Admin-only.

Allowed update fields:

JSON
{
  "plate_number": "ABC-123",
  "plate_country_code": "NG",
  "vehicle_type": "car",
  "make": "Toyota",
  "model": "Corolla",
  "year": 2018,
  "color": "White",
  "status": "active",
  "metadata": {}
}

Rules:

Recompute normalized plate if plate fields change.

Enforce duplicate normalized plate uniqueness.

Write audit event admin.vehicle.updated.

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0/Slice 1 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/driver_profiles.py or similar

app/api/v1/vehicles.py or similar

app/models/driver.py

app/models/vehicle.py

app/models/__init__.py

app/schemas/drivers.py

app/schemas/vehicles.py

app/services/drivers.py

app/services/vehicles.py

app/services/audit.py only if needed to add action helpers

app/api/v1/dependencies.py only if needed to reuse/add driver role helpers

app/db/base.py only if model imports require update

alembic/versions/<slice2_revision>_drivers_and_vehicles.py

README.md

tests for driver profiles, vehicles, access control, and migration behavior

docs/build-loop/reports/slice-02-drivers-vehicles.md

Keep code simple. Avoid unnecessary abstractions.

TEST REQUIREMENTS

Add/extend tests for:

Admin can create a driver profile for an existing driver user.

Admin cannot create a driver profile for an admin user.

Admin cannot create a driver profile for an advertiser user.

Duplicate driver profile for the same user is rejected.

Driver can retrieve own profile.

Driver cannot retrieve profile if no profile exists and receives standard error envelope.

Driver can update allowed own profile fields.

Driver cannot update own onboarding_status.

Advertiser user is rejected from driver profile endpoints.

Unauthenticated users are rejected from driver/admin supply endpoints.

Admin can list driver profiles with pagination response shape.

Admin can update driver onboarding status.

Admin can create vehicle for driver with an existing driver profile.

Admin cannot create vehicle for user without driver role.

Admin cannot create vehicle for driver user without driver profile.

Duplicate normalized plate in same country is rejected.

Same plate number in different plate country is allowed.

Invalid vehicle type/status is rejected.

Invalid vehicle year is rejected.

Driver can list only own vehicles.

Driver can retrieve own vehicle.

Driver cannot retrieve another driver’s vehicle.

Admin can list vehicles with pagination response shape.

Admin can update vehicle status and details.

Vehicle update recomputes normalized plate and enforces uniqueness.

Password hashes are still not returned in user summaries embedded in driver/vehicle responses.

Audit event is created for admin-created driver profile.

Audit event is created for admin-created vehicle.

Alembic migration applies cleanly.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from Slice 1.

If existing tests use SQLite for speed, maintain compatibility where practical, but do not weaken Postgres migration verification.

Migration verification against Postgres/PostGIS remains required.

Keep tests deterministic.

CHECKS THAT MUST WORK

The final implementation should support:

python -m pytest
python -m ruff check .
alembic upgrade head

Also verify Python 3.12 through Docker as in Slice 1:

docker compose run --rm api python --version
docker compose run --rm api python -m pytest
docker compose run --rm api python -m ruff check .

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Driver app can use:

http
GET /api/v1/driver/profile
PATCH /api/v1/driver/profile
GET /api/v1/driver/vehicles
GET /api/v1/driver/vehicles/{vehicle_id}

Admin tools can use:

http
POST /api/v1/admin/drivers/{user_id}/profile
GET /api/v1/admin/drivers
GET /api/v1/admin/drivers/{driver_profile_id}
PATCH /api/v1/admin/drivers/{driver_profile_id}
POST /api/v1/admin/drivers/{user_id}/vehicles
GET /api/v1/admin/vehicles
GET /api/v1/admin/vehicles/{vehicle_id}
PATCH /api/v1/admin/vehicles/{vehicle_id}

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

Driver profile and vehicle response shapes must be stable enough for future frontend/mobile work. Do not expose password hashes.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0/Slice 1 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Driver profile missing

User is not a driver

Duplicate driver profile

Vehicle not found

Vehicle belongs to another driver

Duplicate normalized vehicle plate

Invalid vehicle type/status/year

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 2 is acceptable only if:

Alembic migration creates exactly the approved driver_profiles and vehicles tables, constraints, and indexes.

No Slice 3+ domain tables are added.

Driver profiles can only be associated with users whose role is driver.

One driver profile per driver user is enforced.

Admin can create/list/read/update driver profiles.

Driver can read/update only their own existing profile.

Admin can create/list/read/update vehicles.

Vehicle ownership is tied to driver profiles.

Driver can list/read only their own vehicles.

Duplicate normalized vehicle plates are rejected within the same plate country.

Vehicle validation covers type, status, country code normalization, plate normalization, and year.

Admin/driver/advertiser access boundaries are enforced.

Audit events are written for admin-created/updated driver profiles and vehicles.

API responses do not expose password hashes.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 1 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support Slice 2 without reworking previous slices.

Driver/vehicle ownership requires a product decision not covered here.

You are tempted to add campaigns, creatives, zones, assignments, GPS, analytics, payouts, reports, heatmaps, or seed/demo scope.

Otherwise, stop after Slice 2. Do not continue to Slice 3.

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
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED