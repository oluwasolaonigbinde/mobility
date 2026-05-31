PASS

Safe to commit: Yes. Commit Slice 4 before starting Slice 5.

Basis: Slice 4 added exactly the approved campaign_zones table with PostGIS geometry(MultiPolygon,4326), GiST indexing, advertiser-scoped campaign zone CRUD, GeoJSON validation, PostGIS validity/area checks, audit events, and no Slice 5+ tables or behavior. The reported checks pass on host/PostGIS and Docker Python 3.12: 79 passed, ruff passed, Alembic current is 0005_campaign_zones, and Docker pytest/ruff also passed. 

Pasted text

Recommended commit message:

feat: add campaign zones and geofences

Full Slice 5 implementation prompt:

You are implementing Slice 5 of the Mobility AdTech & Audience Attribution backend.

Slice 0 project foundation, Slice 1 auth/users/advertiser organizations, Slice 2 driver/vehicle foundations, Slice 3 campaign/creative metadata, and Slice 4 campaign zones/geofences have been accepted by Pro review. Build on the existing repo foundation. Do not replace the stack, restructure the project unnecessarily, or introduce speculative scope.

Before starting implementation, confirm Slice 4 has been committed or that the working tree contains only the accepted Slice 4 state. If the repo has uncommitted unrelated changes, stop and report them.

PROJECT CONTEXT

Product:
Mobility AdTech & Audience Attribution Platform.

Backend goal:
Build the backend for a platform where advertisers run campaigns on shared ride vehicles, drivers and vehicles activate campaigns, GPS movement data is ingested, and later analytics support route analytics, impression estimation, payout calculations, advertiser reporting, and heatmap-ready geospatial data.

Slice 5 goal:
Implement campaign assignment and driver/vehicle activation. This connects advertiser campaigns to eligible driver profiles and vehicles, lets drivers accept assigned campaigns, and controls one active campaign assignment per vehicle before Slice 6 adds GPS trip/session tracking.

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
- pytest
- ruff
- Docker Compose

IMPORTANT LOCAL NOTE

The local coding-guidelines file is named `agent.md`, even if other instructions mention `AGENTS.md`. Read and follow `agent.md`.

REQUIRED LOCAL INVESTIGATION BEFORE CODING

1. Inspect the current repo state.
2. Read `agent.md`.
3. Read the accepted Slice 0, Slice 1, Slice 2, Slice 3, and Slice 4 implementation reports under `docs/build-loop/reports/`.
4. Inspect existing app structure, routers, settings, error handling, request ID middleware, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
5. Inspect existing campaign, driver profile, vehicle, audit event, and advertiser membership service patterns.
6. Confirm the existing API prefix is `/api/v1`.
7. Confirm the existing standard error envelope and reuse it.
8. Confirm the current Alembic head is `0005_campaign_zones`.
9. Confirm no Slice 5 campaign assignment or campaign activation event table already exists.
10. Determine existing enum/check-constraint style and match it.
11. If any local evidence conflicts with this prompt, stop and produce a reconciliation report instead of implementing blindly.

ALLOWED SCOPE

Implement only Slice 5:

1. Campaign assignment model, schema, service, and API support.
2. Campaign activation event model, schema/service support, and persistence.
3. Admin endpoint to create campaign assignments.
4. Admin endpoint to list campaign assignments.
5. Admin endpoint to read one campaign assignment.
6. Admin endpoint to cancel an assignment.
7. Driver endpoint to list the current driver’s campaign assignments.
8. Driver endpoint to read one of the current driver’s campaign assignments.
9. Driver endpoint to accept an offered assignment.
10. Driver endpoint to activate an accepted/deactivated assignment.
11. Driver endpoint to deactivate an active assignment.
12. Driver endpoint to fetch the current active assignment.
13. Alembic migration for exactly the Slice 5 campaign assignment and campaign activation event tables, constraints, and indexes.
14. Tests for lifecycle transitions, driver ownership boundaries, admin/driver RBAC, campaign/vehicle eligibility, active-assignment uniqueness, event logging, audit events, migration behavior, and out-of-scope guardrails.
15. README/OpenAPI documentation updates only where needed for Slice 5 usage.
16. Audit events for admin assignment create/cancel actions using the existing audit event mechanism.

DO NOT IMPLEMENT

- GPS pings
- Trip sessions
- Location ingestion
- Route analytics
- Zone-overlap analytics
- Fraud flags
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
- Creative binary upload/storage pipeline
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

