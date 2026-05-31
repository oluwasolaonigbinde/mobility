CODEX BUILD REPORT

Slice: Slice 2 - Driver and vehicle foundations
Status: PASS_CANDIDATE

Summary:
Implemented the approved supply-side foundation only: driver profiles, vehicle profiles, admin and driver APIs, ownership/access boundaries, normalization/validation, audit events for admin actions, Slice 2 Alembic migration, tests, and README endpoint notes.

Local investigation performed:
- Confirmed current branch: `slice-02-driver-vehicle-foundations`.
- Confirmed the only pre-existing uncommitted file was `docs/build-loop/slice-log.md`, already marking Slice 2 in progress.
- Read `agent.md`.
- Read the approved Slice 2 prompt.
- Read accepted Slice 0 and Slice 1 build reports.
- Inspected existing app structure, `/api/v1` router prefix, settings, request ID middleware, standard error envelope, DB session setup, Alembic setup, auth dependencies, RBAC patterns, models, schemas, services, and tests.
- Confirmed roles are `admin`, `advertiser`, and `driver`.
- Confirmed no existing driver profile or vehicle tables/models were present.

Files changed:
- `README.md`
- `alembic/versions/0003_driver_vehicle_foundations.py`
- `app/api/v1/dependencies.py`
- `app/api/v1/driver_profiles.py`
- `app/api/v1/router.py`
- `app/api/v1/vehicles.py`
- `app/core/errors.py`
- `app/db/base.py`
- `app/models/driver.py`
- `app/models/vehicle.py`
- `app/schemas/drivers.py`
- `app/schemas/vehicles.py`
- `app/services/drivers.py`
- `app/services/vehicles.py`
- `docs/build-loop/reports/slice-02-driver-vehicle-foundations.md`
- `docs/build-loop/slice-log.md`
- `tests/conftest.py`
- `tests/test_driver_profiles.py`
- `tests/test_migration_slice2.py`
- `tests/test_vehicles.py`

Database migrations:
- Added `0003_driver_vehicle_foundations`, after `0002_identity_and_organizations`.
- Creates only `driver_profiles` and `vehicles`.
- Uses UUID primary keys with `gen_random_uuid()`.
- Adds driver onboarding status, vehicle type, and vehicle status check constraints.
- Adds unique one-profile-per-driver constraint on `driver_profiles.user_id`.
- Adds unique normalized plate constraint on `(plate_country_code, plate_number_normalized)`.
- Adds approved foreign keys and indexes for user/profile ownership, statuses, country/city, and normalized plates.

API endpoints implemented:
- `GET /api/v1/driver/profile`
- `PATCH /api/v1/driver/profile`
- `GET /api/v1/driver/vehicles`
- `GET /api/v1/driver/vehicles/{vehicle_id}`
- `POST /api/v1/admin/drivers/{user_id}/profile`
- `GET /api/v1/admin/drivers`
- `GET /api/v1/admin/drivers/{driver_profile_id}`
- `PATCH /api/v1/admin/drivers/{driver_profile_id}`
- `POST /api/v1/admin/drivers/{user_id}/vehicles`
- `GET /api/v1/admin/vehicles`
- `GET /api/v1/admin/vehicles/{vehicle_id}`
- `PATCH /api/v1/admin/vehicles/{vehicle_id}`

Security/validation implemented:
- Admin supply endpoints require role `admin`.
- Driver supply endpoints require role `driver`.
- Advertiser and unauthenticated users are rejected from protected supply endpoints.
- Driver profiles can only be created for existing driver users.
- One driver profile per driver user is enforced by service checks and DB uniqueness.
- Driver self-profile updates allow only license number, service city, and country code.
- Drivers can list/read only vehicles attached to their own driver profile.
- Admin vehicle creation requires an existing driver user with an existing driver profile.
- Country codes are normalized uppercase.
- Driver profile text fields are trimmed.
- Vehicle plate display text is trimmed.
- Vehicle `plate_number_normalized` is uppercased with whitespace and hyphens removed.
- Duplicate normalized vehicle plates are rejected within the same plate country.
- Vehicle type/status enums and reasonable year bounds are validated.
- Password hashes are not returned in driver or vehicle user summaries.
- Validation errors continue to use the standard error envelope; the handler now JSON-encodes validation details so custom Pydantic validation errors cannot leak stack traces.
- Audit events are written for `admin.driver_profile.created`, `admin.driver_profile.updated`, `admin.vehicle.created`, and `admin.vehicle.updated`.

