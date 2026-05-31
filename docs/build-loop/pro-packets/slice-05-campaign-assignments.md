PRO REVIEW PACKET

Slice:
Slice 5 - Campaign assignment and driver/vehicle activation

Repo state summary:
- Branch: `slice-05-campaign-assignments`
- Base accepted state: Slice 4 recorded at `9722ef4 docs: record slice 4 commit`
- Current status: uncommitted Slice 5 PASS_CANDIDATE
- Current Alembic head after Slice 5: `0006_campaign_assignments`
- API prefix remains `/api/v1`
- Fixed stack preserved: FastAPI, Pydantic v2, SQLAlchemy async, asyncpg, Alembic, PostgreSQL/PostGIS, Redis, JWT, pytest, ruff, Docker Compose.

Commit status:
- No Slice 5 commit has been created yet.
- Working tree contains only the Slice 5 implementation/report/ledger changes listed below.
- Intended commit only after Pro PASS and local reconciliation.

Files changed:
- `README.md`
- `alembic/versions/0006_campaign_assignments.py`
- `app/api/v1/campaign_assignments.py`
- `app/api/v1/router.py`
- `app/db/base.py`
- `app/models/campaign_assignment.py`
- `app/schemas/campaign_assignments.py`
- `app/services/campaign_assignments.py`
- `docs/build-loop/reports/slice-05-campaign-assignments.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_campaign_assignments.py`
- `tests/test_migration_slice5.py`

Diff summary:
- Adds `campaign_assignments` and `campaign_activation_events` models with string enums, check constraints, metadata column aliasing, timestamps, indexes, and partial unique indexes for active/non-terminal assignment rules.
- Adds Slice 5 Alembic migration `0006_campaign_assignments` after `0005_campaign_zones`.
- Adds admin assignment endpoints for create/list/read/cancel.
- Adds driver endpoints for own assignment list/read/current-active/accept/activate/deactivate.
- Adds service-layer campaign, driver profile, vehicle eligibility checks; deterministic transition checks; non-leaking driver ownership lookups; assignment event creation; and admin audit integration.
- Adds Pydantic schemas with forbidden extras, metadata object validation through typed dict fields, and trimmed notes/reasons.
- Mounts the new router and imports models into DB metadata.
- Extends tests/fixtures for assignment setup, activation event reads, lifecycle/RBAC/eligibility/uniqueness tests, and migration guardrails.
- Updates README and build-loop ledger/report.

Database migrations:
- New migration: `alembic/versions/0006_campaign_assignments.py`
- Down revision: `0005_campaign_zones`
- Creates exactly two new Slice 5 business tables:
  - `campaign_assignments`
  - `campaign_activation_events`
- `campaign_assignments` columns:
  - `id` UUID primary key, `gen_random_uuid()`
  - `campaign_id` UUID FK to `campaigns.id`, not null, cascade delete
  - `driver_profile_id` UUID FK to `driver_profiles.id`, not null, cascade delete
  - `vehicle_id` UUID FK to `vehicles.id`, not null, cascade delete
  - `assigned_by_user_id` UUID FK to `users.id`, not null
  - `status` string constrained to `offered`, `accepted`, `active`, `deactivated`, `cancelled`, `completed`
  - lifecycle timestamps: `offered_at`, `accepted_at`, `activated_at`, `deactivated_at`, `cancelled_at`, `completed_at`
  - `notes` text
  - `metadata` JSONB, not null, default `'{}'::jsonb`
  - `created_at` and `updated_at` timezone-aware timestamps
- `campaign_activation_events` columns:
  - `id` UUID primary key, `gen_random_uuid()`
  - `assignment_id` UUID FK to `campaign_assignments.id`, not null, cascade delete
  - `actor_user_id` UUID FK to `users.id`, nullable
  - `event_type` string constrained to `assigned`, `accepted`, `activated`, `deactivated`, `cancelled`, `completed`
  - `previous_status`, `new_status`, `occurred_at`, `metadata`
- Indexes include campaign/driver/vehicle/status filters, activation event lookup/order, and PostgreSQL partial unique indexes:
  - one active assignment per vehicle
  - one non-terminal assignment per `(campaign_id, vehicle_id)` where status is `offered`, `accepted`, `active`, or `deactivated`
- Does not add GPS, trip, ping, route, analytics, impression, payout, report, heatmap, seed, or future-scope tables.

API endpoints:
- `POST /api/v1/admin/campaign-assignments`
- `GET /api/v1/admin/campaign-assignments`
- `GET /api/v1/admin/campaign-assignments/{assignment_id}`
- `POST /api/v1/admin/campaign-assignments/{assignment_id}/cancel`
- `GET /api/v1/driver/campaign-assignments`
- `GET /api/v1/driver/campaign-assignments/active`
- `GET /api/v1/driver/campaign-assignments/{assignment_id}`
- `POST /api/v1/driver/campaign-assignments/{assignment_id}/accept`
- `POST /api/v1/driver/campaign-assignments/{assignment_id}/activate`
- `POST /api/v1/driver/campaign-assignments/{assignment_id}/deactivate`