Create a new Alembic migration after the Slice 4 migration.

Expected migration name:
`0006_campaign_assignments`

Expected down revision:
`0005_campaign_zones`

Use UUID primary keys. Prefer database-side UUID generation using `gen_random_uuid()`.

Use timezone-aware timestamps.

Use either PostgreSQL enums or string columns with database check constraints. Match the existing repo style unless there is a strong local reason not to.

Create exactly these new business tables:

1. `campaign_assignments`

Required columns:

- `id` UUID primary key
- `campaign_id` UUID foreign key to `campaigns.id`, not null
- `driver_profile_id` UUID foreign key to `driver_profiles.id`, not null
- `vehicle_id` UUID foreign key to `vehicles.id`, not null
- `assigned_by_user_id` UUID foreign key to `users.id`, nullable or not null depending on existing service style; prefer not null for admin-created assignments
- `status` constrained to:
  - `offered`
  - `accepted`
  - `active`
  - `deactivated`
  - `cancelled`
  - `completed`
- `offered_at` timezone-aware timestamp, not null
- `accepted_at` timezone-aware timestamp nullable
- `activated_at` timezone-aware timestamp nullable
- `deactivated_at` timezone-aware timestamp nullable
- `cancelled_at` timezone-aware timestamp nullable
- `completed_at` timezone-aware timestamp nullable
- `notes` text nullable
- `metadata` JSON/JSONB, not null, default empty object
- `created_at` timezone-aware timestamp, not null
- `updated_at` timezone-aware timestamp, not null

Rules:

- Assignment belongs to exactly one campaign.
- Assignment belongs to exactly one driver profile.
- Assignment belongs to exactly one vehicle.
- Vehicle must belong to the assigned driver profile.
- Assignment is created by admin only.
- Initial status is always `offered`.
- Client must not set initial status directly.
- Client must not set lifecycle timestamps directly.
- Client must not set `assigned_by_user_id`.
- `metadata` must be an object when supplied.
- `notes`, if supplied, should be trimmed.
- One active assignment per vehicle must be enforced. Use both service-level checks and a PostgreSQL partial unique index where feasible.
- Duplicate non-terminal assignment for the same `(campaign_id, vehicle_id)` should be rejected while status is one of `offered`, `accepted`, `active`, or `deactivated`. Use service-level checks and a PostgreSQL partial unique index where feasible.
- Do not create trip/session/location-ping records in this slice.

Suggested constraints/indexes:

- Check constraint for `status`.
- Index on `campaign_id`.
- Index on `driver_profile_id`.
- Index on `vehicle_id`.
- Index on `(campaign_id, status)`.
- Index on `(driver_profile_id, status)`.
- Index on `(vehicle_id, status)`.
- PostgreSQL partial unique index on `vehicle_id` where `status = 'active'`.
- PostgreSQL partial unique index on `(campaign_id, vehicle_id)` where `status IN ('offered', 'accepted', 'active', 'deactivated')`.

If SQLite compatibility for tests makes partial unique indexes difficult, keep tests meaningful through service-level checks and ensure Alembic migration still creates the proper PostgreSQL indexes.

2. `campaign_activation_events`

Required columns:

- `id` UUID primary key
- `assignment_id` UUID foreign key to `campaign_assignments.id`, not null
- `actor_user_id` UUID foreign key to `users.id`, nullable
- `event_type` constrained to:
  - `assigned`
  - `accepted`
  - `activated`
  - `deactivated`
  - `cancelled`
  - `completed`
- `previous_status` nullable text
- `new_status` text, not null
- `occurred_at` timezone-aware timestamp, not null
- `metadata` JSON/JSONB, not null, default empty object

Rules:

- Every assignment creation writes `assigned`.
- Driver accept writes `accepted`.
- Driver activation writes `activated`.
- Driver deactivation writes `deactivated`.
- Admin cancellation writes `cancelled`.
- Events are append-only.
- Do not update or delete activation events during normal API operations.
- `metadata` must be an object when supplied.

Suggested constraints/indexes:

- Check constraint for `event_type`.
- Index on `assignment_id`.
- Index on `actor_user_id`.
- Index on `(assignment_id, occurred_at)`.

Do not create GPS, trip, ping, route, analytics, impression, payout, report, heatmap, or seed tables.

AUDIT EVENT REQUIREMENTS

Use the existing `audit_events` table/service from Slice 1.