Tests added/updated:
- Added driver profile API tests for admin create/list/read/update, non-driver rejection, duplicate profile rejection, driver own read/update, missing profile envelope, forbidden self status update, advertiser rejection, unauthenticated rejection, audit events, and password-hash non-exposure.
- Added direct driver onboarding status validation coverage for invalid admin create/update payloads after a clean fix-pass review.
- Added vehicle API tests for admin create/list/read/update, non-driver and missing-profile rejection, duplicate normalized plate rejection, same plate in another country, invalid type/status/year rejection, driver own list/read, cross-driver non-leakage, missing profile, advertiser/unauthenticated rejection, audit events, update plate recomputation, and password-hash non-exposure.
- Added Slice 2 migration guard test.
- Extended test fixtures for driver profiles and vehicles.

Commands run:
- `python -m ruff check .`
- `python -m pytest`
- `python -m pytest tests/test_driver_profiles.py`
- `docker compose up -d db`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic upgrade head`
- `$env:DATABASE_URL='postgresql+asyncpg://mobility:mobility@localhost:5433/mobility'; python -m alembic current`
- `docker compose build api`
- `docker compose run --rm api python --version`
- `docker compose run --rm api python -m pytest`
- `docker compose run --rm api python -m ruff check .`

Command results:
- Host `python -m ruff check .`: all checks passed.
- Host targeted `python -m pytest tests/test_driver_profiles.py`: 11 passed, 1 existing FastAPI/TestClient deprecation warning.
- Host `python -m pytest`: 53 passed, 1 existing FastAPI/TestClient deprecation warning.
- `docker compose up -d db`: DB container running.
- Host Alembic upgrade with configured Postgres URL: passed; database is at head.
- Host Alembic current with configured Postgres URL: `0003_driver_vehicle_foundations (head)`.
- Docker API build: succeeded.
- Docker Python version: Python 3.12.13.
- Docker `python -m pytest`: 53 passed, 1 existing FastAPI/TestClient deprecation warning.
- Docker `python -m ruff check .`: all checks passed.

Known issues:
- Host Python is 3.14.4, while the fixed stack is Python 3.12. Docker verified Python 3.12.13 successfully.
- The existing FastAPI/TestClient stack emits a deprecation warning about `httpx`; tests pass.

Out-of-scope compliance:
- No campaigns, creatives, geofences/zones, campaign assignments, campaign activation, GPS pings, trip sessions, route analytics, fraud flags, impression estimation, payout calculation, earnings ledger, advertiser dashboard/report APIs, heatmap APIs, seed/demo data, Celery/background jobs, frontend/mobile code, GitHub remote/PR setup, production deployment, retargeting, audience pooling, AI/computer vision, or payment settlement were implemented.
- Implementation and fix-pass workers did not touch Pro packet or Pro response files. The orchestrator creates the Pro packet separately after local verification.
- No commit was created.

Acceptance criteria checklist:
- Alembic migration creates approved `driver_profiles` and `vehicles` tables: yes.
- No Slice 3+ domain tables are added: yes.
- Driver profiles can only be associated with driver users: yes.
- One driver profile per driver user is enforced: yes.
- Admin can create/list/read/update driver profiles: yes.
- Driver can read/update only their own existing profile: yes.
- Admin can create/list/read/update vehicles: yes.
- Vehicle ownership is tied to driver profiles: yes.
- Driver can list/read only their own vehicles: yes.
- Duplicate normalized vehicle plates are rejected within the same plate country: yes.
- Vehicle validation covers type, status, country code normalization, plate normalization, and year: yes.
- Admin/driver/advertiser access boundaries are enforced: yes.
- Audit events are written for admin-created/updated driver profiles and vehicles: yes.
- API responses do not expose password hashes: yes.
- Tests pass: yes.
- Ruff passes: yes.
- Alembic upgrade head passes against Postgres/PostGIS: yes.
- Python 3.12 verification performed: yes, via Docker.
- No deferred/future scope implemented: yes.

Manual verification steps:
- Use an admin bearer token to create a driver user, create `/api/v1/admin/drivers/{user_id}/profile`, then create `/api/v1/admin/drivers/{user_id}/vehicles`.
- Use the driver bearer token to call `/api/v1/driver/profile` and `/api/v1/driver/vehicles`.
- Confirm `plate_number_normalized` removes whitespace and hyphens and is unique per `plate_country_code`.

Questions for Pro reviewer:
- None.