Security/validation implemented:
- Admin endpoints require `admin`.
- Driver endpoints require `driver`.
- Advertiser/wrong-role/unauthenticated access is rejected by existing auth dependency patterns and standard error envelope.
- Driver endpoints resolve the current user's driver profile first and then query by `assignment_id` plus `driver_profile_id`, giving non-leaking 404s for cross-driver access.
- Admin create validates:
  - campaign exists
  - campaign status is `scheduled`, `active`, or `paused`
  - campaign is not expired
  - driver profile exists and is `active`
  - vehicle exists and is `active`
  - vehicle belongs to driver profile
  - no duplicate non-terminal campaign/vehicle assignment
- Driver accept validates own assignment, `offered` status, and campaign not completed/cancelled/expired.
- Driver activate validates own assignment, `accepted` or `deactivated` status, campaign status exactly `active`, campaign date window, active driver profile, active vehicle, ownership, and no other active assignment for vehicle.
- Driver deactivate validates own assignment and `active` status.
- Admin cancel rejects `cancelled` and `completed` assignments.
- Request schemas forbid extra fields. Notes/reasons are trimmed. Metadata fields require JSON objects.
- Responses avoid password hashes and unrelated sensitive data.

Assignment lifecycle implemented:
- Admin create: none -> `offered`; sets `offered_at`; writes `assigned` activation event; writes `admin.campaign_assignment.created` audit event.
- Driver accept: `offered` -> `accepted`; sets `accepted_at`; writes `accepted`.
- Driver activate: `accepted`/`deactivated` -> `active`; sets `activated_at`; writes `activated`.
- Driver deactivate: `active` -> `deactivated`; sets `deactivated_at`; writes `deactivated`.
- Admin cancel: `offered`/`accepted`/`active`/`deactivated` -> `cancelled`; sets `cancelled_at`; writes `cancelled`; writes `admin.campaign_assignment.cancelled` audit event.
- Activation events are append-only during normal API operations.
- Admin assignment/status change, activation event, audit event, and commit happen through one session transaction per route.

Tests/checks run:
- `python -m pytest tests/test_campaign_assignments.py tests/test_migration_slice5.py -q`
- `python -m pytest`
- `python -m ruff check .`
- `python -m alembic upgrade head` with Postgres/PostGIS `DATABASE_URL`
- `python -m alembic current` with Postgres/PostGIS `DATABASE_URL`
- `python -m pytest` with Postgres/PostGIS `DATABASE_URL`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Exact command outputs or concise failure excerpts:
- Targeted host tests:
  - `9 passed, 1 warning in 22.29s`
- Host full tests without `DATABASE_URL`:
  - `80 passed, 8 skipped, 1 warning in 94.49s`
- Host ruff:
  - `All checks passed!`
- Host Alembic upgrade/current with `DATABASE_URL=postgresql+asyncpg://mobility:mobility@localhost:5433/mobility`:
  - upgrade passed
  - current: `0006_campaign_assignments (head)`
- Host full tests with same `DATABASE_URL`:
  - `88 passed, 1 warning in 131.14s`
- Docker build:
  - image `mobility-api:latest` built successfully
- Docker Python:
  - `Python 3.12.13`
- Docker full tests:
  - `88 passed, 1 warning in 124.54s`
- Docker ruff:
  - `All checks passed!`

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- Existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.
- PostGIS campaign zone tests intentionally skip on host when no `DATABASE_URL` or `TEST_DATABASE_URL` is configured. They pass with a real PostGIS URL and in Docker.

Out-of-scope confirmation:
- No GPS pings.
- No trip sessions.
- No location ingestion.
- No route analytics or zone-overlap analytics.
- No fraud flags.
- No impression estimation.
- No payout calculation or earnings ledger.
- No advertiser dashboard/reporting APIs.
- No heatmap APIs.
- No map tiles, map providers, or geocoding.
- No creative binary upload/storage pipeline.
- No seed/demo trip data.
- No background jobs.
- No frontend/mobile implementation.
- No deployment/payment settlement/retargeting/audience pooling/AI scope.

Acceptance criteria checklist:
- Alembic migration creates exactly `campaign_assignments` and `campaign_activation_events`: yes.
- No Slice 6+ domain tables are added: yes.
- Admin can create/list/read/cancel campaign assignments: yes.
- Assignment creation validates campaign, driver profile, vehicle, ownership, and duplicate rules: yes.
- Driver users can list/read only their own assignments: yes.
- Driver users can accept, activate, and deactivate only their own assignments: yes.
- Deterministic lifecycle transitions are enforced: yes.
- One active assignment per vehicle is enforced: yes, service check plus PostgreSQL partial unique index.
- Duplicate non-terminal campaign/vehicle assignment is enforced: yes, service check plus PostgreSQL partial unique index.
- Campaign status/date activation rules are enforced: yes.
- Assignment activation events are written for assigned/accepted/activated/deactivated/cancelled transitions: yes.
- Audit events are written for admin-created and admin-cancelled assignments: yes.
- Admin/driver/advertiser/unauthenticated boundaries are enforced: yes.
- API responses do not expose password hashes or unrelated sensitive data: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Codex questions:
- None.

Orchestrator recommendation: PASS_CANDIDATE