Write audit events for admin actions:

- `admin.campaign_assignment.created`
- `admin.campaign_assignment.cancelled`

Do not create a new audit table.

Driver assignment lifecycle transitions are sufficiently captured by `campaign_activation_events`; they do not need separate audit events unless existing audit service patterns make it trivial and consistent.

SECURITY AND VALIDATION REQUIREMENTS

1. Admin assignment endpoints require role `admin`.
2. Driver assignment endpoints require role `driver`.
3. Advertiser users must be rejected from admin and driver assignment endpoints.
4. Admin users must be rejected from driver assignment endpoints.
5. Driver users must only list/read/accept/activate/deactivate assignments tied to their own driver profile.
6. Cross-driver assignment access must not leak data. Prefer 404 where practical.
7. Unauthenticated users must be rejected from all assignment endpoints.
8. Reuse existing auth/current-user dependencies and role-check patterns.
9. Reuse the existing standard error envelope from previous slices.
10. Do not introduce new auth schemes.
11. Do not expose password hashes in embedded user summaries.
12. Do not expose unrelated advertiser billing/user-sensitive data.
13. Do not expose raw driver details to advertiser endpoints because advertiser assignment/reporting APIs are not part of this slice.
14. Use UTC-aware timestamps.
15. Use deterministic status transition validation.

CAMPAIGN, DRIVER, AND VEHICLE ELIGIBILITY RULES

Admin assignment creation:

- Campaign must exist.
- Campaign must not be in status `draft`, `completed`, or `cancelled`.
- Campaign status `scheduled`, `active`, or `paused` is assignable.
- If campaign `end_at` is set and already in the past, assignment creation is rejected.
- Driver profile must exist.
- Driver profile `onboarding_status` must be `active`.
- Vehicle must exist.
- Vehicle `status` must be `active`.
- Vehicle must belong to the driver profile.
- Duplicate non-terminal assignment for same campaign and vehicle is rejected.
- Initial assignment status is `offered`.

Driver accept:

- Current user must own the assignment’s driver profile.
- Assignment status must be `offered`.
- Campaign must not be `completed` or `cancelled`.
- If campaign `end_at` is set and already in the past, accept is rejected.
- Transition: `offered` -> `accepted`.
- Set `accepted_at`.
- Write activation event `accepted`.

Driver activate:

- Current user must own the assignment’s driver profile.
- Assignment status must be `accepted` or `deactivated`.
- Campaign status must be exactly `active`.
- If campaign `start_at` is set and current UTC time is before `start_at`, activation is rejected.
- If campaign `end_at` is set and current UTC time is after `end_at`, activation is rejected.
- Driver profile must still be `active`.
- Vehicle must still be `active`.
- Vehicle must belong to the assignment’s driver profile.
- No other assignment for the same vehicle may currently be `active`.
- Transition: `accepted` or `deactivated` -> `active`.
- Set `activated_at` to current time.
- Write activation event `activated`.

Driver deactivate:

- Current user must own the assignment’s driver profile.
- Assignment status must be `active`.
- Transition: `active` -> `deactivated`.
- Set `deactivated_at`.
- Write activation event `deactivated`.
- No GPS/trip/session closing should occur because GPS/trips are not implemented yet.

Admin cancel:

- Assignment status must not be `completed` or `cancelled`.
- Transition to `cancelled`.
- Set `cancelled_at`.
- Write activation event `cancelled`.
- Write audit event `admin.campaign_assignment.cancelled`.

Do not implement automatic campaign completion, cron jobs, or background lifecycle workers in Slice 5.

API ENDPOINTS

Implement these endpoints under `/api/v1`.

Admin assignment endpoints:

1. `POST /api/v1/admin/campaign-assignments`

Admin-only.

Input:

```json
{
  "campaign_id": "campaign-uuid",
  "driver_profile_id": "driver-profile-uuid",
  "vehicle_id": "vehicle-uuid",
  "notes": "Optional assignment notes",
  "metadata": {}
}

Output: created assignment.

Rules:

Initial status is offered.

Do not allow client to set status or lifecycle timestamps.

Validate campaign, driver profile, and vehicle eligibility.

Write campaign activation event assigned.

Write audit event admin.campaign_assignment.created.

GET /api/v1/admin/campaign-assignments

Admin-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

optional campaign_id

optional driver_profile_id

optional vehicle_id

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

Admin can list assignments across campaigns/drivers/vehicles.

Include minimal campaign, driver profile, vehicle, and assigned-by summaries if straightforward.

Do not expose password hashes.

GET /api/v1/admin/campaign-assignments/{assignment_id}

Admin-only.

Rules:

Admin can read assignment details across campaigns/drivers/vehicles.

Include lifecycle timestamps and recent activation events if straightforward.

Do not expose password hashes.

POST /api/v1/admin/campaign-assignments/{assignment_id}/cancel

Admin-only.

Input:

JSON
{
  "reason": "Optional cancellation reason",
  "metadata": {}
}

Output: updated assignment.

Rules:

Assignment must not already be cancelled or completed.

Write campaign activation event cancelled.

Write audit event admin.campaign_assignment.cancelled.

Driver assignment endpoints:

GET /api/v1/driver/campaign-assignments

Driver-only.

Query parameters:

limit, default 50, max 100

offset, default 0

optional status

Output shape:

JSON
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}

Rules:

Returns only assignments tied to the current driver’s driver profile.

If the current driver has no driver profile, return a clear 404/domain error using the standard error envelope.

GET /api/v1/driver/campaign-assignments/active

Driver-only.

Important routing note:
Define this static route before GET /api/v1/driver/campaign-assignments/{assignment_id} to avoid path conflicts.

Rules:

Returns the current active assignment for the driver, or null / clear 404 depending on existing project style.

Prefer this response shape if no active assignment exists:

JSON
{
  "assignment": null
}

If there are multiple active assignments due to corrupted data, return a deterministic server/domain error and do not silently choose one.

GET /api/v1/driver/campaign-assignments/{assignment_id}

Driver-only.

Rules:

Return the assignment only if it belongs to the current driver profile.

Cross-driver reads must not leak data. Prefer 404.

POST /api/v1/driver/campaign-assignments/{assignment_id}/accept

Driver-only.

Input:

JSON
{
  "metadata": {}
}

Output: updated assignment.

Rules:

Assignment must belong to current driver.

Assignment status must be offered.

Campaign must not be completed/cancelled/expired.

Write campaign activation event accepted.

POST /api/v1/driver/campaign-assignments/{assignment_id}/activate

Driver-only.

Input:

JSON
{
  "metadata": {}
}

Output: updated assignment.

Rules:

Assignment must belong to current driver.

Assignment status must be accepted or deactivated.

Campaign must be active.

Campaign date window must allow activation.

Vehicle and driver profile must still be active.

No other active assignment may exist for the same vehicle.

Write campaign activation event activated.

POST /api/v1/driver/campaign-assignments/{assignment_id}/deactivate

Driver-only.

Input:

JSON
{
  "metadata": {}
}

Output: updated assignment.

Rules:

Assignment must belong to current driver.

Assignment status must be active.

Write campaign activation event deactivated.

RESPONSE SHAPE GUIDANCE

Assignment response should include at minimum:

JSON
{
  "id": "uuid",
  "campaign_id": "uuid",
  "driver_profile_id": "uuid",
  "vehicle_id": "uuid",
  "status": "offered",
  "offered_at": "2026-05-31T00:00:00Z",
  "accepted_at": null,
  "activated_at": null,
  "deactivated_at": null,
  "cancelled_at": null,
  "completed_at": null,
  "notes": "Optional assignment notes",
  "metadata": {},
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:00:00Z"
}

Where useful, list/detail responses may include compact nested summaries:

JSON
{
  "campaign": {
    "id": "uuid",
    "name": "Lagos Launch Campaign",
    "status": "active",
    "start_at": "2026-06-01T00:00:00Z",
    "end_at": "2026-06-30T23:59:59Z"
  },
  "vehicle": {
    "id": "uuid",
    "plate_number": "ABC-123",
    "plate_country_code": "NG",
    "vehicle_type": "car",
    "status": "active"
  },
  "driver_profile": {
    "id": "uuid",
    "user_id": "uuid",
    "onboarding_status": "active"
  }
}

Do not include password hashes.

Activation event response shape, if exposed inside admin detail, should include:

JSON
{
  "id": "uuid",
  "assignment_id": "uuid",
  "event_type": "activated",
  "previous_status": "accepted",
  "new_status": "active",
  "occurred_at": "2026-05-31T00:00:00Z",
  "metadata": {}
}

LIKELY FILES/AREAS TO CREATE OR CHANGE

Use existing Slice 0-Slice 4 conventions. Likely create/change:

app/api/v1/router.py

app/api/v1/campaign_assignments.py or similar

app/models/campaign_assignment.py

app/models/__init__.py

app/schemas/campaign_assignments.py

app/services/campaign_assignments.py

app/services/audit.py only if needed to add action helpers

app/api/v1/dependencies.py only if needed to reuse/add driver/admin helpers

app/db/base.py only if model imports require update

alembic/versions/0006_campaign_assignments.py

README.md

tests/test_campaign_assignments.py

tests/test_migration_slice5.py

Possibly fixture updates in tests/conftest.py

docs/build-loop/reports/slice-05-campaign-assignments.md

Keep code simple. Avoid unnecessary abstractions.

STATUS TRANSITION TABLE

Implement deterministic status transitions:

admin create:
  none -> offered

driver accept:
  offered -> accepted

driver activate:
  accepted -> active
  deactivated -> active

driver deactivate:
  active -> deactivated

admin cancel:
  offered -> cancelled
  accepted -> cancelled
  active -> cancelled
  deactivated -> cancelled

Reject all other transitions with a standard domain error.

Do not implement automatic completed transitions unless the existing service already has an obvious admin-safe path. The completed status exists for forward compatibility and later reporting/payout slices, but no completion automation is required in Slice 5.

TEST REQUIREMENTS

Add/extend tests for:

Admin assignment creation and listing:

Admin can create an assignment for an eligible campaign, active driver profile, and active vehicle.

Assignment creation writes initial status offered.

Assignment creation writes assigned activation event.

Assignment creation writes admin.campaign_assignment.created audit event.

Admin can list assignments with pagination response shape.

Admin can filter assignments by status.

Admin can read one assignment.

Admin can cancel a non-terminal assignment.

Admin cancellation writes cancelled activation event.

Admin cancellation writes admin.campaign_assignment.cancelled audit event.

Admin cannot cancel an already cancelled assignment.

Eligibility validation:

Assignment creation rejects draft campaign.

Assignment creation rejects completed campaign.

Assignment creation rejects cancelled campaign.

Assignment creation rejects campaign with end_at in the past.

Assignment creation rejects non-active driver profile.

Assignment creation rejects non-active vehicle.

Assignment creation rejects vehicle that does not belong to the driver profile.

Assignment creation rejects duplicate non-terminal assignment for same campaign and vehicle.

Assignment creation allows a new assignment after prior assignment is cancelled, if all other eligibility rules pass.

Metadata must be an object.

Notes are trimmed.

Driver assignment access:

Driver can list only own assignments.

Driver can read own assignment.

Driver cannot read another driver’s assignment; use non-leaking 404 where practical.

Driver with no driver profile receives clear standard error for driver assignment list.

Advertiser user is rejected from driver assignment endpoints.

Admin user is rejected from driver assignment endpoints.

Unauthenticated user is rejected from all assignment endpoints.

Driver user is rejected from admin assignment endpoints.

Advertiser user is rejected from admin assignment endpoints.

Driver lifecycle:

Driver can accept own offered assignment.

Accepting assignment sets accepted_at.

Accepting assignment writes accepted activation event.

Driver cannot accept another driver’s assignment.

Driver cannot accept assignment that is already accepted.

Driver cannot accept cancelled assignment.

Driver can activate own accepted assignment when campaign is active and within date window.

Activating assignment sets activated_at.

Activating assignment writes activated activation event.

Driver can activate a previously deactivated assignment when still eligible.

Driver cannot activate an offered assignment before accepting.

Driver cannot activate when campaign is scheduled but not active.

Driver cannot activate when campaign is paused.

Driver cannot activate when current time is before campaign start_at.

Driver cannot activate when current time is after campaign end_at.

Driver cannot activate when driver profile is no longer active.

Driver cannot activate when vehicle is no longer active.

Driver cannot activate if another assignment is already active for the same vehicle.

Driver can deactivate own active assignment.

Deactivating assignment sets deactivated_at.

Deactivating assignment writes deactivated activation event.

Driver cannot deactivate assignment that is not active.

GET /api/v1/driver/campaign-assignments/active returns the active assignment when one exists.

GET /api/v1/driver/campaign-assignments/active returns {"assignment": null} or equivalent documented no-active shape when none exists.

Migration and scope:

Alembic migration creates exactly campaign_assignments and campaign_activation_events as new Slice 5 tables.

Migration creates expected indexes, including active vehicle uniqueness where feasible.

Migration does not create GPS, trip, ping, analytics, impression, payout, report, heatmap, or seed tables.

Existing Slice 0-Slice 4 tests continue to pass.

API responses do not expose password hashes.

Testing implementation guidance:

Reuse existing test fixtures and auth helpers from prior slices.

Prefer deterministic time handling. Use fixed timestamps or monkeypatch/freezegun only if already available; do not add heavy time libraries unnecessarily.

If existing tests use SQLite for speed, maintain compatibility where practical, but do not weaken Postgres migration verification.

Migration verification against Postgres/PostGIS remains required.

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

If any command cannot be run locally due to missing external runtime or local environment issues, report that honestly with exact evidence.

FRONTEND CONTRACT NOTES

Admin tools can use:

http
POST /api/v1/admin/campaign-assignments
GET  /api/v1/admin/campaign-assignments
GET  /api/v1/admin/campaign-assignments/{assignment_id}
POST /api/v1/admin/campaign-assignments/{assignment_id}/cancel

Driver app can use:

http
GET  /api/v1/driver/campaign-assignments
GET  /api/v1/driver/campaign-assignments/active
GET  /api/v1/driver/campaign-assignments/{assignment_id}
POST /api/v1/driver/campaign-assignments/{assignment_id}/accept
POST /api/v1/driver/campaign-assignments/{assignment_id}/activate
POST /api/v1/driver/campaign-assignments/{assignment_id}/deactivate

All protected endpoints must use bearer token auth:

http
Authorization: Bearer <token>

Driver activation only marks a campaign assignment as active. GPS tracking, trip sessions, and location ping ingestion are not available until Slice 6.

STANDARD ERROR BEHAVIOR

Use the existing Slice 0-Slice 4 error envelope for expected errors.

Expected examples:

Missing token

Invalid token

Forbidden role

Assignment not found

Assignment belongs to another driver

Driver profile missing

Campaign not assignable

Campaign not active for activation

Campaign outside date window

Driver profile not active

Vehicle not active

Vehicle does not belong to driver profile

Duplicate active assignment for vehicle

Duplicate non-terminal assignment for campaign and vehicle

Invalid assignment transition

Invalid metadata

Do not return raw stack traces.

ACCEPTANCE CRITERIA

Slice 5 is acceptable only if:

Alembic migration creates exactly the approved campaign_assignments and campaign_activation_events tables, constraints, and indexes.

No Slice 6+ domain tables are added.

Admin can create/list/read/cancel campaign assignments.

Assignment creation validates campaign, driver profile, vehicle, ownership, and duplicate non-terminal assignment rules.

Driver users can list/read only their own assignments.

Driver users can accept, activate, and deactivate only their own assignments.

Deterministic lifecycle transitions are enforced.

One active assignment per vehicle is enforced.

Campaign status/date activation rules are enforced.

Assignment activation events are written for assigned/accepted/activated/deactivated/cancelled transitions.

Audit events are written for admin-created and admin-cancelled assignments.

Admin/driver/advertiser/unauthenticated access boundaries are enforced.

API responses do not expose password hashes or unrelated sensitive data.

Tests pass.

Ruff passes.

Alembic upgrade head passes against Postgres/PostGIS.

Python 3.12 verification is performed through Docker or explicitly reported if impossible.

No deferred/future scope is implemented.

STOP CONDITIONS

Stop and report instead of implementing if:

Slice 4 accepted foundation is missing or materially different from the packet.

The existing project uses a materially different stack than the approved stack.

agent.md conflicts with this prompt.

The DB/migration setup cannot support assignment status constraints/indexes without reworking previous slices.

Existing campaign, driver profile, or vehicle status behavior makes assignment eligibility ambiguous in a way that requires a product decision.

Existing router path structure makes /driver/campaign-assignments/active conflict unavoidable without changing the endpoint contract.

You are tempted to add GPS pings, trip sessions, route analytics, fraud flags, impressions, payouts, reports, heatmaps, map tiles, or seed/demo scope.

Otherwise, stop after Slice 5. Do not continue to Slice 6.

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
Assignment lifecycle approach:
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
Assignment lifecycle implemented:
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
Assignment lifecycle implemented:
Tests/checks run:
Exact command outputs or concise failure excerpts:
Known issues:
Out-of-scope confirmation:
Acceptance criteria checklist:
Codex questions:
Orchestrator recommendation: PASS_CANDIDATE | NEEDS_FIX | BLOCKED